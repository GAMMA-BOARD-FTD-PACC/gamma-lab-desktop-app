from typing import List, Optional, Literal
import numpy as np
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

EndMode = Literal["fixed", "until_next_onset"]


def _detect_onsets_abs(
    signal: np.ndarray,
    fs: float,
    threshold: float,
    min_distance_s: Optional[float],
) -> List[int]:
    """
    Detecta onsets (inicios) donde |signal| pasa de <= umbral a > umbral.
    Equivale a la "máquina de estados" del MATLAB pero vectorizado.

    Devuelve índices de muestra (enteros) de cada onset.
    """
    x = np.abs(signal.astype(np.float64, copy=False))
    thr = float(threshold)

    # Booleano: True donde la señal supera el umbral
    above = x > thr
    if above.size < 2:
        return []

    # Flanco ascendente: de False a True
    rising = np.flatnonzero((~above[:-1]) & (above[1:])) + 1
    if rising.size == 0:
        return []

    # Si no pides separación mínima, devolvemos todos los flancos
    if not min_distance_s or min_distance_s <= 0:
        return rising.astype(int).tolist()

    # De lo contrario, "filtrado" por distancia mínima entre onsets
    min_dist = int(round(min_distance_s * fs))
    picks = [int(rising[0])]
    last = picks[0]
    for idx in rising[1:]:
        if idx - last >= min_dist:
            picks.append(int(idx))
            last = int(idx)
    return picks


def cut_trials_single_channel(
    ds: SignalDataset,
    channel: int,
    threshold: float,
    t0: float,                     # offset relativo al onset (negativo = pre-estímulo)
    t1: float,                     # solo se usa en "fixed"
    stim_expected: Optional[int] = None,  # cantidad de estímulos "
    isi: Optional[float] = None,           # separación mínima entre cruces (s)
    end_mode: EndMode = "fixed",          # "fixed" | "until_next_onset"
) -> TrialDataset:
    """
    Corta trials usando |y| > threshold como trigger.

    - fixed:             ventana fija [t0, t1) respecto a cada onset.
    - until_next_onset:  desde (onset + t0) hasta el *siguiente onset* (o fin de señal).
                         (Columnas con padding a la longitud máxima para mantener matriz rectangular).
    """
    fs = float(ds.sampling_rate)
    C, N = ds.signals.shape
    if not (0 <= channel < C):
        raise ValueError(f"channel fuera de rango (C={C})")

    y = ds.signals[channel].astype(np.float64, copy=False)

    # ------------------------------------------------------------
    # 1) DETECCIÓN de todos los onsets (equivalente a la ME del MATLAB)
    # ------------------------------------------------------------
    onsets_all = _detect_onsets_abs(y, fs, float(threshold), isi)  # índices (int)
    K = len(onsets_all)  # # de estímulos detectados

    # Caso sin estímulos detectados: devolvemos la señal completa como 1 columna
    if K == 0:
        trials = y.reshape(-1, 1)
        time_rel = np.arange(y.shape[0], dtype=np.float64) / fs
        dur = time_rel[-1] if time_rel.size else 0.0
        return TrialDataset(
            source=ds.source_path, sampling_rate=fs,
            channel_index=channel,
            channel_name=(ds.channel_names[channel] if channel < len(ds.channel_names) else f"ch{channel}"),
            unit=(ds.units[channel] if channel < len(ds.units) else ""),
            t0=0.0, t1=dur, time_rel=time_rel,
            trials=trials, onsets_s=[], isi_s=[],
            metadata={"end_mode": end_mode, "note": "sin_estímulos"},
        )

    # ------------------------------------------------------------
    # 2) SELECCIÓN según Stim Number (stim_expected)
    #    >>> OJO: Aquí fijamos cuántos trials construir
    # ------------------------------------------------------------
    if stim_expected is None or stim_expected <= 0:
        T = K                       # usar todos los estímulos detectados
    else:
        T = min(stim_expected, K)   # usar hasta 'stim_expected' (si hay menos, se recorta)

    # Índices de onsets que sí se convertirán en columnas
    sel_idx = list(range(T))
    onsets_sel = [onsets_all[i] for i in sel_idx]  # inicios "reales" de cada trial

    # ------------------------------------------------------------
    # 3) CONSTRUCCIÓN de las columnas (dos modos)
    # ------------------------------------------------------------
    if end_mode == "until_next_onset":
        # a) Para cada onset_i, el fin es el onset_{i+1}; para el último, fin = N
        ends_all = [onsets_all[i + 1] if (i + 1) < K else N for i in range(K)]
        # b) Offset inicial en muestras (permite pre-estímulo si t0 < 0)
        n0 = int(round(t0 * fs))
        # c) Longitud (en muestras) de cada trial seleccionado (varía por trial)
        lengths = [max(0, ends_all[i] - (onsets_all[i] + n0)) for i in sel_idx]
        Ns = max(lengths) if lengths else 0
        if Ns <= 0:
            Ns = 1  # evita matriz vacía

        trials = np.zeros((Ns, T), dtype=np.float64)
        for t, i in enumerate(sel_idx):
            a = onsets_all[i] + n0
            b = ends_all[i]
            a_clip = max(a, 0)
            b_clip = min(b, N)
            if b_clip > a_clip:
                seg = y[a_clip:b_clip]
                start = a_clip - a  # padding si a<0 (mueve el inicio dentro de la columna)
                trials[start:start + seg.shape[0], t] = seg

        # Eje temporal relativo compartido (de t0 hasta t0+Ns/fs)
        time_rel = (np.arange(n0, n0 + Ns, dtype=np.int64) / fs).astype(np.float64)
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    else:  # end_mode == "fixed"
        if t1 <= t0:
            raise ValueError("En 'fixed' se requiere t1 > t0.")
        n0 = int(round(t0 * fs))
        n1 = int(round(t1 * fs))
        Ns = n1 - n0

        trials = np.zeros((Ns, T), dtype=np.float64)
        for t, i in enumerate(sel_idx):
            a = onsets_all[i] + n0
            b = onsets_all[i] + n1
            a_clip = max(a, 0)
            b_clip = min(b, N)
            if b_clip > a_clip:
                seg = y[a_clip:b_clip]
                start = a_clip - a
                trials[start:start + seg.shape[0], t] = seg

        time_rel = (np.arange(n0, n1, dtype=np.int64) / fs).astype(np.float64)
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    # ------------------------------------------------------------
    # 4) Salida coherente con TrialDataset
    #    - onsets_s debe tener T elementos (uno por columna)
    #    - isi_s se calcula SOLO entre los onsets seleccionados (no todos)
    # ------------------------------------------------------------
    onsets_s_sel = [i / fs for i in onsets_sel]
    isi_s_sel = (np.diff(onsets_s_sel).tolist() if T > 1 else [])

    return TrialDataset(
        source=ds.source_path,
        sampling_rate=fs,
        channel_index=channel,
        channel_name=(ds.channel_names[channel] if channel < len(ds.channel_names) else f"ch{channel}"),
        unit=(ds.units[channel] if channel < len(ds.units) else ""),
        t0=float(t0),
        t1=t1_report,
        time_rel=time_rel,
        trials=trials,
        onsets_s=onsets_s_sel,
        isi_s=isi_s_sel,
        metadata={
            "end_mode": end_mode,
            "stim_expected": (None if stim_expected is None or stim_expected <= 0 else int(stim_expected)),
            "stim_detected": int(K),
            "note": ("stim_detected < stim_expected → faltan onsets"
                     if (stim_expected and K < stim_expected) else "")
        },
    )

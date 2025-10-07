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
    stim_expected: Optional[int] = None,  # ahora: Nº de estímulos POR TRIAL
    isi: Optional[float] = None,          # separación mínima entre cruces (s)
    end_mode: EndMode = "fixed",          # "fixed" | "until_next_onset"
) -> TrialDataset:
    """
    Corta trials usando |y| > threshold como trigger.

    - fixed:             ventana fija [t0, t1) respecto al PRIMER onset de cada grupo.
    - until_next_onset:  desde (first_onset + t0) hasta el onset situado 'stim_expected'
                         posiciones después (o fin de señal). Se hace padding para matriz rectangular.

    NOTA: 'stim_expected' indica cuántos ESTÍMULOS hay por trial; el número de trials
    se obtiene agrupando los onsets detectados en bloques consecutivos de tamaño 'stim_expected'.
    """
    fs = float(ds.sampling_rate)
    C, N = ds.signals.shape
    if not (0 <= channel < C):
        raise ValueError(f"channel fuera de rango (C={C})")

    y = ds.signals[channel].astype(np.float64, copy=False)

    # 1) Detección de onsets
    onsets_all = _detect_onsets_abs(y, fs, float(threshold), isi)
    K = len(onsets_all)
    print(f"[DEBUG] Detectados {K} onsets en canal {channel}")

    # Caso sin onsets → 1 “trial” con toda la señal (comportamiento previo)
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

    # 2) Agrupación por 'stim_expected' estímulos por trial
    if stim_expected is None or stim_expected <= 0:
        stim_per_trial = 1
    else:
        stim_per_trial = int(stim_expected)

    # Número de trials = grupos completos de 'stim_per_trial'
    T = K // stim_per_trial
    if T <= 0:
        # No alcanza para formar ni un grupo completo → por consistencia, usar 1 trial desde el primer onset
        stim_per_trial = 1
        T = K

    # Índices de inicio de cada trial (primer onset de cada grupo)
    # p.ej., si stim_per_trial=3 y K=10 → starts=[0,3,6] (T=3) y el último onset queda suelto y se descarta
    group_starts = [i * stim_per_trial for i in range(T)]
    first_onsets = [onsets_all[s] for s in group_starts]  # primeros onsets por trial

    # 3) Construcción de columnas según modo
    if end_mode == "until_next_onset":
        # El fin de cada trial es el onset del siguiente GRUPO (s + stim_per_trial),
        # o fin de la señal si no existe.
        # También permitimos t0 negativo (pre-estímulo)
        n0 = int(round(t0 * fs))

        # Longitud (en muestras) de cada trial (varía con la separación entre grupos)
        lengths = []
        for g in range(T):
            start_idx = group_starts[g]
            a_onset = onsets_all[start_idx]
            # El "siguiente grupo" empieza en start_idx + stim_per_trial
            next_group_idx = start_idx + stim_per_trial
            b_onset = onsets_all[next_group_idx] if next_group_idx < K else N
            length = max(0, b_onset - (a_onset + n0))
            lengths.append(length)

        Ns = max(lengths) if lengths else 0
        if Ns <= 0:
            Ns = 1

        trials = np.zeros((Ns, T), dtype=np.float64)
        for tcol, start_idx in enumerate(group_starts):
            a_onset = onsets_all[start_idx]
            next_group_idx = start_idx + stim_per_trial
            b_onset = onsets_all[next_group_idx] if next_group_idx < K else N

            a = a_onset + n0
            b = b_onset
            a_clip = max(a, 0)
            b_clip = min(b, N)
            if b_clip > a_clip:
                seg = y[a_clip:b_clip]
                start = a_clip - a  # padding si a<0
                trials[start:start + seg.shape[0], tcol] = seg

        time_rel = (np.arange(n0, n0 + Ns, dtype=np.int64) / fs).astype(np.float64)
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    else:  # fixed
        if t1 <= t0:
            raise ValueError("En 'fixed' se requiere t1 > t0.")
        n0 = int(round(t0 * fs))
        n1 = int(round(t1 * fs))
        Ns = n1 - n0

        trials = np.zeros((Ns, T), dtype=np.float64)
        for tcol, start_idx in enumerate(group_starts):
            a_onset = onsets_all[start_idx]
            a = a_onset + n0
            b = a_onset + n1
            a_clip = max(a, 0)
            b_clip = min(b, N)
            if b_clip > a_clip:
                seg = y[a_clip:b_clip]
                start = a_clip - a
                trials[start:start + seg.shape[0], tcol] = seg

        time_rel = (np.arange(n0, n1, dtype=np.int64) / fs).astype(np.float64)
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    print(f"[DEBUG] stim_per_trial={stim_per_trial}, grupos(T)={T}")
    print(f"[DEBUG] Matriz de trials generada con {trials.shape[1]} trials × {trials.shape[0]} muestras")

    # 4) Metadatos coherentes
    # onsets_s: usamos el PRIMER onset de cada trial como “timestamp” del trial
    onsets_s_sel = [i / fs for i in first_onsets]
    # isi entre trials (entre primeros onsets consecutivos)
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
        trials=trials,                 # (Ns, T) = (muestras, trials)
        onsets_s=onsets_s_sel,         # primer onset de cada trial
        isi_s=isi_s_sel,
        metadata={
            "end_mode": end_mode,
            "stim_per_trial": int(stim_per_trial),
            "stim_detected": int(K),
            "trials_built": int(T),
            "note": ("últimos onsets descartados por no completar grupo"
                     if (K % stim_per_trial != 0) else "")
        },
    )


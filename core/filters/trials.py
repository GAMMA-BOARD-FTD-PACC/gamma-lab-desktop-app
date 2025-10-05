from typing import List, Optional
import numpy as np
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset


def _detect_onsets_abs(
    signal: np.ndarray, fs: float, threshold: float, min_distance_s: Optional[float]
) -> List[int]:
    """
    Detecta flancos ascendentes de |signal| > threshold.
    """
    x = np.abs(signal.astype(np.float64, copy=False))
    thr = float(threshold)

    above = x > thr
    if above.size < 2:
        return []

    rising = np.flatnonzero((~above[:-1]) & (above[1:])) + 1
    if rising.size == 0:
        return []

    if not min_distance_s or min_distance_s <= 0:
        return rising.astype(int).tolist()

    # aplicar separación mínima en muestras
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
    channel: int,                 # único canal: análisis + trigger
    threshold: float,             # |y| > threshold -> onset
    t0: float,                    # s (puede ser <= 0)
    t1: float,                    # s (> t0)
    stim_count: Optional[int] = None,
    isi: Optional[float] = None,
) -> TrialDataset:
    """
    Corta trials en UN canal usando la propia señal como trigger.
    Devuelve TrialDataset con trials (Ns, T).
    - Sin onsets => 1 trial con toda la señal (columna única), time_rel = 0..duración.
    - Con onsets => ventana [t0, t1) relativa a cada onset; padding con ceros si recorta fuera de límites.
    """
    fs = float(ds.sampling_rate)
    C, N = ds.signals.shape
    if not (0 <= channel < C):
        raise ValueError(f"channel fuera de rango (C={C})")
    if t1 <= t0:
        raise ValueError("Se requiere t1 > t0")

    # señal (float64) sobre la que detectamos y cortamos
    y = ds.signals[channel].astype(np.float64, copy=False)

    # detectar onsets en el MISMO canal
    onsets_idx = _detect_onsets_abs(y, fs, float(threshold), isi)
    if stim_count is not None and stim_count > 0:
        onsets_idx = onsets_idx[:stim_count]

    # ventana en muestras
    n0 = int(round(t0 * fs))
    n1 = int(round(t1 * fs))
    Ns = n1 - n0
    if Ns <= 0:
        raise ValueError("Ventana inválida: (t1 - t0) * fs <= 0")

    # ========== SIN estímulos: un único trial con toda la señal ==========
    if len(onsets_idx) == 0:
        trials = y.reshape(-1, 1)  # (N, 1)
        time_rel = np.arange(y.shape[0], dtype=np.float64) / fs  # 0..duración
        dur = time_rel[-1] if time_rel.size else 0.0

        return TrialDataset(
            source=ds.source_path,
            sampling_rate=fs,
            channel_index=channel,
            channel_name=(ds.channel_names[channel] if channel < len(ds.channel_names) else f"ch{channel}"),
            unit=(ds.units[channel] if channel < len(ds.units) else ""),
            t0=0.0,
            t1=dur,
            time_rel=time_rel,
            trials=trials,
            onsets_s=[],
            isi_s=[],
            metadata={"note": "sin_estímulos → trial único con señal completa"},
        )

    # ========== CON estímulos: cortar [t0, t1) relativo al onset ==========
    T = len(onsets_idx)
    trials = np.zeros((Ns, T), dtype=np.float64)

    for t, idx in enumerate(onsets_idx):
        a = idx + n0
        b = idx + n1

        # evita pisar el siguiente onset
        if t + 1 < T:
            b = min(b, onsets_idx[t + 1])

        a_clip = max(a, 0)
        b_clip = min(b, N)
        if b_clip > a_clip:
            seg = y[a_clip:b_clip]
            start = a_clip - a  # si a<0, empieza más adelante (padding a izquierda)
            trials[start:start + seg.shape[0], t] = seg

    # eje temporal relativo (en s) de t0..t1
    time_rel = (np.arange(n0, n1, dtype=np.int64) / fs).astype(np.float64)
    onsets_s = [i / fs for i in onsets_idx]
    isi_s = (np.diff(onsets_s).tolist() if len(onsets_s) > 1 else [])

    return TrialDataset(
        source=ds.source_path,
        sampling_rate=fs,
        channel_index=channel,
        channel_name=(ds.channel_names[channel] if channel < len(ds.channel_names) else f"ch{channel}"),
        unit=(ds.units[channel] if channel < len(ds.units) else ""),
        t0=float(t0),
        t1=float(t1),
        time_rel=time_rel,
        trials=trials,
        onsets_s=onsets_s,
        isi_s=isi_s,
        metadata={},
    )
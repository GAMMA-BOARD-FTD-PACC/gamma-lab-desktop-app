from typing import List, Optional, Literal
import math
import numpy as np
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

EndMode = Literal["fixed", "until_next_onset"]


def _detect_onsets_abs(
    signal: np.ndarray,
    threshold: float,
    *,
    fs: float,
    min_distance_s: Optional[float] = None,  # ← antirrebote (si None, no filtra)
    debug: bool = True
) -> List[int]:
    """
    Detecta onsets (flancos ascendentes) donde |signal| pasa de <= umbral a > umbral.
    Si 'min_distance_s' está definido, aplica antirrebote: descarta onsets a menos de
    'min_distance_s' del último onset aceptado.
    Devuelve índices de muestra (enteros).
    """
    x = np.abs(signal.astype(np.float64, copy=False))
    thr = float(threshold)

    above = x > thr
    if above.size < 2:
        if debug:
            print("[Onsets] Señal muy corta (<2 muestras). No hay onsets.")
        return []

    # flancos ascendentes
    rising = (np.flatnonzero((~above[:-1]) & (above[1:])) + 1).astype(int)

    if min_distance_s is None or min_distance_s <= 0:
        if debug:
            print(f"[Onsets] Umbral={thr} → onsets K={rising.size} (SIN antirrebote)")
            if rising.size:
                print(f"[Onsets] Primeros onsets (muestras): {rising[:10].tolist()}")
        return rising.tolist()

    # antirrebote
    min_dist = int(round(min_distance_s * fs))
    picked: List[int] = []
    last = -10**12
    for idx in rising:
        if idx - last >= min_dist:
            picked.append(int(idx))
            last = int(idx)
        else:
            if debug:
                dt = (idx - last) / fs
                print(f"[Onsets] descartado {idx} (Δt={dt:.6f}s < {min_distance_s}s)")

    if debug:
        print(f"[Onsets] Umbral={thr}, min_dist={min_dist} muestras ({min_distance_s}s) → K final={len(picked)}")
        if picked:
            print(f"[Onsets] Primeros onsets aceptados (muestras): {picked[:10]}")
    return picked


def cut_trials_single_channel(
    ds: SignalDataset,
    channel: int,
    threshold: float,
    t0: float,
    t1: float,
    stim_expected: Optional[int] = None,
    isi: Optional[float] = None,
    end_mode: EndMode = "fixed",
    trigger_channel: Optional[int] = None,
    pad_value: float = np.nan,
    *,
    debounce_s: Optional[float] = None,
    include_leading_segment: bool = True,   # ← NUEVO: incluir tramo [inicio → primer onset)
    debug: bool = True
) -> TrialDataset:
    fs = float(ds.sampling_rate)
    C, N = ds.signals.shape
    if not (0 <= channel < C): raise ValueError(f"channel fuera de rango (C={C})")
    trig_ch = channel if trigger_channel is None else trigger_channel
    if not (0 <= trig_ch < C): raise ValueError(f"trigger_channel fuera de rango (C={C})")

    y_trig = ds.signals[trig_ch].astype(np.float64, copy=False)
    y = ds.signals[channel].astype(np.float64, copy=False)

    if debounce_s is None:
        debounce_s = 0.25 if (stim_expected is None or stim_expected == 1) else 0.01

    if debug:
        print(f"\n[TRIALS] ==== INICIO ====")
        print(f"[TRIALS] fs={fs}Hz, N={N}, channel={channel}, trigger_channel={trig_ch}, "
              f"threshold={threshold}, t0={t0}, t1={t1}, end_mode='{end_mode}', "
              f"stim_expected={stim_expected}, isi={isi}, pad={pad_value}, "
              f"debounce_s={debounce_s}, include_leading_segment={include_leading_segment}")

    # 1) onsets con antirrebote
    onsets_all = _detect_onsets_abs(y_trig, float(threshold), fs=fs,
                                    min_distance_s=debounce_s, debug=debug)

    # --- NUEVO: onset sintético en 0 para capturar el tramo inicial ---
    prepended_zero = False
    if include_leading_segment and (len(onsets_all) == 0 or onsets_all[0] > 0):
        onsets_all = [0] + onsets_all
        prepended_zero = True
        if debug:
            print("[TRIALS] (leading) Agregado onset sintético en 0 para cubrir el inicio de la señal.")

    K = len(onsets_all)
    if debug:
        print(f"[TRIALS] onsets totales (incluyendo sintético si aplica): {K}")
        if K:
            print("[TRIALS] Tiempos primeros onsets (s):",
                  [round(i/fs, 6) for i in onsets_all[:10]])

    # Caso sin onsets (solo podría ocurrir si N<2 y include_leading_segment=False)
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
            metadata={"end_mode": end_mode, "stim_per_trial": int(stim_expected or 1),
                      "stim_detected": 0, "trials_built": 1,
                      "trigger_channel": int(trig_ch),
                      "debounce_s": float(debounce_s) if debounce_s is not None else None,
                      "leading_segment_included": False,
                      "note": "sin_estímulos"},
        )

    # 2) Agrupación por 'stim_expected' (no se descartan remanentes)
    stim_per_trial = 1 if (stim_expected is None or stim_expected <= 0) else int(stim_expected)
    T = int(math.ceil(K / stim_per_trial))
    group_starts = [i * stim_per_trial for i in range(T)]
    first_onsets = [onsets_all[s] for s in group_starts]

    if debug:
        print(f"[GROUP] stim_per_trial={stim_per_trial} → grupos(T)={T}")
        for g in range(min(T, 10)):
            a_idx = group_starts[g]
            a_on  = onsets_all[a_idx]
            last  = min(a_idx + stim_per_trial, K) - 1
            b_on  = onsets_all[last]
            print(f"  - Grupo {g}: [{a_idx}:{last}] first={a_on/fs:.6f}s, last={b_on/fs:.6f}s")

    # 3) Construcción
    if end_mode == "until_next_onset":
        n0 = int(round(t0 * fs))
        lengths = []
        for g in range(T):
            start_idx = group_starts[g]
            a_onset = onsets_all[start_idx]
            next_group_start = start_idx + stim_per_trial
            b_onset = onsets_all[next_group_start] if next_group_start < K else N
            lengths.append(max(0, b_onset - (a_onset + n0)))

        Ns = max(lengths) if lengths else 1
        Ns = max(Ns, 1)
        trials = np.full((Ns, T), pad_value, dtype=np.float64)

        if debug:
            print(f"[MODE until_next_onset] n0={n0} ({n0/fs:.6f}s), Ns(max)={Ns}")
        for tcol, start_idx in enumerate(group_starts):
            a_onset = onsets_all[start_idx]
            next_group_start = start_idx + stim_per_trial
            b_onset = onsets_all[next_group_start] if next_group_start < K else N
            a = a_onset + n0; b = b_onset
            a_clip = max(a, 0); b_clip = min(b, N)
            if b_clip > a_clip:
                seg = y[a_clip:b_clip]
                start = a_clip - a
                trials[start:start + seg.shape[0], tcol] = seg
            if debug:
                print(f"  [col {tcol}] a_on={a_onset/fs:.6f}s → clip [{a_clip},{b_clip}) len={max(0,b_clip-a_clip)}")

        time_rel = (np.arange(n0, n0 + Ns, dtype=np.int64) / fs).astype(np.float64)
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    else:  # fixed
        if t1 <= t0: raise ValueError("En 'fixed' se requiere t1 > t0.")
        n0 = int(round(t0 * fs)); n1 = int(round(t1 * fs)); Ns = n1 - n0
        if Ns <= 0: raise ValueError("Ventana fija inválida: (t1 - t0) debe ser > 0.")
        trials = np.full((Ns, T), pad_value, dtype=np.float64)
        if debug:
            print(f"[MODE fixed] n0={n0}({n0/fs:.6f}s), n1={n1}({n1/fs:.6f}s), Ns={Ns}")
        for tcol, start_idx in enumerate(group_starts):
            a_onset = onsets_all[start_idx]
            a = a_onset + n0; b = a_onset + n1
            a_clip = max(a, 0); b_clip = min(b, N)
            if b_clip > a_clip:
                seg = y[a_clip:b_clip]
                start = a_clip - a
                trials[start:start + seg.shape[0], tcol] = seg
            if debug:
                print(f"  [col {tcol}] a_on={a_onset/fs:.6f}s → clip [{a_clip},{b_clip}) len={max(0,b_clip-a_clip)}")
        time_rel = (np.arange(n0, n1, dtype=np.int64) / fs).astype(np.float64)
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    if debug:
        print(f"[TRIALS] Matriz generada: {trials.shape[1]} trials × {trials.shape[0]} muestras")

    # 4) ISI y metadatos
    onsets_s_sel = [i / fs for i in first_onsets]
    isi_detail_s, isi_mean_s = [], []
    for g in range(T):
        start_idx = group_starts[g]; end_idx = min(start_idx + stim_per_trial, K)
        grp = onsets_all[start_idx:end_idx]
        if len(grp) >= 2:
            deltas_s = np.diff(np.array(grp, dtype=np.float64)) / fs
            isi_detail_s.append(deltas_s.tolist()); isi_mean_s.append(float(np.mean(deltas_s)))
        else:
            isi_detail_s.append([]); isi_mean_s.append(0.0)

    if debug:
        print(f"[ISI] isi_expected={isi}, isi_mean_por_trial (primeros 10): {isi_mean_s[:10]}")
        print("[TRIALS] ==== FIN ====\n")

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
        isi_s=isi_mean_s,
        metadata={
            "end_mode": end_mode,
            "stim_per_trial": int(stim_per_trial),
            "stim_detected": int(K),
            "trials_built": int(T),
            "trigger_channel": int(trig_ch),
            "debounce_s": float(debounce_s) if debounce_s is not None else None,
            "pad_value": float(pad_value),
            "leading_segment_included": bool(prepended_zero),  # ← marca si se agregó onset 0
            "isi_detail_s": isi_detail_s,
            "isi_expected_s": (float(isi) if isi is not None else None),
            "note": "incluye segmento inicial usando onset sintético en 0" if prepended_zero
                    else "último grupo incluido con padding si quedó incompleto",
        },
    )

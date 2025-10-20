from typing import List, Optional, Literal, Tuple
import math
import numpy as np
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

EndMode = Literal["fixed", "until_next_onset"]


# =========================
#  Onset detection helpers
# =========================

def _detect_onsets_abs(
    signal: np.ndarray,
    threshold: float,
    *,
    fs: float,
    min_distance_s: Optional[float] = None,  # antirrebote
    debug: bool = True
) -> List[int]:
    """
    Detecta flancos ascendentes donde |signal| pasa de <=threshold a >threshold.
    Si min_distance_s>0, aplica antirrebote temporal.
    Devuelve índices de muestra (ints).
    """
    x = np.abs(signal.astype(np.float64, copy=False))
    thr = float(threshold)

    above = x > thr
    if above.size < 2:
        if debug:
            print("[Onsets] Señal muy corta (<2 muestras). No hay onsets.")
        return []

    rising = (np.flatnonzero((~above[:-1]) & (above[1:])) + 1).astype(int)

    if min_distance_s is None or min_distance_s <= 0:
        if debug:
            print(f"[Onsets] Umbral={thr} → onsets K={rising.size} (SIN antirrebote)")
            if rising.size:
                print(f"[Onsets] Primeros onsets (muestras): {rising[:10].tolist()}")
        return rising.tolist()

    # Antirrebote
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


def _detect_onsets_abs_no_debounce(signal: np.ndarray, threshold: float) -> np.ndarray:
    """
    Igual que arriba pero SIN antirrebote. Útil para diagnóstico.
    Devuelve np.ndarray de int (índices).
    """
    x = np.abs(signal.astype(np.float64, copy=False))
    thr = float(threshold)
    above = x > thr
    if above.size < 2:
        return np.empty((0,), dtype=np.int64)
    rising = np.flatnonzero((~above[:-1]) & (above[1:])) + 1
    return rising.astype(np.int64)


def debug_onsets_intervals(
    ds: SignalDataset,
    channel: int,
    threshold: float,
    fs: Optional[float] = None,
    show_examples: int = 10,
    debug: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Diagnóstico: detecta TODOS los onsets crudos (sin debounce),
    calcula Δt entre onsets consecutivos y muestra estadísticas.
    Retorna (onsets_crudos, dts_en_segundos).
    """
    if fs is None:
        fs = float(ds.sampling_rate)

    y = ds.signals[channel].astype(np.float64, copy=False)

    # detección cruda
    rising = _detect_onsets_abs_no_debounce(y, threshold)
    K = rising.size

    if debug:
        print("\n[RAW] ================= ONSETS RAW =================")
        print(f"[RAW] K={K}")
        if K:
            t_first = [np.array(i/fs).astype(np.float64) for i in rising[:show_examples]]
            print(f"[RAW] primeros idx    : {rising[:show_examples].tolist()}")
            print(f"[RAW] primeros tiempos: {t_first}")

    if K < 2:
        if debug:
            print("[RAW] Muy pocos onsets para calcular Δt.")
            print("[RAW] =================================================")
        return rising, np.empty((0,), dtype=np.float64)

    dts = np.diff(rising.astype(np.int64)) / fs

    # Estadísticos y conteos
    p = np.percentile(dts, [1, 5, 50, 95, 99])
    if debug:
        print(f"[RAW] Δt stats (s)    : min={dts.min():.6f}  p1={p[0]:.6f}  p5={p[1]:.6f}  "
              f"median={p[2]:.6f}  p95={p[3]:.6f}  max={dts.max():.6f}")
        print(f"[RAW] primeros Δt (s) : {np.round(dts[:20], 4).tolist()}")

        bins = [0.001, 0.003, 0.005, 0.010, 0.015, 0.020, 0.050, 0.100, 0.200, 0.500, 1.0]
        print("\n[RAW] Conteo de Δt por rango:")
        prev = 0.0
        total = len(dts)
        for b in bins:
            cnt = np.sum((dts >= prev) & (dts < b))
            print(f"    {prev:>6.3f}s ≤ Δt < {b:>6.3f}s : {cnt:4d}  ({100.0*cnt/total:5.1f}%)")
            prev = b
        cnt = np.sum(dts >= prev)
        print(f"  Δt ≥  {prev:>6.3f}s           : {cnt:4d}  ({100.0*cnt/total:5.1f}%)")
        print("[RAW] =================================================")

    return rising, dts


# =========================
#  Assemble general (S>=2)
# =========================

def _assemble_trials_general(
    trials: np.ndarray,
    stim_per_trial: int,
    tis: float,
    fs: float,
    *,
    pad_value: float = np.nan,
    debug: bool = True
) -> np.ndarray:
    """
    Ensambla grupos de 'stim_per_trial' columnas en una sola:
      out_col = head_len (del 1er trial) + trial_2_completo + ... + trial_S_completo
    con head_len = floor(tis * fs).
    Se conservan sólo grupos completos: G = floor(T_raw / stim_per_trial).

    trials: (Ns_in, T_raw)
    return: (Ns_out, G) con Ns_out = head_len + (S-1)*Ns_in
    """
    Ns_in, T_raw = trials.shape
    if stim_per_trial <= 1 or T_raw == 0:
        if debug:
            print("[ASSEMBLE] nada que hacer: stim_per_trial <= 1 o T_raw=0")
        return trials

    head_len = int(np.floor(tis * fs))
    head_len = max(0, min(head_len, Ns_in))  # clamp

    G = T_raw // stim_per_trial
    if G == 0:
        if debug:
            print("[ASSEMBLE] no hay grupos completos para ensamblar")
        return trials

    Ns_out = head_len + (stim_per_trial - 1) * Ns_in
    out = np.full((Ns_out, G), pad_value, dtype=np.float64)

    if debug:
        print(f"[ASSEMBLE] T_raw={T_raw}, S={stim_per_trial}, G={G}, "
              f"head_len={head_len}, Ns_in={Ns_in}, Ns_out={Ns_out}")

    for g in range(G):
        c0 = g * stim_per_trial
        # head del primer trial
        if head_len > 0:
            out[:head_len, g] = trials[:head_len, c0]
        # trials 2..S completos
        write = head_len
        for k in range(1, stim_per_trial):
            ck = c0 + k
            seg = trials[:, ck]
            out[write:write + Ns_in, g] = seg
            write += Ns_in

    if debug:
        print(f"[ASSEMBLE] out shape {out.shape[1]}×{out.shape[0]} (T×Ns)")
    return out


# =========================
#  Main function
# =========================

def cut_trials_single_channel(
    ds: SignalDataset,
    channel: int,
    threshold: float,
    t0: float,
    t1: float,
    stim_expected: Optional[int] = None,
    inter_stim_time: Optional[float] = None,
    end_mode: EndMode = "fixed",
    trigger_channel: Optional[int] = None,
    pad_value: float = np.nan,
    *,
    debounce_s: Optional[float] = None,
    debug: bool = True,
    # activar diagnóstico RAW (sin debounce)
    diag_print_raw_onsets: bool = True
) -> TrialDataset:
    """
    Corta trials con |y|>threshold como trigger.
      - 'fixed': ventana [t0, t1) respecto al PRIMER onset de cada grupo.
      - 'until_next_onset': desde (first_onset + t0) hasta el primer onset del siguiente grupo.
    Luego, si S=stim_expected>=2 y tis>0, ensambla S columnas por grupo estilo MATLAB.
    """
    fs = float(ds.sampling_rate)
    C, N = ds.signals.shape
    if not (0 <= channel < C): raise ValueError(f"channel fuera de rango (C={C})")
    trig_ch = channel if trigger_channel is None else trigger_channel
    if not (0 <= trig_ch < C): raise ValueError(f"trigger_channel fuera de rango (C={C})")

    y_trig = ds.signals[trig_ch].astype(np.float64, copy=False)
    y = ds.signals[channel].astype(np.float64, copy=False)

    # antirrebote por defecto (si S>1, hacerlo pequeño pero consistente con ISI)
    if debounce_s is None:
        # si esperamos múltiples estímulos, usar algo < ISI; por ejemplo 0.03 s si ISI≈0.1 s
        if (stim_expected is not None and stim_expected > 1) and (inter_stim_time is not None and inter_stim_time > 0):
            debounce_s = min(0.03, 0.3 * inter_stim_time)
        else:
            debounce_s = 0.25

    if debug:
        print(f"\n[TRIALS] ==== INICIO ====")
        print(f"[TRIALS] fs={fs}Hz, N={N}, channel={channel}, trigger_channel={trig_ch}, "
              f"threshold={threshold}, t0={t0}, t1={t1}, end_mode='{end_mode}', "
              f"stim_expected={stim_expected}, isi={inter_stim_time}, pad={pad_value}, debounce_s={debounce_s}")

    # 0) Diagnóstico RAW (sin debounce)
    if diag_print_raw_onsets:
        raw_onsets, raw_dts = debug_onsets_intervals(ds, channel=trig_ch, threshold=threshold, fs=fs, debug=True)
    else:
        raw_onsets = np.array([], dtype=np.int64)

    # 1) Onsets con antirrebote clásico
    onsets_all = _detect_onsets_abs(y_trig, float(threshold), fs=fs, min_distance_s=debounce_s, debug=debug)
    K = len(onsets_all)
    if debug:
        print(f"[DEBUG] K_raw={len(raw_onsets)}  |  K_debounced={K}  |  ΔK={len(raw_onsets) - K}")
        if K:
            print(f"[DEBUG] primeros onsets (debounced) idx : {onsets_all[:10]}")
            print(f"[DEBUG] primeros onsets (debounced) time: {[np.array(i/fs).astype(np.float64) for i in onsets_all[:10]]}")

    if K == 0:
        # un solo trial con toda la señal
        trials = y.reshape(-1, 1)
        time_rel = np.arange(y.shape[0], dtype=np.float64) / fs
        dur = time_rel[-1] if time_rel.size else 0.0
        if debug:
            print("[TRIALS] K=0 → devuelvo 1 trial con la señal completa.")
        return TrialDataset(
            source=ds.source_path, sampling_rate=fs,
            channel_index=channel,
            channel_name=(ds.channel_names[channel] if channel < len(ds.channel_names) else f"ch{channel}"),
            unit=(ds.units[channel] if channel < len(ds.units) else ""),
            t0=0.0, t1=dur, time_rel=time_rel,
            trials=trials, onsets_s=[], isi_s=[],
            metadata={
                "end_mode": end_mode,
                "stim_per_trial": int(stim_expected or 1),
                "stim_detected": 0,
                "trials_built": 1,
                "trigger_channel": int(trig_ch),
                "debounce_s": float(debounce_s) if debounce_s is not None else None,
                "pad_value": float(pad_value),
                "note": "sin_estímulos",
            },
        )

    # 2) Parche: si vamos a ensamblar (S>=2 y tis>0), cortamos por onset individual
    force_per_onset_for_assemble = (
        end_mode == "until_next_onset"
        and (inter_stim_time is not None and inter_stim_time > 0)
        and (stim_expected is not None and stim_expected > 1)
    )
    stim_per_trial_for_cut = 1 if force_per_onset_for_assemble else (
        1 if (stim_expected is None or stim_expected <= 0) else int(stim_expected)
    )

    # Agrupación por 'stim_per_trial_for_cut'
    T = int(math.ceil(K / stim_per_trial_for_cut))
    group_starts = [i * stim_per_trial_for_cut for i in range(T)]
    first_onsets = [onsets_all[s] for s in group_starts]

    if debug:
        print(f"[GROUP] stim_per_trial_for_cut={stim_per_trial_for_cut} → grupos(T)={T}")
        for g in range(min(T, 10)):
            a_idx = group_starts[g]
            a_on  = onsets_all[a_idx]
            last  = min(a_idx + stim_per_trial_for_cut, K) - 1
            b_on  = onsets_all[last]
            print(f"  - Grupo {g}: [{a_idx}:{last}] first={a_on/fs:.6f}s, last={b_on/fs:.6f}s")

    # 3) Construcción de matriz de trials (antes del assemble)
    if end_mode == "until_next_onset":
        n0 = int(round(t0 * fs))
        lengths = []
        for g in range(T):
            start_idx = group_starts[g]
            a_onset = onsets_all[start_idx]
            next_group_start = start_idx + stim_per_trial_for_cut
            b_onset = onsets_all[next_group_start] if next_group_start < K else N
            lengths.append(max(0, b_onset - (a_onset + n0)))

        Ns = max(lengths) if lengths else 1
        Ns = max(Ns, 1)
        trials = np.full((Ns, T), pad_value, dtype=np.float64)

        if debug:
            print(f"[MODE until_next_onset] n0={n0} ({n0/fs:.6f}s), Ns(max)={Ns}")
        for tcol, start_idx in enumerate(group_starts):
            a_onset = onsets_all[start_idx]
            next_group_start = start_idx + stim_per_trial_for_cut
            b_onset = onsets_all[next_group_start] if next_group_start < K else N
            a = a_onset + n0; b = b_onset
            a_clip = max(a, 0); b_clip = min(b, N)
            if b_clip > a_clip:
                seg = y[a_clip:b_clip]
                start = a_clip - a
                trials[start:start + seg.shape[0], tcol] = seg
            if debug:
                print(f"  [col {tcol}] a_on={a_onset/fs:.6f}s → clip [{a_clip},{b_clip}) len={max(0,b_clip-a_clip)}")

        # tiempo relativo arranca en t0 (puede ser negativo) y dura Ns muestras
        time_rel = (np.arange(Ns, dtype=np.int64) / fs).astype(np.float64) + t0
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    else:  # fixed
        if t1 <= t0:
            raise ValueError("En 'fixed' se requiere t1 > t0.")
        n0 = int(round(t0 * fs)); n1 = int(round(t1 * fs)); Ns = n1 - n0
        if Ns <= 0:
            raise ValueError("Ventana fija inválida: (t1 - t0) debe ser > 0.")
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

        time_rel = (np.arange(Ns, dtype=np.int64) / fs).astype(np.float64) + t0
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

    if debug:
        print(f"[TRIALS] Matriz generada (pre-assemble): {trials.shape[1]} trials × {trials.shape[0]} muestras")

    # 4) ISI preliminar (respecto a primeros onsets de los grupos de corte)
    onsets_s_sel = [i / fs for i in first_onsets]
    isi_detail_s, isi_mean_s = [], []
    for g in range(T):
        start_idx = group_starts[g]; end_idx = min(start_idx + stim_per_trial_for_cut, K)
        grp = onsets_all[start_idx:end_idx]
        if len(grp) >= 2:
            deltas_s = np.diff(np.array(grp, dtype=np.float64)) / fs
            isi_detail_s.append(deltas_s.tolist()); isi_mean_s.append(float(np.mean(deltas_s)))
        else:
            isi_detail_s.append([]); isi_mean_s.append(0.0)

    # 5) ENSAMBLE (si S>=2 y tis>0) → ahora S es el solicitado (stim_expected)
    if (stim_expected is not None and stim_expected >= 2) and (inter_stim_time is not None and inter_stim_time > 0):
        trials_w = _assemble_trials_general(
            trials, stim_per_trial=int(stim_expected), tis=float(inter_stim_time), fs=fs,
            pad_value=pad_value, debug=debug
        )
        trials = trials_w  # (Ns_out, G) con G=floor(T_raw/S)

        # Recalcular onsets/ISI para G grupos completos (cada grupo S onsets)
        G = (K // int(stim_expected))
        first_onsets_full = [onsets_all[g * int(stim_expected)] for g in range(G)]
        onsets_s_sel = [i / fs for i in first_onsets_full]

        isi_detail_s, isi_mean_s = [], []
        for g in range(G):
            start_idx = g * int(stim_expected)
            end_idx   = min(start_idx + int(stim_expected), K)
            grp = onsets_all[start_idx:end_idx]
            if len(grp) >= 2:
                deltas_s = np.diff(np.array(grp, dtype=np.float64)) / fs
                isi_detail_s.append(deltas_s.tolist())
                isi_mean_s.append(float(np.mean(deltas_s)))
            else:
                isi_detail_s.append([])
                isi_mean_s.append(0.0)

        # Ajustar time_rel para la nueva longitud (conservando origen en t0 relativo)
        Ns_new = trials.shape[0]
        time_rel = (np.arange(Ns_new, dtype=np.int64) / fs).astype(np.float64) + t0
        t1_report = float(time_rel[-1]) if time_rel.size else 0.0

        if debug:
            print(f"[ASSEMBLE] aplicado. Trials ahora: {trials.shape} (Ns×T)")
            print(f"[ASSEMBLE] onsets_s: {len(onsets_s_sel)} (deben coincidir con T={trials.shape[1]})")

    if debug:
        print(f"[ISI] isi_expected={inter_stim_time}, isi_mean_por_trial (primeros 10): {isi_mean_s[:10]}")
        print("[TRIALS] ==== FIN ====\n")

    # Validación: onsets_s coincide con T o se deja vacío (evitar crash aguas arriba)
    if len(onsets_s_sel) not in (0, trials.shape[1]):
        if debug:
            print(f"[WARN] onsets_s (len={len(onsets_s_sel)}) != T ({trials.shape[1]}). Se deja vacío para coherencia.")
        onsets_s_sel = []

    # 6) TrialDataset final
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
            "stim_per_trial": int(stim_expected or stim_per_trial_for_cut),
            "stim_detected": int(K),
            "trials_built": int(trials.shape[1]),
            "trigger_channel": int(trig_ch),
            "debounce_s": float(debounce_s) if debounce_s is not None else None,
            "pad_value": float(pad_value),
            "isi_detail_s": isi_detail_s,
            "isi_expected_s": (float(inter_stim_time) if inter_stim_time is not None else None),
            "note": "assemble aplicado" if ((stim_expected or 1) >= 2 and inter_stim_time and inter_stim_time > 0)
                    else "sin assemble",
        },
    )

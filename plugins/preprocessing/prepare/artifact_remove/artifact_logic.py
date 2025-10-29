# plugins/preprocessing/prepare/artifact_remove/artifact_logic.py
from typing import List, Tuple
import numpy as np
from pathlib import Path

LOGL = "[ArtifactLogic]"

# ----------------- Helpers -----------------

def _get_active_signal_and_name(kernel):
    store = kernel.get_service("DataStore")
    if not store:
        raise RuntimeError("DataStore missing.")
    sd = store.get_active_signal()
    if sd is None:
        raise RuntimeError("No active signal.")
    # El SignalDataset usa file_name (Path(source).name) como clave
    # Intentamos tomarlo del último TD si existe; si no, del source_path.
    file_name = None
    try:
        if sd.trials_dataset:
            file_name = Path(sd.trials_dataset[-1].source).name
    except Exception:
        pass
    if not file_name:
        file_name = Path(getattr(sd, "source_path", "")).name or getattr(sd, "name", None)
    if not file_name:
        raise RuntimeError("Active signal has no file name.")
    return sd, file_name

def _get_current_channel_name(sd) -> str:
    """
    Canal actual:
      1) channel_name del último TrialDataset
      2) primer nombre en sd.channel_names
      3) 'ch-1' si hay señales cargadas
    """
    try:
        if sd.trials_dataset:
            ch = getattr(sd.trials_dataset[-1], "channel_name", None)
            if ch:
                return str(ch)
    except Exception:
        pass
    try:
        names = getattr(sd, "channel_names", None)
        if names and len(names) > 0:
            return str(names[0])
    except Exception:
        pass
    sig = getattr(sd, "signals", None)
    if sig is not None and getattr(sig, "shape", None) and sig.shape[0] > 0:
        return "ch-1"
    raise RuntimeError("No channel selected/found. Generate Trials first or select a channel.")

def _time_window_indices(t: np.ndarray, a: float, b: float) -> Tuple[int, int]:
    """Devuelve índices [i_a, i_b) para la ventana [a, b] (ordenando si b<a)."""
    if b < a:
        a, b = b, a
    i_a = int(np.searchsorted(t, a, side="left"))
    i_b = int(np.searchsorted(t, b, side="right"))
    i_a = max(0, min(i_a, t.shape[0]))
    i_b = max(0, min(i_b, t.shape[0]))
    return i_a, i_b

# ----------------- Lógica pública -----------------

def apply_modification_to_all_valid(kernel, *, mode: str, point_a: float, point_b: float = 0.0):
    """
    Modifica *valores* dentro de los trials ACTIVOS sin resegmentar ni descartar:
      - mode='blank'  (alias 'cut'): pone NaN en [A,B] o hasta A si no se da B.
      - mode='interpolate': interpola linealmente en [A,B].
    Lee trials activos con SignalDataset.get_active_trials(...), y escribe los cambios
    de vuelta en el TrialDataset base (sd.trials_dataset) mapeando columnas activas
    → índices originales usando sd.discarded_trials[(file_name, channel_name)].
    """
    sd, file_name = _get_active_signal_and_name(kernel)
    channel_name = _get_current_channel_name(sd)

    # 1) Leer trials ACTIVOS (filtrados por descartes) del dataset
    td_active = sd.get_active_trials(file_name, channel_name)
    if td_active is None:
        raise RuntimeError(f"No active trials for ({file_name}, {channel_name}).")

    t = np.asarray(td_active.time_rel)          # (Ns,)
    trials_active = np.asarray(td_active.trials)  # (Ns, T_act)
    if t.ndim != 1 or trials_active.ndim != 2:
        raise RuntimeError(f"Active trials missing (time_rel or trials).")
    Ns, T_act = trials_active.shape
    if T_act == 0:
        return None

    # 2) Encontrar el TrialDataset BASE (sin filtrar) para este file+channel
    td_base = next(
        (tdb for tdb in getattr(sd, "trials_dataset", [])
         if Path(tdb.source).name == file_name and tdb.channel_name == channel_name),
        None
    )
    if td_base is None:
        raise RuntimeError(f"No base TrialDataset found for ({file_name}, {channel_name}).")
    if td_base.trials.shape[0] != Ns:
        raise RuntimeError(f"Shape mismatch: base Ns={td_base.trials.shape[0]} vs active Ns={Ns}.")

    # 3) Construir el mapeo índices ACTIVOS → ORIGINALES usando discarded_trials
    discarded = sd.discarded_trials.get((file_name, channel_name), set()) or set()
    T_total = td_base.trials.shape[1]
    orig_indices = [i for i in range(T_total) if i not in discarded]
    if len(orig_indices) != T_act:
        # Por seguridad (si alguien cambió descartes en caliente)
        T_act = min(T_act, len(orig_indices))
        trials_active = trials_active[:, :T_act]
        orig_indices = orig_indices[:T_act]

    # 4) Crear una copia para modificar
    out_active = trials_active.copy()

    if mode in ("blank", "cut"):
        if point_b and point_b != point_a:
            i_a, i_b = _time_window_indices(t, point_a, point_b)
            if i_b > i_a:
                out_active[i_a:i_b, :] = np.nan
            else:
                return None
        else:
            # blank until A
            i_a = int(np.searchsorted(t, point_a, side="left"))
            i_a = max(0, min(i_a, Ns))
            if i_a > 0:
                out_active[:i_a, :] = np.nan
            else:
                return None

    elif mode == "interpolate":
        if point_a == point_b:
            raise ValueError("Points A and B cannot be the same for interpolation.")
        i_a, i_b = _time_window_indices(t, point_a, point_b)
        if i_b - i_a < 2:
            return None
        for j in range(T_act):
            y = out_active[:, j]
            valid = np.isfinite(y)
            if valid.sum() < 2:
                continue
            ya = np.interp(t[i_a], t[valid], y[valid])
            yb = np.interp(t[i_b-1], t[valid], y[valid])
            r = np.linspace(0.0, 1.0, i_b - i_a)
            y[i_a:i_b] = ya + (yb - ya) * r
            out_active[:, j] = y
    else:
        raise ValueError(f"Unknown mode: {mode}")

    # 5) Escribir los cambios en el TrialDataset BASE (por columnas mapeadas)
    for k, orig_col in enumerate(orig_indices):
        if 0 <= orig_col < td_base.trials.shape[1]:
            td_base.trials[:, orig_col] = out_active[:, k]

    # 6) Marcar metadata de modificados (opcional)
    try:
        mods = td_base.metadata.get("modified_trials", set())
        mods = set(mods)
        mods.update(orig_indices)
        td_base.metadata["modified_trials"] = mods
    except Exception:
        td_base.metadata = getattr(td_base, "metadata", {}) or {}
        td_base.metadata["modified_trials"] = set(orig_indices)

    # 7) Notificar a la UI (si el pipeline lo usa)
    if hasattr(kernel, "event"):
        try:
            kernel.event.emit("trials_generated", {"signal": file_name, "channel": channel_name})
        except Exception:
            pass

    print(f"{LOGL} Mode='{mode}' applied to {len(orig_indices)} active trials on ({file_name}, {channel_name}).")
    return True

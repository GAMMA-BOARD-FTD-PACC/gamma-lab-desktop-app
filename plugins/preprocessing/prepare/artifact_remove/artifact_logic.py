# plugins/preprocessing/prepare/artifact_remove/artifact_logic.py
import numpy as np
from typing import Optional, List, Tuple
from core.services.data_store import DataStore
from core.services.trial_dataset import TrialDataset

LOGL = "[ArtifactLogic]"

def _clip(i: int, n: int) -> int:
    """Asegura que un índice esté dentro de los límites [0, n-1] de un array."""
    return max(0, min(int(i), n - 1))

def _time_to_index(time_vec: np.ndarray, time_point_s: float) -> int:
    """Convierte un punto en el tiempo (segundos) a su índice de muestra más cercano."""
    return np.searchsorted(time_vec, time_point_s, side='left')

def process_cut_from_start(trials_matrix: np.ndarray, time_rel: np.ndarray, cut_point_s: float) -> Tuple[np.ndarray, np.ndarray]:
    """Corta los trials desde el inicio hasta el punto especificado."""
    cut_index = _time_to_index(time_rel, cut_point_s)
    new_trials = trials_matrix[cut_index:, :]
    new_time = time_rel[cut_index:]
    return new_trials, new_time

def process_interpolate_interval(trials_matrix: np.ndarray, time_rel: np.ndarray, interval_s: Tuple[float, float]):
    """Interpola un intervalo en la matriz de trials, modificando la matriz directamente."""
    t_start, t_end = min(interval_s), max(interval_s)
    i_start = _time_to_index(time_rel, t_start)
    i_end = _time_to_index(time_rel, t_end)
    start, end = _clip(i_start, trials_matrix.shape[0]), _clip(i_end, trials_matrix.shape[0])
    
    if start >= end: return

    for trial_idx in range(trials_matrix.shape[1]):
        y_start = trials_matrix[start - 1, trial_idx] if start > 0 else trials_matrix[start, trial_idx]
        y_end = trials_matrix[end, trial_idx] if end < trials_matrix.shape[0] - 1 else trials_matrix[end - 1, trial_idx]
        num_points = end - start
        if num_points > 0:
            line = np.linspace(y_start, y_end, num_points)
            trials_matrix[start:end, trial_idx] = line

# --- FUNCIÓN PRINCIPAL CORREGIDA ---
def apply_artifact_modification(kernel, *, mode: str, point_a: float, point_b: float = 0.0) -> TrialDataset:
    store: Optional[DataStore] = kernel.get_service("DataStore")
    if not store: raise RuntimeError("Servicio DataStore no encontrado.")
    
    active_signal = store.get_active_signal()
    if not active_signal or not active_signal.trials_dataset:
        raise RuntimeError("No se encontró un TrialDataset en la señal activa.")

    base_td = active_signal.trials_dataset[-1]
    trials_matrix, time_rel = np.copy(base_td.trials), np.copy(base_td.time_rel)
    metadata_update = {}

    if mode == 'cut':
        trials_matrix, time_rel = process_cut_from_start(trials_matrix, time_rel, point_a)
        metadata_update = {"artifact_cut_until": point_a}
    elif mode == 'interpolate':
        process_interpolate_interval(trials_matrix, time_rel, (point_a, point_b))
        metadata_update = {"artifact_interpolated": (point_a, point_b)}
    else:
        raise ValueError(f"Modo '{mode}' no reconocido.")

    cleaned_td = TrialDataset(
        source=base_td.source, sampling_rate=base_td.sampling_rate, channel_index=base_td.channel_index,
        channel_name=base_td.channel_name, unit=base_td.unit, t0=time_rel[0] if len(time_rel) > 0 else base_td.t0,
        t1=time_rel[-1] if len(time_rel) > 0 else base_td.t1, time_rel=time_rel, trials=trials_matrix,
        onsets_s=base_td.onsets_s, metadata={**(base_td.metadata or {}), **metadata_update}
    )
    
    # --- ¡ESTA ES LA CORRECCIÓN CLAVE! ---
    # 1. Reemplazamos el TrialDataset viejo por el nuevo DENTRO de la señal activa.
    active_signal.trials_dataset[-1] = cleaned_td
    
    # 2. Guardamos el resultado bajo la clave 'raw_clean' para que pueda ser usado por otros plugins.
    #    NO se toca 'active_signal' directamente.
    store.set("raw_clean", active_signal) 
    
    return cleaned_td
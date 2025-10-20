# plugins/preprocessing/prepare/artifact_remove/artifact_logic.py
import numpy as np
from typing import Optional, Tuple
from pathlib import Path

from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

LOGL = "[ArtifactLogic]"

# --- Funciones Auxiliares Puras ---

def _clip(i: int, n: int) -> int:
    """Asegura que un índice esté dentro de los límites [0, n-1] de un array."""
    return max(0, min(int(i), n - 1))

def _time_to_index(time_vec: np.ndarray, time_point_s: float) -> int:
    """Convierte un punto en el tiempo (segundos) a su índice de muestra más cercano."""
    return np.searchsorted(time_vec, time_point_s, side='left')

# --- Lógicas de Procesamiento ---

def process_modification(
    trials_matrix: np.ndarray,
    time_rel: np.ndarray,
    mode: str,
    point_a: float,
    point_b: float,
    target_original_index: int
) -> np.ndarray:
    """Aplica una modificación (corte o interpolación) a un solo trial en una copia de la matriz."""
    modified_trials = trials_matrix.copy()
    
    # Validar que el índice del trial es correcto
    if not (0 <= target_original_index < modified_trials.shape[1]):
        print(f"{LOGL} ADVERTENCIA: Índice de trial {target_original_index} fuera de rango. No se hace nada.")
        return modified_trials

    if mode == 'interpolate':
        t_start, t_end = min((point_a, point_b)), max((point_a, point_b))
        i_start = _time_to_index(time_rel, t_start)
        i_end = _time_to_index(time_rel, t_end)
        start, end = _clip(i_start, modified_trials.shape[0]), _clip(i_end, modified_trials.shape[0])

        if start < end:
            y_start = modified_trials[start - 1, target_original_index] if start > 0 else modified_trials[start, target_original_index]
            y_end = modified_trials[end, target_original_index] if end < modified_trials.shape[0] - 1 else modified_trials[end - 1, target_original_index]
            num_points = end - start
            if num_points > 0:
                line = np.linspace(y_start, y_end, num_points)
                modified_trials[start:end, target_original_index] = line
                print(f"{LOGL} Interpolado trial {target_original_index} en [{t_start:.4f}s - {t_end:.4f}s].")

    elif mode == 'cut':
        cut_index = _time_to_index(time_rel, point_a)
        print(f"{LOGL} Cortando (con NaN) trial {target_original_index} hasta {point_a:.4f}s.")
        # Rellena el inicio del trial con NaN (Not a Number) para "borrarlo"
        modified_trials[:cut_index, target_original_index] = np.nan
            
    return modified_trials

# --- FUNCIÓN PRINCIPAL ---

def apply_artifact_modification(
    kernel, *, mode: str, point_a: float, point_b: float = 0.0,
    target_original_index: Optional[int]
) -> Optional[TrialDataset]:
    """Orquesta la remoción de artefactos en un SOLO trial, creando un nuevo TrialDataset."""
    if target_original_index is None:
        # Esta comprobación es una seguridad extra. El plugin UI ya no debería permitir esto.
        raise ValueError("target_original_index no puede ser None. Se debe especificar un trial.")

    store: Optional[DataStore] = kernel.get_service("DataStore")
    if not store: raise RuntimeError("Servicio DataStore no encontrado.")
    
    active_signal: Optional[SignalDataset] = store.get_active_signal()
    if not active_signal or not active_signal.trials_dataset:
        raise RuntimeError("No se encontró un TrialDataset en la señal activa.")

    base_td = active_signal.trials_dataset[-1]
    
    new_trials_matrix = process_modification(
        trials_matrix=base_td.trials,
        time_rel=base_td.time_rel,
        mode=mode,
        point_a=point_a,
        point_b=point_b,
        target_original_index=target_original_index
    )

    # Actualiza los metadatos
    new_metadata = (base_td.metadata or {}).copy()
    if "modified_trials" not in new_metadata:
        new_metadata["modified_trials"] = set()
    new_metadata["modified_trials"].add(target_original_index)
        
    # Crea un nuevo dataset con los datos modificados
    cleaned_td = TrialDataset(
        source=base_td.source, sampling_rate=base_td.sampling_rate,
        channel_index=base_td.channel_index, channel_name=base_td.channel_name,
        unit=base_td.unit, t0=base_td.t0, t1=base_td.t1, time_rel=base_td.time_rel.copy(),
        trials=new_trials_matrix, onsets_s=base_td.onsets_s, metadata=new_metadata
    )
    
    # Reemplazar el estado es la clave para la actualización instantánea
    active_signal.trials_dataset[-1] = cleaned_td
    
    active_signal_key = store.get_active_signal_key()
    print(f"{LOGL} TrialDataset actualizado en la señal activa '{Path(active_signal_key).name}'.")
    
    return cleaned_td
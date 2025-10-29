# Ubicación: plugins/preprocessing/prepare/artifact_remove/artifact_logic.py
import numpy as np
from typing import Optional, Tuple, Set
from pathlib import Path
import math # Needed for ceiling function if using assemble logic elsewhere

from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset
# --- AÑADIDO: Importar funciones de detección de onsets si son necesarias ---
# from core.analysis.prepare import _detect_onsets_abs, debug_onsets_intervals, _assemble_trials_general, EndMode

LOGL = "[ArtifactLogic]"

# --- Funciones Auxiliares Puras ---

def _clip(i: int, n: int) -> int:
    """Asegura que un índice esté dentro de los límites [0, n-1] de un array."""
    return max(0, min(int(i), n - 1))

def _time_to_index(time_vec: np.ndarray, time_point_s: float) -> int:
    """Convierte un punto en el tiempo (segundos) a su índice de muestra más cercano."""
    # Usar np.argmin para encontrar el índice del tiempo más cercano
    # Es más robusto que searchsorted si time_vec no es perfectamente monotónico
    if time_vec is None or time_vec.size == 0:
         return 0
    return np.argmin(np.abs(time_vec - time_point_s))

# --- Lógica de Modificación (Aplicada a UN trial) ---
# Esta función ahora es un helper interno
def _apply_modification_single_trial(
    trial_data: np.ndarray, # Vector 1D de un solo trial
    time_rel: np.ndarray,
    mode: str,
    point_a: float,
    point_b: float
) -> Tuple[np.ndarray, bool]:
    """
    Aplica corte o interpolación a una COPIA de un vector de trial 1D.
    Devuelve el trial modificado y un booleano indicando si se hizo algún cambio.
    """
    modified_trial = trial_data.copy()
    num_samples = modified_trial.shape[0]
    changed = False

    if mode == 'interpolate':
        t_start, t_end = min((point_a, point_b)), max((point_a, point_b))
        i_start = _time_to_index(time_rel, t_start)
        i_end = _time_to_index(time_rel, t_end)
        start, end = _clip(i_start, num_samples), _clip(i_end, num_samples)

        # Asegurarse de que start sea estrictamente menor que end para interpolar
        if start < end:
            # Encontrar valores válidos antes y después del segmento a interpolar
            y_start = np.nan
            idx_before = start - 1
            while idx_before >= 0 and np.isnan(modified_trial[idx_before]):
                idx_before -= 1
            if idx_before >= 0:
                y_start = modified_trial[idx_before]
            else: # Si no hay valor antes, usar el primer valor después
                 idx_after_start = start
                 while idx_after_start < end and np.isnan(modified_trial[idx_after_start]):
                      idx_after_start += 1
                 if idx_after_start < end:
                      y_start = modified_trial[idx_after_start]
                 # Si todo el inicio es NaN, y_start quedará NaN (interpolará a NaN)


            y_end = np.nan
            idx_after = end # Empezar justo en el índice final
            while idx_after < num_samples and np.isnan(modified_trial[idx_after]):
                idx_after += 1
            if idx_after < num_samples:
                y_end = modified_trial[idx_after]
            else: # Si no hay valor después, usar el último valor antes del final
                 idx_before_end = end - 1
                 while idx_before_end > start and np.isnan(modified_trial[idx_before_end]):
                      idx_before_end -= 1
                 if idx_before_end > start:
                      y_end = modified_trial[idx_before_end]
                 # Si todo el final es NaN, y_end quedará NaN

            # Interpolar solo si tenemos puntos de inicio y fin válidos
            if not np.isnan(y_start) and not np.isnan(y_end):
                 num_points_to_interpolate = end - start
                 if num_points_to_interpolate > 0:
                      line = np.linspace(y_start, y_end, num_points_to_interpolate)
                      modified_trial[start:end] = line
                      # print(f"    Interpolado muestras [{start}-{end}) con [{y_start:.2f} - {y_end:.2f}]")
                      changed = True
            elif np.isnan(y_start) and not np.isnan(y_end): # Si solo el inicio es NaN, rellenar con y_end
                 modified_trial[start:end] = y_end
                 changed = True
            elif not np.isnan(y_start) and np.isnan(y_end): # Si solo el fin es NaN, rellenar con y_start
                 modified_trial[start:end] = y_start
                 changed = True
            # Si ambos son NaN, el segmento se queda como NaN o como estaba
            # else: print(f"    No se pudo interpolar [{start}-{end}), ambos bordes son NaN")

    elif mode == 'cut':
        cut_index = _time_to_index(time_rel, point_a)
        idx_to_cut = _clip(cut_index, num_samples)
        # print(f"    Cortando (NaN) hasta índice {idx_to_cut} ({point_a:.4f}s)")
        if idx_to_cut > 0:
            # Rellenar con NaN solo si no está ya lleno de NaN
            if not np.all(np.isnan(modified_trial[:idx_to_cut])):
                 modified_trial[:idx_to_cut] = np.nan
                 changed = True

    return modified_trial, changed


# --- NUEVA FUNCIÓN PRINCIPAL ---
def apply_modification_to_all_valid(
    kernel, *, mode: str, point_a: float, point_b: float = 0.0
) -> Optional[TrialDataset]:
    """
    Aplica una modificación (corte o interpolación) a TODOS los trials válidos
    basándose en los puntos A y B definidos (probablemente desde la vista promedio).
    Crea un único y nuevo TrialDataset actualizado.
    """
    store: Optional[DataStore] = kernel.get_service("DataStore")
    if not store: raise RuntimeError("Servicio DataStore no encontrado.")

    active_signal: Optional[SignalDataset] = store.get_active_signal()
    if not active_signal or not active_signal.trials_dataset:
        raise RuntimeError("No se encontró un TrialDataset en la señal activa.")

    # Usar el último TrialDataset como base
    base_td = active_signal.trials_dataset[-1]
    original_trials_matrix = base_td.trials
    time_rel = base_td.time_rel
    n_samples, n_total_trials = original_trials_matrix.shape

    # Obtener índices descartados para este canal específico
    active_signal_key = store.get_active_signal_key()
    file_name = Path(active_signal_key).name if active_signal_key else "unknown"
    # Usar la fuente del base_td por si la key del store es diferente
    source_file_name = Path(base_td.source).name if base_td.source else file_name
    discard_key = (source_file_name, base_td.channel_name)
    discarded_indices: Set[int] = active_signal.discarded_trials.get(discard_key, set())

    print(f"{LOGL} Aplicando modo '{mode}' a todos los trials válidos. Puntos: A={point_a:.4f}s, B={point_b:.4f}s.")
    print(f"{LOGL} Total trials originales: {n_total_trials}. Descartados: {len(discarded_indices)}.")

    # Crear una copia de la matriz para modificarla
    new_trials_matrix = original_trials_matrix.copy()
    indices_actually_modified: Set[int] = set()

    # Iterar sobre TODOS los índices originales
    for original_index in range(n_total_trials):
        # Omitir los trials que ya están marcados como descartados
        if original_index in discarded_indices:
            # print(f"    Omitiendo trial {original_index} (descartado).")
            continue

        # Extraer el trial actual (importante: es una vista, no copia inicial)
        current_trial_data = new_trials_matrix[:, original_index]

        # Aplicar la modificación a este trial individual
        modified_trial, changed = _apply_modification_single_trial(
            current_trial_data, time_rel, mode, point_a, point_b
        )

        # Si hubo cambios, actualizar la matriz y registrar el índice
        if changed:
            new_trials_matrix[:, original_index] = modified_trial
            indices_actually_modified.add(original_index)

    if not indices_actually_modified:
        print(f"{LOGL} No se realizaron modificaciones en ningún trial válido.")
        # Devolver None indica que no hubo cambios efectivos
        return None

    print(f"{LOGL} Modificados {len(indices_actually_modified)} trials válidos.")

    # Actualizar los metadatos: añadir los nuevos índices modificados
    new_metadata = (base_td.metadata or {}).copy()
    # Asegurarse que 'modified_trials' sea un set
    existing_modified = new_metadata.get("modified_trials", set())
    if not isinstance(existing_modified, set): # Convertir si no es un set
        try: existing_modified = set(existing_modified)
        except TypeError: existing_modified = set()

    # Unir los índices modificados previamente con los nuevos
    new_metadata["modified_trials"] = existing_modified.union(indices_actually_modified)
    # Añadir nota sobre la operación
    new_metadata["last_artifact_op"] = f"Mode: {mode}, Points: ({point_a:.4f}, {point_b:.4f}), Applied to {len(indices_actually_modified)} trials"


    # Crear un nuevo dataset con la matriz de trials completamente actualizada
    cleaned_td = TrialDataset(
        source=base_td.source, sampling_rate=base_td.sampling_rate,
        channel_index=base_td.channel_index, channel_name=base_td.channel_name,
        unit=base_td.unit, t0=base_td.t0, t1=base_td.t1, time_rel=time_rel.copy(), # Copiar time_rel por seguridad
        trials=new_trials_matrix, # La matriz con todas las modificaciones
        onsets_s=base_td.onsets_s, # Los onsets originales no cambian
        metadata=new_metadata # Los metadatos actualizados
    )

    # Reemplazar el último TrialDataset en la señal activa
    # Esto asegura que la próxima vez que se lean los trials, se obtengan los actualizados
    active_signal.trials_dataset[-1] = cleaned_td

    print(f"{LOGL} TrialDataset actualizado en la señal activa '{source_file_name}' -> '{base_td.channel_name}'.")
    # Emitir evento para que otras partes de la UI (como el propio plugin) se actualicen
    # Usar la key correcta de la señal activa del store
    event_payload = {"key": active_signal_key if active_signal_key else base_td.source}
    kernel.event.emit("trials_generated", event_payload) # Reutilizar evento existente

    return cleaned_td
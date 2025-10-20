from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any
import numpy as np

from core.services.trial_dataset import TrialDataset


'''
    En esta clase se guardan los datos puros transformados directamente de los archicos leídos
    Es el formato general de señal cruda.
    Contiene los metadatos como los datos generales de la señal. 
'''
@dataclass
class SignalDataset:
    name: str
    format: str                     # "abf"
    source_path: str
    sampling_rate: float            
    time: np.ndarray                
    signals: np.ndarray             
    channel_names: List[str]
    units: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    vtk_table = None

    trials_dataset:List[TrialDataset] = field(default_factory=list)

    discarded_trials: Dict[tuple[str, str], set[int]] = field(default_factory=dict)

    #Agregar un trial_dataset a la lista de trials dataset
    def add_trial_dataset(self, trial: "TrialDataset"):
        if not isinstance(trial, TrialDataset):
            raise ValueError("trial debe ser de tipo TrialDataset")
        self.trials_dataset.append(trial)

    def get_active_trials(self, file_name: str, channel_name: str):
        """
        Retorna el TrialDataset activo para un archivo y canal específicos,
        aplicando los descartes definidos en self.discarded_trials.

        Parámetros:
            name (str): Nombre del archivo origen.
            channel_name (str): Nombre del canal.

        Retorna:
            TrialDataset | None: El dataset filtrado o None si no existe.
        """
        key = (file_name, channel_name)

        # Buscar el dataset correspondiente
        td = next(
            (t for t in self.trials_dataset if Path(t.source).name == file_name and t.channel_name == channel_name),
            None
        )

        if td is None:
            print(f"[SignalDataset] No se encontró dataset para {key}")
            return None

        # Obtener los descartes específicos de ese dataset
        discarded = self.discarded_trials.get(key, set())

        # Si no hay descartes, retornar el dataset original
        if not discarded:
            return td

        Ns, T = td.trials.shape
        valid_mask = np.ones(T, dtype=bool)

        for idx in discarded:
            if 0 <= idx < T:
                valid_mask[idx] = False

        # Si todos los trials son válidos, se retorna directamente el dataset original
        if valid_mask.all():
            return td

        # Aplicar el filtro solo a los índices válidos
        filtered_trials = td.trials[:, valid_mask]
        filtered_onsets = [on for i, on in enumerate(td.onsets_s) if valid_mask[i]] if td.onsets_s else []

        # Crear una nueva instancia filtrada (sin copiar arrays innecesariamente)
        filtered_dataset = TrialDataset(
            source=td.source,
            sampling_rate=td.sampling_rate,
            channel_index=td.channel_index,
            channel_name=td.channel_name,
            unit=td.unit,
            t0=td.t0,
            t1=td.t1,
            time_rel=td.time_rel,
            trials=filtered_trials,
            onsets_s=filtered_onsets,
            isi_s=td.isi_s,
            metadata=td.metadata
        )

        return filtered_dataset

    def discard_trial(self, source: str, channel: str, index: int):
        """Descarta un trial específico del canal indicado."""
        key = (source, channel)
        self.discarded_trials.setdefault(key, set()).add(index)
        print(f"discarted trials: {self.discarded_trials}:  ")

    def include_trial(self, source: str, channel: str, index: int):
        """Vuelve a incluir un trial previamente descartado."""
        key = (source, channel)
        if key in self.discarded_trials:
            self.discarded_trials[key].discard(index)
            if not self.discarded_trials[key]:
                del self.discarded_trials[key]  # limpia entradas vacías

    def clear_discarded_trials(self):
        self.discarded_trials.clear()
    
    def is_trial_discarded(self, source: str, channel: str, index: int) -> bool:
        key = (source, channel)
        return key in self.discarded_trials and index in self.discarded_trials[key]



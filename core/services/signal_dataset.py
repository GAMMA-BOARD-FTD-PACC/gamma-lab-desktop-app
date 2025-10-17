from dataclasses import dataclass, field
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

    discarded_trials: set[int] = field(default_factory=set)

    #Agregar un trial_dataset a la lista de trials dataset
    def add_trial_dataset(self, trial: "TrialDataset"):
        if not isinstance(trial, TrialDataset):
            raise ValueError("trial debe ser de tipo TrialDataset")
        self.trials_dataset.append(trial)

    def get_active_trials(self):
        """
        Retorna los TrialDataset activos, descartando los trials marcados,
        pero sin duplicar datos innecesariamente.
        """
        # Si no hay descartes, retorna directamente la lista original
        if not self.discarded_trials:
            return self.trials_dataset

        discarded = set(self.discarded_trials)  # Conversión a set para búsqueda O(1)
        filtered_datasets = []

        for td in self.trials_dataset:
            Ns, T = td.trials.shape

            # Selecciona índices válidos (no descartados)
            valid_mask = np.ones(T, dtype=bool)
            for idx in discarded:
                if 0 <= idx < T:
                    valid_mask[idx] = False

            # Si todos los trials son válidos, reusa directamente el objeto original
            if valid_mask.all():
                filtered_datasets.append(td)
                continue

            # Crea una vista del array sin copiar datos (usa slicing con máscara)
            filtered_trials = td.trials[:, valid_mask]

            # También filtra onsets si existen
            filtered_onsets = [on for i, on in enumerate(td.onsets_s) if valid_mask[i]] if td.onsets_s else []

            # Reusa la mayoría de atributos para evitar duplicación
            filtered_datasets.append(TrialDataset(
                source=td.source,
                sampling_rate=td.sampling_rate,
                channel_index=td.channel_index,
                channel_name=td.channel_name,
                unit=td.unit,
                t0=td.t0,
                t1=td.t1,
                time_rel=td.time_rel,  # misma referencia, no copia
                trials=filtered_trials,  # vista filtrada
                onsets_s=filtered_onsets,
                isi_s=td.isi_s,
                metadata=td.metadata
            ))

        return filtered_datasets

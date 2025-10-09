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

    #Agregar un trial_dataset a la lista de trials dataset
    def add_trial_dataset(self, trial: "TrialDataset"):
        if not isinstance(trial, TrialDataset):
            raise ValueError("trial debe ser de tipo TrialDataset")
        self.trials_dataset.append(trial)               
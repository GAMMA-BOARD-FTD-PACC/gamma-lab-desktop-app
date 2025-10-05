from dataclasses import dataclass, field
from typing import List, Dict, Any
import numpy as np
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
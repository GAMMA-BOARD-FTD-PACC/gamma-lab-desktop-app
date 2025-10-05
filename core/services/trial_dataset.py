# core/services/trials_matrix.py
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np

@dataclass
class TrialDataset:
    source: str                         # archivo de origen
    sampling_rate: float                # Hz
    channel_index: int                  # índice del canal usado
    channel_name: str                   # nombre del canal
    unit: str                           # unidad del canal (ej. "uV", "mV")
    t0: float                           # s (relativo al onset)
    t1: float                           # s
    time_rel: np.ndarray                # (Ns,) eje de tiempo relativo [t0..t1)
    trials: np.ndarray                  # (Ns, T) matriz -> cada columna es un trial
    onsets_s: List[float]               # onsets en segundos (len = T)
    isi_s: List[float] = field(default_factory=list)    # tiempos inter-estímulo (opcional)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        assert self.trials.ndim == 2, "trials debe ser 2D (Ns, T)"
        Ns, T = self.trials.shape
        assert self.time_rel.shape[0] == Ns, "time_rel y trials no coinciden en Ns"
        assert len(self.onsets_s) == T or len(self.onsets_s) == 0, "onsets_s debe coincidir con T (o estar vacío)"
# test/plugins_test/test_psd_average_plugin.py
import numpy as np
from pathlib import Path
import pytest

from core.services.fileio import FileIOService
from core.filters import trials as tr
from core.services.trial_dataset import TrialDataset
from plugins.analysis.frequency.psd_average.psd_average_plugin import Psd_average_plugin
from core.plugins.meta import PluginMeta

# ---------- Config ----------
ABF_PATH = Path(r"C:\Users\sergi\OneDrive\Documentos\Mis cosas\Tesis\pruebas\datos_prueba\17308005.abf")
MATLAB_CSV = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\psd_average_datos.csv")

TARGET_CHANNEL = 0
STIM_CHANNEL = 1
THRESHOLD = 0.7
T0 = -0.05
T1 = 4.00
END_MODE = "until_next_onset"
STIM_EXPECTED = 1
ISI = 0.0
PAD_VALUE = np.nan

# Parámetros por defecto del UI
TARGET_FS = 1000.0
WIN = "hamming"
NPERSEG = 256
NOVERLAP = 128
NFFT = 256
F_LO = 0.0
F_HI = 500.0

RTOL = 1e-6
ATOL = 1e-6
# ----------------------------


class PsdAvgDouble(Psd_average_plugin):
    """
    Doble de prueba que:
      - evita VTK/UI,
      - permite inyectar TD/SD,
      - captura (freq, power_avg) después del cálculo y filtro.
    """
    def __init__(self):
        meta = PluginMeta(
            id="psd_average",
            name="PSD Average",
            category="analysis",
            subcategory="frequency",
            version="0.0.0",
            icon="",
            logic_class="Psd_average_plugin",
        )
        super().__init__(meta)
        self._active_signal = None
        self._active_trials = None
        self.captured_freq = None      # (Nf_sel,)
        self.captured_power = None     # (Nf_sel, 1)

    # inyección
    def set_active_signal(self, sd): self._active_signal = sd
    def set_active_trials(self, td: TrialDataset): self._active_trials = td

    # puente esperados por el plugin
    def get_active_signal(self): return self._active_signal
    def get_active_trials(self): return self._active_trials

    # evita VTK
    def _ensure_vtk(self, *a, **k):
        self.vtk_interactor = None
        self.vtk_view = None

    # captura en vez de plotear
    def _plot_psd(self, freq, power, plot_title, lo, hi, ch_name):
        sel = (freq >= lo) & (freq <= hi)
        self.captured_freq = np.asarray(freq[sel], dtype=float)
        self.captured_power = np.asarray(power[sel, :], dtype=float)

    # helper para correr la lógica sin UI
    def run_average(self, *, target_fs=TARGET_FS, lo=F_LO, hi=F_HI,
                    window=WIN, nperseg=NPERSEG, noverlap=NOVERLAP, nfft=NFFT):
        td = self.get_active_trials()
        assert td is not None, "TrialDataset no presente"
        X = np.asarray(td.trials, dtype=np.float64)
        fs = float(td.sampling_rate)

        freq, power_all, fs_eff = self._compute_psd(
            X, fs, target_fs, window, int(nperseg), int(noverlap), int(nfft)
        )
        power_avg = np.mean(power_all, axis=1, keepdims=True)  # (Nf,1)
        self._plot_psd(freq, power_avg, "PSD (Average)", lo, hi, getattr(td, "channel_name", ""))
        return freq, power_avg, fs_eff


@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_CSV.exists(), reason="MATLAB CSV not found")
class TestPsdAverageABFVsMatlab:

    @pytest.fixture(scope="class")
    def ds(self):
        fio = FileIOService()
        sd = fio.load_abf(str(ABF_PATH))
        sd.signals = sd.signals.astype(np.float64, copy=False)
        sd.time = sd.time.astype(np.float64, copy=False)
        return sd

    @pytest.fixture(scope="class")
    def td(self, ds):
        return tr.cut_trials_single_channel(
            ds=ds,
            channel=TARGET_CHANNEL,
            stim_channel=STIM_CHANNEL,
            threshold=THRESHOLD,
            t0=T0, t1=T1, end_mode=END_MODE,
            stim_expected=STIM_EXPECTED, inter_stim_time=ISI,
            pad_value=PAD_VALUE, debug=False,
        )

    @pytest.fixture(scope="class")
    def app_psd_avg(self, ds, td):
        plug = PsdAvgDouble()
        plug.set_active_signal(ds)
        plug.set_active_trials(td)
        plug.run_average(target_fs=TARGET_FS, lo=F_LO, hi=F_HI,
                         window=WIN, nperseg=NPERSEG, noverlap=NOVERLAP, nfft=NFFT)
        assert plug.captured_power is not None and plug.captured_power.ndim == 2 and plug.captured_power.shape[1] == 1
        return plug.captured_freq, plug.captured_power[:, 0]

    @pytest.fixture(scope="class")
    def matlab_psd_avg(self):
        """
        Carga curva PSD promedio desde MATLAB.
        Si el CSV trae [f, Pxx], se usa la segunda columna (Pxx).
        Si trae una sola columna, se asume magnitud directamente.
        """
        M = np.loadtxt(MATLAB_CSV, delimiter=",")
        M = np.asarray(M, dtype=np.float64)
        if M.ndim == 1:
            return None, M
        if M.ndim == 2 and M.shape[1] >= 2:
            return M[:, 0], M[:, 1]
        return (M[:, 0] if M.shape[1] > 1 else None), M[:, -1]

    def test_internal_mean_consistency(self, td):
        """
        Verifica que el promedio entre trials de _compute_psd coincida
        con calcular Welch para todos los trials y luego hacer mean(axis=1).
        """
        plug = PsdAvgDouble()
        plug.set_active_trials(td)

        # plugin
        freq_p, power_all, _ = plug._compute_psd(
            np.asarray(td.trials, dtype=np.float64), float(td.sampling_rate),
            TARGET_FS, WIN, NPERSEG, NOVERLAP, NFFT
        )
        avg_p = np.mean(power_all, axis=1)  # (Nf,)

        # ruta "average"
        _, power_avg2, _ = plug.run_average(target_fs=TARGET_FS, lo=F_LO, hi=F_HI,
                                            window=WIN, nperseg=NPERSEG, noverlap=NOVERLAP, nfft=NFFT)
        n = min(avg_p.shape[0], power_avg2.shape[0])
        assert np.allclose(avg_p[:n], power_avg2[:n, 0], rtol=RTOL, atol=ATOL, equal_nan=True)

    def test_matches_matlab(self, app_psd_avg, matlab_psd_avg):
        """
        Compara la curva PSD promedio calculada por la app vs CSV de MATLAB (alineando por mínimo).
        """
        _, app_pow = app_psd_avg
        _, mat_pow = matlab_psd_avg

        n = min(app_pow.shape[0], mat_pow.shape[0])
        a = app_pow[:n]
        b = mat_pow[:n]
        assert np.allclose(a, b, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"PSD average mismatch at length {n}: app[{a.shape}] vs matlab[{b.shape}]"

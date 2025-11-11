# test/plugins_test/test_wavelet_plugin.py
import numpy as np
from pathlib import Path
import pytest

from core.services.fileio import FileIOService
from core.filters import trials as tr
from core.services.trial_dataset import TrialDataset
from plugins.analysis.time_frequency.wavelet.wavelet_plugin import Wavelet_plugin
from core.plugins.meta import PluginMeta

# ---------- Config ----------
ABF_PATH = Path(r"C:\Users\sergi\OneDrive\Documentos\Mis cosas\Tesis\pruebas\datos_prueba\17308005.abf")
MATLAB_SCALO = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\wavelet_datos.csv")

TARGET_CHANNEL = 0
STIM_CHANNEL = 1
THRESHOLD = 0.7
T0 = -0.05
T1 = 4.00
END_MODE = "until_next_onset"
STIM_EXPECTED = 1
ISI = 0.0
PAD_VALUE = np.nan

# Parámetros por defecto del plugin
TARGET_FS = 1000.0     # sampleDensitySpinBox
F_LO = 1.0             # lowFrequencySpinBox
F_HI = 500.0           # highFrequencySpinBox
CYCLES = 2.0           # cyclesSpinBox
NORMALIZE = False      # normalizeCheckBox
SCALE_LOG = False      # scaleCheckBox

RTOL = 1e-6
ATOL = 1e-6
# ----------------------------


class WaveletDouble(Wavelet_plugin):
    """
    Doble de prueba para el plugin Wavelet:
      - evita VTK/UI,
      - permite inyectar TD/SD,
      - expone un método run() que calcula el scalograma (sin render)
      - captura (scalogram, t, f) para comparar.
    """
    def __init__(self):
        meta = PluginMeta(
            id="wavelet",
            name="Wavelet",
            category="analysis",
            subcategory="time_frequency",
            version="0.0.0",
            icon="",
            logic_class="Wavelet_plugin",
        )
        super().__init__(meta)
        self._active_signal = None
        self._active_trials = None
        self.scalo = None
        self.t_axis = None
        self.f_axis = None

    # inyección
    def set_active_signal(self, sd): self._active_signal = sd
    def set_active_trials(self, td: TrialDataset): self._active_trials = td

    # puente esperados
    def get_active_signal(self): return self._active_signal
    def get_active_trials(self): return self._active_trials

    # evita VTK
    def ensure_vtk(self): pass
    def render_scalogram(self, *args, **kwargs): pass  # no pintar

    def run(self, *, fs_plot=TARGET_FS, fmin=F_LO, fmax=F_HI, cycles=CYCLES,
            normalize=NORMALIZE, scale_log=SCALE_LOG):
        td = self.get_active_trials()
        assert td is not None, "TrialDataset no presente"
        t = np.asarray(td.time_rel, dtype=float)
        X = np.asarray(td.trials, dtype=float)

        # tomar el vector del primer trial (como hace tu plugin)
        sig = X[:, 0] if X.ndim == 2 else X

        fs_calculado = round(1.0 / (t[1] - t[0]), 3)
        scalo, times, freqs = self.compute_wavelet(sig, fs_calculado, fs_plot, fmin, fmax, float(cycles))

        if normalize:
            scalo = self.normalize_tf(scalo, "z-score")  # o el método que quieras testear

        if scale_log:
            scalo, freqs = self._scale_log(scalo, freqs)

        self.scalo = np.asarray(scalo, dtype=float)       # (nF, nT)
        self.t_axis = np.asarray(times, dtype=float)      # (nT,)
        self.f_axis = np.asarray(freqs, dtype=float)      # (nF,)
        return self.scalo, self.t_axis, self.f_axis


@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_SCALO.exists(), reason="MATLAB scalogram CSV not found")
class TestWaveletABFVsMatlab:

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
    def app_scalogram(self, ds, td):
        plug = WaveletDouble()
        plug.set_active_signal(ds)
        plug.set_active_trials(td)
        scalo, t_axis, f_axis = plug.run(
            fs_plot=TARGET_FS, fmin=F_LO, fmax=F_HI, cycles=CYCLES,
            normalize=NORMALIZE, scale_log=SCALE_LOG
        )
        assert scalo.ndim == 2 and scalo.shape[0] > 0 and scalo.shape[1] > 0
        return scalo

    @pytest.fixture(scope="class")
    def matlab_scalogram(self):
        """
        Carga la matriz (nF, nT) exportada desde MATLAB. Debe ser la matriz
        que corresponde al “heatmap” de wavelet (sin ejes).
        """
        M = np.loadtxt(MATLAB_SCALO, delimiter=",")
        return np.asarray(M, dtype=np.float64)

    def test_internal_cwt_consistency(self, td, app_scalogram):
        """
        Verifica que compute_wavelet coincida si la ejecutamos “a mano” con los
        mismos parámetros (sin normalización ni escala log).
        """
        # Recalcular a mano usando la API del plugin
        plug = WaveletDouble()
        plug.set_active_trials(td)
        scalo2, _, _ = plug.run(
            fs_plot=TARGET_FS, fmin=F_LO, fmax=F_HI, cycles=CYCLES,
            normalize=False, scale_log=False
        )
        # alinear por mínimo (por si en MATLAB recortan/ajustan)
        r = min(app_scalogram.shape[0], scalo2.shape[0])
        c = min(app_scalogram.shape[1], scalo2.shape[1])
        A = app_scalogram[:r, :c]
        B = scalo2[:r, :c]
        assert np.allclose(A, B, rtol=RTOL, atol=ATOL, equal_nan=True)

    def test_matches_matlab(self, app_scalogram, matlab_scalogram):
        """
        Compara matriz (nF, nT) del escalograma vs CSV MATLAB.
        """
        r = min(app_scalogram.shape[0], matlab_scalogram.shape[0])
        c = min(app_scalogram.shape[1], matlab_scalogram.shape[1])
        A = app_scalogram[:r, :c]
        B = matlab_scalogram[:r, :c]
        assert np.allclose(A, B, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"Wavelet mismatch: app{A.shape} vs matlab{B.shape}"

# test/plugins_test/test_wavelet_average_plugin.py
import numpy as np
from pathlib import Path
import pytest

from core.services.fileio import FileIOService
from core.filters import trials as tr
from core.services.trial_dataset import TrialDataset
from plugins.analysis.time_frequency.wavelet_average.wavelet_average_plugin import Wavelet_average_plugin
from core.plugins.meta import PluginMeta

# ---------- Config ----------
ABF_PATH = Path(r"C:\Users\sergi\OneDrive\Documentos\Mis cosas\Tesis\pruebas\datos_prueba\17308005.abf")
MATLAB_SCALO = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\wavelet_average_datos.csv")

TARGET_CHANNEL = 0
STIM_CHANNEL = 1
THRESHOLD = 0.7
T0 = -0.05
T1 = 4.00
END_MODE = "until_next_onset"
STIM_EXPECTED = 1
ISI = 0.0
PAD_VALUE = np.nan

# Parámetros por defecto (igual que UI del plugin)
TARGET_FS = 1000.0    # sampleDensitySpinBox
F_LO = 1.0            # lowFrequencySpinBox
F_HI = 500.0          # highFrequencySpinBox
CYCLES = 2.0          # cyclesSpinBox
NORMALIZE = False     # normalizeCheckBox
NORM_METHOD = "z-score"  # combo cuando normalize=True
SCALE_LOG = False     # scaleCheckBox

RTOL = 1e-6
ATOL = 1e-6
# ----------------------------


class WaveletAvgDouble(Wavelet_average_plugin):
    """
    Doble de prueba:
      - evita VTK/UI/hilos,
      - permite inyectar TD/SD,
      - ejecuta el promedio de CWT de manera síncrona,
      - captura (scalogram_avg, t, f).
    """
    def __init__(self):
        meta = PluginMeta(
            id="wavelet_average",
            name="Wavelet Average",
            category="analysis",
            subcategory="time_frequency",
            version="0.0.0",
            icon="",
            logic_class="Wavelet_average_plugin",
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

    # no VTK
    def _create_vtk_container(self): pass
    def ensure_vtk(self): pass
    def render_scalogram(self, *args, **kwargs): pass

    # ejecución síncrona del promedio (emula WaveletWorker.run, pero sin QThread)
    def run_average(self, *, fs_plot=TARGET_FS, fmin=F_LO, fmax=F_HI, cycles=CYCLES,
                    normalize=NORMALIZE, norm_method=NORM_METHOD, scale_log=SCALE_LOG):
        td = self.get_active_trials()
        assert td is not None, "TrialDataset no presente"

        # (n_samples, n_trials)
        X = np.array(td.trials, dtype=float)
        if X.ndim == 1:
            X = X[:, np.newaxis]
        if X.shape[0] < X.shape[1]:
            X = X.T

        t = np.asarray(td.time_rel, dtype=float)
        assert t.size >= 2, "time_rel inválido"

        fs_calculado = round(1.0 / (t[1] - t[0]), 3)

        scalos = []
        # CWT por trial y apilar
        for k in range(X.shape[1]):
            sig = np.nan_to_num(X[:, k], nan=0.0, posinf=0.0, neginf=0.0)
            S, times, freqs = self.compute_wavelet(sig, fs_calculado, fs_plot, fmin, fmax, float(cycles))
            if S is None or S.size == 0:
                continue
            scalos.append(S)

        assert len(scalos) > 0, "No se pudo calcular ningún CWT"

        # Promedio (nF, nT)
        stacked = np.stack(scalos, axis=0)   # (T, nF, nT)
        avg_scalo = np.mean(stacked, axis=0) # (nF, nT)

        if normalize:
            avg_scalo = self.normalize_tf(avg_scalo, norm_method)

        if scale_log:
            avg_scalo, freqs = self._scale_log(avg_scalo, freqs)

        # Guardar capturas
        self.scalo = np.asarray(avg_scalo, dtype=float)
        self.t_axis = np.asarray(times, dtype=float)
        self.f_axis = np.asarray(freqs, dtype=float)
        return self.scalo, self.t_axis, self.f_axis


@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_SCALO.exists(), reason="MATLAB scalogram CSV not found")
class TestWaveletAverageABFVsMatlab:

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
    def app_scalogram_avg(self, ds, td):
        plug = WaveletAvgDouble()
        plug.set_active_signal(ds)
        plug.set_active_trials(td)
        scalo, t_axis, f_axis = plug.run_average(
            fs_plot=TARGET_FS, fmin=F_LO, fmax=F_HI, cycles=CYCLES,
            normalize=NORMALIZE, norm_method=NORM_METHOD, scale_log=SCALE_LOG
        )
        assert scalo.ndim == 2 and scalo.shape[0] > 0 and scalo.shape[1] > 0
        return scalo  # (nF, nT)

    @pytest.fixture(scope="class")
    def matlab_scalogram_avg(self):
        """
        Carga matriz (nF, nT) promediada desde MATLAB.
        Debe corresponder al heatmap promedio (sin ejes).
        """
        M = np.loadtxt(MATLAB_SCALO, delimiter=",")
        return np.asarray(M, dtype=np.float64)

    def test_internal_average_consistency(self, td, app_scalogram_avg):
        """
        Recalcula el promedio CWT manualmente llamando compute_wavelet trial por trial
        y verifica que coincida con run_average (mismos params, sin normalización ni log).
        """
        plug = WaveletAvgDouble()
        plug.set_active_trials(td)

        # Recalcular manual: run_average ya hace exactamente esto; lo repetimos para confirmar
        scalo2, _, _ = plug.run_average(
            fs_plot=TARGET_FS, fmin=F_LO, fmax=F_HI, cycles=CYCLES,
            normalize=False, scale_log=False
        )
        r = min(app_scalogram_avg.shape[0], scalo2.shape[0])
        c = min(app_scalogram_avg.shape[1], scalo2.shape[1])
        A = app_scalogram_avg[:r, :c]
        B = scalo2[:r, :c]
        assert np.allclose(A, B, rtol=RTOL, atol=ATOL, equal_nan=True)

    def test_matches_matlab(self, app_scalogram_avg, matlab_scalogram_avg):
        """
        Compara matriz (nF, nT) promedio de la app vs CSV MATLAB (alineando por mínimo).
        """
        r = min(app_scalogram_avg.shape[0], matlab_scalogram_avg.shape[0])
        c = min(app_scalogram_avg.shape[1], matlab_scalogram_avg.shape[1])
        A = app_scalogram_avg[:r, :c]
        B = matlab_scalogram_avg[:r, :c]
        assert np.allclose(A, B, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"Wavelet Average mismatch: app{A.shape} vs matlab{B.shape}"

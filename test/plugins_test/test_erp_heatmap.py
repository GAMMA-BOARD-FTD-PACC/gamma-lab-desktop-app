# test/integration/test_erp_heatmap_abf_vs_matlab.py
import numpy as np
import pytest
from pathlib import Path

# pipeline real
from core.services.fileio import FileIOService
from core.filters import trials as tr
from core.services.trial_dataset import TrialDataset
from core.plugins.meta import PluginMeta

# plugin real
from plugins.analysis.time.erp.erp_plugin import Erp_plugin


# ---------- Config ----------
ABF_PATH = Path(r"C:\Users\sergi\OneDrive\Documentos\Mis cosas\Tesis\pruebas\datos_prueba\17308005.abf")
MATLAB_CSV = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\erp_heatmap_datos.csv")

TARGET_CHANNEL = 0
STIM_CHANNEL = 1
THRESHOLD = 0.7
T0 = -0.05
T1 = 4.00
END_MODE = "until_next_onset"
STIM_EXPECTED = 1
ISI = 0.0
PAD_VALUE = np.nan
RTOL = 1e-6
ATOL = 1e-6
MAX_SAMPLES = 2000   # igual que el plugin para el downsample
# ----------------------------


class ErpHeatmapDouble(Erp_plugin):
    """
    Doble headless del plugin ERP para capturar la matriz del heatmap (abajo).
    Captura:
      - captured_t   -> (Tn_ds,)
      - captured_img -> (K, Tn_ds) (trials x time)
    """
    def __init__(self, max_samples: int = MAX_SAMPLES):
        meta = PluginMeta(
            id="erp-heatmap",
            name="ERP Heatmap (Double)",
            category="analysis",
            subcategory="time",
            version="0.0.0",
            icon="",
            logic_class="Erp_plugin",
        )
        super().__init__(meta)
        self._active_signal = None
        self._active_trials: TrialDataset | None = None
        self.max_samples = int(max_samples)

        # anula VTK/UI
        self.view_top = None
        self.view_bot = None
        self.vtk_top = None
        self.vtk_bot = None
        self.vtk_widget = None

        self.captured_t = None
        self.captured_img = None  # (K, Tn_ds)

    def ensure_vtk(self):
        self.view_top = None
        self.view_bot = None
        self.vtk_top = None
        self.vtk_bot = None
        self.vtk_widget = None

    # inyección
    def set_active_signal(self, sd): self._active_signal = sd
    def set_active_trials(self, td: TrialDataset): self._active_trials = td
    def get_active_signal(self): return self._active_signal
    def get_active_trials(self): return self._active_trials

    # núcleo: selección "todos", downsample y captura
    def run_all(self):
        td = self.get_active_trials()
        if td is None:
            raise RuntimeError("TrialDataset no inyectado.")

        t = np.asarray(td.time_rel, dtype=float)   # (Ns,)
        M = np.asarray(td.trials, dtype=float)     # (Ns, T) ó (T, Ns)

        # normaliza a (K, Ns) = (trials, samples)
        if M.shape[0] == t.size:
            M = M.T
        elif M.shape[1] == t.size:
            pass
        else:
            raise ValueError("time_rel no coincide con trials.")

        X = np.asarray(M, dtype=np.float32)  # (K, Ns)
        K, Tn = X.shape
        t_plot = t.copy()

        if Tn > self.max_samples:
            factor = int(np.ceil(Tn / self.max_samples))
            X = X[:, ::factor]
            t_plot = t_plot[::factor]
            Tn = X.shape[1]

        self.captured_t = t_plot.astype(float, copy=False)
        self.captured_img = X.astype(np.float32, copy=False)  # (K, Tn_ds)


@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_CSV.exists(), reason="MATLAB CSV not found")
class TestErpHeatmapABFVsMatlab:

    @pytest.fixture(scope="class")
    def ds(self):
        """Carga ABF real."""
        fio = FileIOService()
        sd = fio.load_abf(str(ABF_PATH))
        sd.signals = sd.signals.astype(np.float64, copy=False)
        sd.time = sd.time.astype(np.float64, copy=False)
        return sd

    @pytest.fixture(scope="class")
    def td(self, ds):
        """Corta trials con el pipeline real."""
        return tr.cut_trials_single_channel(
            ds=ds,
            channel=TARGET_CHANNEL,
            stim_channel=STIM_CHANNEL,
            threshold=THRESHOLD,
            t0=T0,
            t1=T1,
            end_mode=END_MODE,
            stim_expected=STIM_EXPECTED,
            inter_stim_time=ISI,
            pad_value=PAD_VALUE,
            debug=False,
        )

    @pytest.fixture(scope="class")
    def app_img(self, ds, td):
        """Ejecuta el doble y devuelve la matriz (K, Tn_ds)."""
        plug = ErpHeatmapDouble()
        plug.set_active_signal(ds)
        plug.set_active_trials(td)
        plug.run_all()
        return plug.captured_img  # (K, T)

    @pytest.fixture(scope="class")
    def matlab_img(self):
        """
        Carga el CSV del heatmap. Esperamos que MATLAB lo exporte como
        (K, T) = (filas=trials, columnas=tiempo).
        Si viene traspuesto, detectamos y corregimos.
        """
        M = np.loadtxt(MATLAB_CSV, delimiter=",")
        M = np.asarray(M, dtype=np.float64, copy=False)
        if M.ndim == 1:
            M = M.reshape(1, -1)
        # heurística: si hay muchas más filas que columnas, prueba trasponer
        if M.shape[0] > M.shape[1] and M.shape[0] > 4 * M.shape[1]:
            M = M.T
        return M  # (K, T) esperado

    def test_dimensions_compatible(self, app_img, matlab_img):
        a, b = app_img, matlab_img
        assert a.ndim == 2 and b.ndim == 2
        assert a.shape[0] >= 1 and a.shape[1] >= 1
        assert b.shape[0] >= 1 and b.shape[1] >= 1

    def test_values_match_matlab(self, app_img, matlab_img):
        # alinear por mínimo
        r = min(app_img.shape[0], matlab_img.shape[0])  # K
        c = min(app_img.shape[1], matlab_img.shape[1])  # T
        A = app_img[:r, :c]
        B = matlab_img[:r, :c]
        assert np.allclose(A, B, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"Mismatch heatmap: app{A.shape} vs matlab{B.shape}"

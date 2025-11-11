# test/integration/test_erp_butterfly_abf_vs_matlab.py
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
MATLAB_CSV = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\erp_butterfly_datos.csv")

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
# ----------------------------


class ErpButterflyDouble(Erp_plugin):
    """
    Doble headless del plugin ERP para capturar la matriz del gráfico superior (butterfly).
    Captura:
      - captured_t      -> (Ns,)
      - captured_lines  -> (K, Ns)  (K trials, Ns samples)
    """
    def __init__(self):
        meta = PluginMeta(
            id="erp-butterfly",
            name="ERP Butterfly (Double)",
            category="analysis",
            subcategory="time",
            version="0.0.0",
            icon="",
            logic_class="Erp_plugin",
        )
        super().__init__(meta)
        self._active_signal = None
        self._active_trials: TrialDataset | None = None
        self.captured_t = None
        self.captured_lines = None

        # anula VTK/UI
        self.view_top = None
        self.view_bot = None
        self.vtk_top = None
        self.vtk_bot = None
        self.vtk_widget = None

    def ensure_vtk(self):
        # sin UI en tests
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

    # núcleo: selección "todos" y captura
    def run_all(self):
        td = self.get_active_trials()
        if td is None:
            raise RuntimeError("TrialDataset no inyectado.")

        t = np.asarray(td.time_rel, dtype=float)          # (Ns,)
        M = np.asarray(td.trials, dtype=float)            # (Ns, T) ó (T, Ns)

        # normaliza a (K, Ns) = (trials, samples)
        if M.shape[0] == t.size:
            M = M.T
        elif M.shape[1] == t.size:
            pass
        else:
            raise ValueError("time_rel no coincide con trials.")

        self.captured_t = t
        self.captured_lines = M  # (K, Ns)


@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_CSV.exists(), reason="MATLAB CSV not found")
class TestErpButterflyABFVsMatlab:

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
    def app_matrix(self, ds, td):
        """Ejecuta el doble y devuelve la matriz (Ns, K) para comparar directo con MATLAB."""
        plug = ErpButterflyDouble()
        plug.set_active_signal(ds)
        plug.set_active_trials(td)
        plug.run_all()
        # el gráfico butterfly en MATLAB se exportó como "una columna por línea(trial)"
        # => CSV (Ns, K). Nosotros tenemos (K, Ns) -> transponemos.
        return plug.captured_lines.T  # (Ns, K)

    @pytest.fixture(scope="class")
    def matlab_matrix(self):
        """Carga el CSV (una columna por línea). Esperamos (Ns, K)."""
        M = np.loadtxt(MATLAB_CSV, delimiter=",")
        M = np.asarray(M, dtype=np.float64, copy=False)
        if M.ndim == 1:
            M = M.reshape(-1, 1)
        return M  # (Ns, K)

    def test_dimensions_compatible(self, app_matrix, matlab_matrix):
        a, b = app_matrix, matlab_matrix
        assert a.ndim == 2 and b.ndim == 2
        assert a.shape[0] >= 1 and a.shape[1] >= 1
        assert b.shape[0] >= 1 and b.shape[1] >= 1

    def test_values_match_matlab(self, app_matrix, matlab_matrix):
        # alinear por mínimo (Ns y K pueden diferir si hubo selección/distinto conteo)
        r = min(app_matrix.shape[0], matlab_matrix.shape[0])
        c = min(app_matrix.shape[1], matlab_matrix.shape[1])
        A = app_matrix[:r, :c]
        B = matlab_matrix[:r, :c]
        assert np.allclose(A, B, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"Mismatch butterfly: app{A.shape} vs matlab{B.shape}"

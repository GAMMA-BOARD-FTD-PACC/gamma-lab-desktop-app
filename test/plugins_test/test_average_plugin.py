# test/integration/test_average_abf_vs_matlab.py
import os
from pathlib import Path
import numpy as np
import pytest

# real pipeline bits
from core.services.fileio import FileIOService
from core.filters import trials as tr
from core.services.trial_dataset import TrialDataset
from plugins.analysis.time.average.average_plugin import Average_plugin
from core.plugins.meta import PluginMeta


# ---------- Config ----------
ABF_PATH = Path(r"C:\Users\sergi\OneDrive\Documentos\Mis cosas\Tesis\pruebas\datos_prueba\17308005.abf")
MATLAB_CSV = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\average_tiempo_datos.csv")

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


class AverageDouble(Average_plugin):
    """
    Doble de pruebas que evita UI/VTK y captura (t, avg).
    """
    def __init__(self):
        meta = PluginMeta(
            id="average",
            name="Average",
            category="analysis",
            subcategory="time",
            version="0.0.0",
            icon="",  # o una ruta válida si tu meta lo exige
            logic_class="Average_plugin",
        )
        super().__init__(meta)
        self._captured_t = None
        self._captured_avg = None
        self._active_signal = None
        self._active_trials = None

    # evita UI/VTK
    def ensure_vtk(self):
        self.view = None
        self.vtk_widget = None

    # captura en vez de renderizar
    def render_average(self, t, av_data, channel_name=None, unit=None):
        self._captured_t = np.asarray(t, dtype=float)
        self._captured_avg = np.asarray(av_data, dtype=float)

    # puentes que el plugin original espera
    def get_active_signal(self):
        return self._active_signal

    def get_active_trials(self):
        return self._active_trials

    # helpers de inyección
    def set_active_signal(self, sd):
        self._active_signal = sd

    def set_active_trials(self, td: TrialDataset):
        self._active_trials = td


@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_CSV.exists(), reason="MATLAB CSV not found")
class TestAverageABFVsMatlab:

    @pytest.fixture(scope="class")
    def ds(self):
        """Carga ABF real vía FileIOService."""
        fio = FileIOService()
        sd = fio.load_abf(str(ABF_PATH))  # ajusta a tu API real si difiere
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
    def app_avg(self, ds, td):
        """Ejecuta el plugin Average (headless) y captura su vector promedio."""
        plug = AverageDouble()
        plug.set_active_signal(ds)
        plug.set_active_trials(td)
        plug._on_calculate_average()
        assert plug._captured_avg is not None and plug._captured_avg.ndim == 1
        return plug._captured_avg

    @pytest.fixture(scope="class")
    def matlab_avg(self):
        """Carga el CSV de MATLAB (una columna esperada)."""
        M = np.loadtxt(MATLAB_CSV, delimiter=",")
        M = np.asarray(M, dtype=np.float64)
        if M.ndim == 2 and M.shape[1] >= 1:
            # si tu CSV tiene (Ns,1) o (Ns,2 [t,y]), toma la última col por seguridad
            M = M[:, -1]
        elif M.ndim != 1:
            M = M.reshape(-1)
        return M

    def test_average_plugin_internal_mean_consistency(self, td, app_avg):
        """El promedio del plugin debe coincidir con np.nanmean(trials, axis=1)."""
        expected = np.nanmean(td.trials, axis=1)
        assert app_avg.shape == expected.shape
        assert np.allclose(app_avg, expected, rtol=RTOL, atol=ATOL, equal_nan=True)

    def test_average_matches_matlab(self, app_avg, matlab_avg):
        """Compara el promedio del plugin contra el CSV de MATLAB (alineación por mínimo)."""
        n = min(app_avg.shape[0], matlab_avg.shape[0])
        a = app_avg[:n]
        b = matlab_avg[:n]
        assert np.allclose(a, b, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"Average mismatch at length {n}: app[{a.shape}] vs matlab[{b.shape}]"

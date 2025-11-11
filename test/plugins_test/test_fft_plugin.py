# test/integration/test_fft_abf_vs_matlab.py
import os
from pathlib import Path
import numpy as np
import pytest

# pipeline bits
from core.services.fileio import FileIOService
from core.filters import trials as tr
from core.services.trial_dataset import TrialDataset
from plugins.analysis.frequency.fft.fft_plugin import Fft_plugin
from core.plugins.meta import PluginMeta


# ---------- Config (adjust paths if needed) ----------
ABF_PATH = Path(r"C:\Users\sergi\OneDrive\Documentos\Mis cosas\Tesis\pruebas\datos_prueba\17308005.abf")
MATLAB_CSV = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\fft_datos.csv")

TARGET_CHANNEL = 0
STIM_CHANNEL = 1
THRESHOLD = 0.7
T0 = -0.05
T1 = 4.00
END_MODE = "until_next_onset"
STIM_EXPECTED = 1
ISI = 0.0
PAD_VALUE = np.nan

# FFT params used in the test-double "UI"
UI_TARGET_FS = 0.0     # 0 -> no resample (match MATLAB more easily)
UI_F_LO = 0.0
UI_F_HI = 1e9          # very high to avoid trimming

RTOL = 1e-6
ATOL = 1e-6
# -----------------------------------------------------


# -------- Minimal UI stubs for the plugin --------
class _Spin:
    def __init__(self, v): self._v = float(v)
    def value(self): return self._v

class _FftUiStub:
    def __init__(self, target_fs, f_lo, f_hi):
        self.sampleDensitySpinBox = _Spin(target_fs)
        self.lowFrequencySpinBox = _Spin(f_lo)
        self.highFrequencySpinBox = _Spin(f_hi)
        # fields referenced by _ensure_vtk (we won't call it in the double)
        self.plotArea = None
        self.layoutWidget = None
        self.splitter = None


# -------- Test-double FFT plugin (headless) --------
class FftDouble(Fft_plugin):
    """
    Headless version of the FFT plugin:
      - bypasses UI/VTK
      - injects td/ds directly
      - captures (freq, mag) on _plot_fft
    """
    def __init__(self, target_fs=UI_TARGET_FS, f_lo=UI_F_LO, f_hi=UI_F_HI):
        meta = PluginMeta(
            id="fft",
            name="FFT",
            category="analysis",
            subcategory="frequency",
            version="0.0.0",
            icon="",
            logic_class="Fft_plugin",
        )
        super().__init__(meta)
        self._captured_freq = None
        self._captured_mag = None
        self._active_td: TrialDataset | None = None
        self._active_sd = None
        # stub UI for parameter reads
        self.ui = _FftUiStub(target_fs, f_lo, f_hi)

    # bypass VTK creation
    def _ensure_vtk(self):  # noqa: D401
        self.vtk_interactor = None
        self.vtk_view = None
        self.chart = None

    # inject datasets
    def set_active_trials(self, td: TrialDataset): self._active_td = td
    def set_active_signal(self, sd): self._active_sd = sd

    # plugin expects these accessors
    def get_active_signal(self): return self._active_sd

    # bypass DataStore/mainwin checks and return the injected TD
    def _load_trials_from_store(self):
        td = self._active_td
        if td is None or not hasattr(td, "trials") or td.trials.size == 0:
            return None, None, None
        fs = float(getattr(td, "sampling_rate", 0.0))
        X = np.asarray(td.trials, dtype=np.float64)  # (Ns, T)
        ch = getattr(td, "channel_name", "")
        return fs, X, ch

    # capture instead of plotting
    def _plot_fft(self, freq: np.ndarray, mag: np.ndarray, ch_name: str, lo: float, hi: float):
        self._captured_freq = np.asarray(freq, dtype=float)
        self._captured_mag = np.asarray(mag, dtype=float)


# ------------------- Fixtures -------------------
@pytest.fixture(scope="session")
def ds():
    fio = FileIOService()
    sd = fio.load_abf(str(ABF_PATH))
    # enforce float64 for determinism
    sd.signals = sd.signals.astype(np.float64, copy=False)
    sd.time = sd.time.astype(np.float64, copy=False)
    return sd

@pytest.fixture(scope="session")
def td(ds):
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

@pytest.fixture(scope="session")
def app_fft(ds, td):
    plug = FftDouble(target_fs=UI_TARGET_FS, f_lo=UI_F_LO, f_hi=UI_F_HI)
    plug.set_active_signal(ds)
    plug.set_active_trials(td)
    plug._on_calculate_clicked()
    assert plug._captured_freq is not None and plug._captured_mag is not None
    return plug._captured_freq, plug._captured_mag  # (Nf,), (Nf, T)

@pytest.fixture(scope="session")
def matlab_fft_matrix():
    """
    Load MATLAB CSV exported for the FFT figure.
    Expected to be either (Nf, T) or (T, Nf). We will adapt at compare time.
    """
    M = np.loadtxt(MATLAB_CSV, delimiter=",")
    M = np.asarray(M, dtype=np.float64)
    # ensure 2D
    if M.ndim == 1:
        M = M.reshape(-1, 1)
    return M  # unknown orientation yet


# ------------------- Tests -------------------
@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_CSV.exists(), reason="MATLAB CSV not found")
class TestFFTABFVsMatlab:

    def test_internal_fft_consistency(self, td, app_fft):
        """
        Sanity check: plugin FFT must match a direct numpy rFFT using its params.
        """
        freq_app, mag_app = app_fft  # (Nf,), (Nf, T)

        # Recompute with the same rules from _compute_fft
        X = np.asarray(td.trials, dtype=np.float64)  # (Ns, T)
        fs = float(td.sampling_rate)

        # same decimation rule as plugin
        target_fs = UI_TARGET_FS
        if target_fs and target_fs > 0:
            srt = max(1, int(round(fs / float(target_fs))))
        else:
            srt = 1
        fs_eff = fs / srt
        Xds = X[::srt, :] if srt > 1 else X
        Ns_eff = Xds.shape[0]
        mF = np.fft.rfft(Xds, axis=0)
        mag_np = np.abs(mF)
        freq_np = np.fft.rfftfreq(Ns_eff, d=1.0 / fs_eff)

        # Align by min in case plugin filtered out-of-range freqs (we set hi big, so it shouldn't)
        r = min(freq_app.size, freq_np.size)
        c = min(mag_app.shape[1], mag_np.shape[1])

        assert np.allclose(freq_app[:r], freq_np[:r], rtol=RTOL, atol=ATOL)
        assert np.allclose(mag_app[:r, :c], mag_np[:r, :c], rtol=RTOL, atol=ATOL)

    def test_matches_matlab_csv(self, app_fft, matlab_fft_matrix):
        """
        Compare the plugin output against MATLAB CSV.
        We adapt MATLAB orientation:
          - if matlab rows match plugin Nf, use as-is (Nf, T)
          - else if columns match plugin Nf, transpose.
        """
        freq_app, mag_app = app_fft  # (Nf,), (Nf, T)
        Nf_app, T_app = mag_app.shape

        M = matlab_fft_matrix
        # orientation fix
        if M.shape[0] == Nf_app:
            M_use = M
        elif M.shape[1] == Nf_app:
            M_use = M.T
        else:
            # fallback: align by min both dims after trying transpose
            if M.shape[0] >= M.shape[1]:
                M_use = M
            else:
                M_use = M.T

        # Align by min (number of freqs, number of trials/lines)
        r = min(Nf_app, M_use.shape[0])
        c = min(T_app, M_use.shape[1])
        A = mag_app[:r, :c]
        B = M_use[:r, :c]

        assert np.allclose(A, B, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"FFT mismatch: app{A.shape} vs matlab{B.shape}"

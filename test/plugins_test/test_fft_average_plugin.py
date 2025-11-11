# test/plugins_test/test_fft_average_plugin.py
import os
from pathlib import Path
import numpy as np
import pytest

from core.services.fileio import FileIOService
from core.filters import trials as tr
from core.services.trial_dataset import TrialDataset
from plugins.analysis.frequency.fft_average.fft_average_plugin import Fft_average_plugin
from core.plugins.meta import PluginMeta

# ---------- Config ----------
ABF_PATH = Path(r"C:\Users\sergi\OneDrive\Documentos\Mis cosas\Tesis\pruebas\datos_prueba\17308005.abf")
MATLAB_CSV = Path(r"C:\Users\sergi\OneDrive\Documentos\GitHub\gamma-lab-desktop-app\test\data\fft_average_datos.csv")

TARGET_CHANNEL = 0
STIM_CHANNEL = 1
THRESHOLD = 0.7
T0 = -0.05
T1 = 4.00
END_MODE = "until_next_onset"
STIM_EXPECTED = 1
ISI = 0.0
PAD_VALUE = np.nan

# Parámetros “por defecto” del UI del plugin
TARGET_FS = 1000.0
F_LO = 0.0
F_HI = 500.0

RTOL = 1e-6
ATOL = 1e-6
# ----------------------------


class FftAvgDouble(Fft_average_plugin):
    """
    Doble de prueba que:
      - evita UI/VTK,
      - permite inyectar TD/SD,
      - y captura (freq, mag) tras el cálculo y filtrado.
    """
    def __init__(self):
        meta = PluginMeta(
            id="fft_average",
            name="FFT Average",
            category="analysis",
            subcategory="frequency",
            version="0.0.0",
            icon="",
            logic_class="Fft_average_plugin",
        )
        super().__init__(meta)
        self._active_signal = None
        self._active_trials = None
        self.captured_freq = None     # (Nf_sel,)
        self.captured_mag = None      # (Nf_sel, 1)

    # inyección
    def set_active_signal(self, sd):
        self._active_signal = sd

    def set_active_trials(self, td: TrialDataset):
        self._active_trials = td

    # puente
    def get_active_signal(self):
        return self._active_signal

    def get_active_trials(self):
        return self._active_trials

    # evita VTK
    def _ensure_vtk(self, *args, **kwargs):
        self.vtk_interactor = None
        self.vtk_view = None

    # captura en vez de plotear
    def _plot_fft_average(self, freq, mag, ch_name, lo, hi, fs_eff):
        sel = (freq >= max(lo, 0.0)) & (freq <= min(hi, fs_eff/2.0))
        self.captured_freq = np.asarray(freq[sel], dtype=float)
        self.captured_mag = np.asarray(mag[sel, :], dtype=float)

    # helper para correr sin UI
    def run(self, target_fs=TARGET_FS, lo=F_LO, hi=F_HI, per_trial=False):
        td = self.get_active_trials()
        assert td is not None, "TrialDataset no presente"
        X = np.asarray(td.trials, dtype=np.float64)   # (Ns, T)
        fs = float(td.sampling_rate)

        freq, mag, fs_eff = self._compute_fft_average(X, fs, target_fs, per_trial=per_trial)
        self._plot_fft_average(freq, mag, getattr(td, "channel_name", ""), lo, hi, fs_eff)
        return freq, mag, fs_eff


@pytest.mark.skipif(not ABF_PATH.exists(), reason="ABF file not found")
@pytest.mark.skipif(not MATLAB_CSV.exists(), reason="MATLAB CSV not found")
class TestFftAverageABFVsMatlab:

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
            t0=T0,
            t1=T1,
            end_mode=END_MODE,
            stim_expected=STIM_EXPECTED,
            inter_stim_time=ISI,
            pad_value=PAD_VALUE,
            debug=False,
        )

    @pytest.fixture(scope="class")
    def app_fft_avg(self, ds, td):
        plug = FftAvgDouble()
        plug.set_active_signal(ds)
        plug.set_active_trials(td)
        # Corre cálculo con promedio entre trials (per_trial=False)
        plug.run(target_fs=TARGET_FS, lo=F_LO, hi=F_HI, per_trial=False)
        # Capturado: (Nf_sel, 1)
        assert plug.captured_mag is not None and plug.captured_mag.ndim == 2 and plug.captured_mag.shape[1] == 1
        return plug.captured_freq, plug.captured_mag[:, 0]

    @pytest.fixture(scope="class")
    def matlab_fft_avg(self):
        """
        Carga la curva de magnitud (columna única o segunda columna si el CSV trae [f, mag]).
        """
        M = np.loadtxt(MATLAB_CSV, delimiter=",")
        M = np.asarray(M, dtype=np.float64)
        if M.ndim == 1:
            # vector de magnitud
            return None, M
        if M.ndim == 2 and M.shape[1] >= 2:
            return M[:, 0], M[:, 1]
        # fallback: usa última columna como magnitud
        return (M[:, 0] if M.shape[1] > 1 else None), M[:, -1]

    def test_internal_mean_consistency(self, td):
        """
        Verifica que _compute_fft_average concuerde con un cálculo manual:
        - FFT por trial
        - |.|, tomar positivo, quedarnos con Nf = Ns//2+1
        - promedio por frecuencia.
        """
        X = np.asarray(td.trials, dtype=np.float64)       # (Ns, T)
        fs = float(td.sampling_rate)

        # diezmado como en el plugin
        srt = max(1, int(round(fs / TARGET_FS))) if TARGET_FS > 0 else 1
        fs_eff = fs / srt
        Xds = X[::srt, :]

        Ns_eff = Xds.shape[0]
        F = np.fft.fft(Xds, n=Ns_eff, axis=0)[: (Ns_eff // 2) + 1, :]
        mag = np.abs(F).astype(np.float64)                # (Nf, T)
        mean_mag = np.nanmean(mag, axis=1)               # (Nf,)

        # plugin
        plug = FftAvgDouble()
        plug.set_active_trials(td)
        _, mag_out, _ = plug._compute_fft_average(X, fs, TARGET_FS, per_trial=False)
        mag_out = mag_out[:, 0]                           # (Nf,)

        n = min(mean_mag.shape[0], mag_out.shape[0])
        assert np.allclose(mean_mag[:n], mag_out[:n], rtol=RTOL, atol=ATOL, equal_nan=True)

    def test_matches_matlab(self, app_fft_avg, matlab_fft_avg):
        """
        Compara magnitud promedio (app) vs MATLAB. Si MATLAB trae frecuencia,
        se ignora para la comparación y se alinea por mínimo.
        """
        _, app_mag = app_fft_avg        # (Nf_sel,)
        _, mat_mag = matlab_fft_avg     # (Nf_csv,)

        n = min(app_mag.shape[0], mat_mag.shape[0])
        a = app_mag[:n]
        b = mat_mag[:n]
        assert np.allclose(a, b, rtol=RTOL, atol=ATOL, equal_nan=True), \
            f"FFT average mismatch at length {n}: app[{a.shape}] vs matlab[{b.shape}]"

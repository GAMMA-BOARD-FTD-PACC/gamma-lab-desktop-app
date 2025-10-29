import sys
import numpy as np
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
from scipy.signal import welch

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from plugins.analysis.frequency.relative_psd.relative_psd_plugin_ui import Ui_Relative_psd


class Relative_psd_plugin(IPlugin):
    """
    PSD relativa (y absoluta) replicando f_PSD_Relative de MATLAB.
    - Welch por columnas (trials)
    - Ptot en [0.5, 490] Hz
    - Bins seleccionados como MATLAB: id1 = find(f>=lo), id2 = find(f>=hi), sum inclusive id1:id2
    - Modo GF:
        GF=1 	-> All Trials (no promedio entre trials, suma potencias)
        GF=0 	-> Average 	(promedio de PSD entre trials)
    """

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None
        self.widget: QtWidgets.QWidget | None = None
        self.ui: Ui_Relative_psd | None = None
        self.active_signal: SignalDataset | None = None

    # ---------- util ----------
    def _log(self, *args):
        print("[Relative PSD]", *args)
        sys.stdout.flush()

    def initialize(self, kernel):
        self.kernel = kernel

    def start(self, kernel):
        self.mainwin = kernel.get_service("MainWindow")

    def stop(self):
        pass

    def process(self, data):
        self._log("Process:", data)

    # ---------- UI ----------
    def get_widget(self, parent=None):
        if self.widget is None:
            self.ui = Ui_Relative_psd()
            self.widget = QtWidgets.QWidget(parent)
            self.ui.setupUi(self.widget)
            self._inject_optional_controls()
            self._wire_ui()
            self._init_defaults()
        else:
            self.widget.setParent(parent)
        return self.widget

    def _inject_optional_controls(self):
        """Inyecta combos opcionales sin asumir que existe ui.widget."""
        def _add_form_row(label_text: str, w: QtWidgets.QWidget):
            # 1) Form layout si existe
            if hasattr(self.ui, "formLayoutWelch") and isinstance(self.ui.formLayoutWelch, QtWidgets.QFormLayout):
                self.ui.formLayoutWelch.addRow(QtWidgets.QLabel(label_text), w)
                return
            # 2) Layout del panel si existe
            if hasattr(self.ui, "panel") and isinstance(self.ui.panel, QtWidgets.QWidget):
                lay = self.ui.panel.layout()
                if lay is None:
                    lay = QtWidgets.QVBoxLayout(self.ui.panel)
                hl = QtWidgets.QHBoxLayout()
                hl.addWidget(QtWidgets.QLabel(label_text))
                hl.addWidget(w)
                lay.addLayout(hl)
                return
            # 3) Fallback: layout del widget raíz del plugin
            if self.widget.layout() is None:
                self.widget.setLayout(QtWidgets.QVBoxLayout())
            hl = QtWidgets.QHBoxLayout()
            hl.addWidget(QtWidgets.QLabel(label_text))
            hl.addWidget(w)
            self.widget.layout().addLayout(hl)

        # --- Detrend ---
        if not hasattr(self.ui, "detrendComboBox"):
            detrend_cb = QtWidgets.QComboBox()
            detrend_cb.addItems(["none", "constant", "linear"])
            self.ui.detrendComboBox = detrend_cb
            _add_form_row("Detrend", detrend_cb)

        # --- GF (modo de cálculo) ---
        if not hasattr(self.ui, "gainFactorComboBox"):
            gf_cb = QtWidgets.QComboBox()
            gf_cb.addItems(["Average (GF=0)", "All Trials (GF=1)"])
            self.ui.gainFactorComboBox = gf_cb
            _add_form_row("Calculation Mode (GF)", gf_cb)

    def _wire_ui(self):
        self.ui.pushButton.clicked.connect(self._on_calculate_clicked)
        self.ui.npersegSpinBox.valueChanged.connect(self._sync_noverlap)

    def _init_defaults(self):
        # Ventana hamming (como MATLAB)
        try:
            idx = self.ui.windowComboBox.findText("hamming", QtCore.Qt.MatchFixedString)
            if idx >= 0:
                self.ui.windowComboBox.setCurrentIndex(idx)
        except Exception:
            pass
        # Welch
        self.ui.npersegSpinBox.setValue(256)
        self._sync_noverlap()
        self.ui.nfftSpinBox.setValue(256)
        # Banda por defecto
        self.ui.f1DoubleSpinBox.setValue(8.0)
        self.ui.f2DoubleSpinBox.setValue(12.0)
        # Detrend
        if hasattr(self.ui, "detrendComboBox"):
            self.ui.detrendComboBox.setCurrentText("none")
        # GF por defecto = 1 (All Trials) para emular MATLAB si no se tocó
        if hasattr(self.ui, "gainFactorComboBox"):
            self.ui.gainFactorComboBox.setCurrentIndex(1)

    def _sync_noverlap(self):
        nperseg = self.ui.npersegSpinBox.value()
        self.ui.noverlapSpinBox.setValue(nperseg // 2)
        self.ui.nfftSpinBox.setValue(nperseg)

    # ---------- acciones ----------
    def _on_calculate_clicked(self):
        self._log("_on_calculate_clicked()")

        fs, X, ch_name = self._load_trials_from_store()
        if X is None or fs is None:
            self._notify("Relative PSD: No hay trials en la señal activa.")
            return

        # Target Fs por defecto (resolución suficiente)
        if self.ui.sampleDensityDoubleSpinBox.value() <= 0:
            self.ui.sampleDensityDoubleSpinBox.setValue(min(fs, 1000.0))

        # Parámetros
        try:
            target_fs = float(self.ui.sampleDensityDoubleSpinBox.value())
            window 	  = self.ui.windowComboBox.currentText()
            nperseg 	= self.ui.npersegSpinBox.value()
            noverlap 	= self.ui.noverlapSpinBox.value()
            nfft 	  = self.ui.nfftSpinBox.value()
            f1 	    = float(self.ui.f1DoubleSpinBox.value())
            f2 	    = float(self.ui.f2DoubleSpinBox.value())
            detrend 	= getattr(self.ui, "detrendComboBox", None)
            detrend 	= detrend.currentText() if detrend else "none"
            gf_idx 	= getattr(self.ui, "gainFactorComboBox", None)
            GF 	    = 1 if (gf_idx and gf_idx.currentIndex() == 1) else 0 	# 1=All Trials, 0=Average

            if f1 >= f2:
                raise ValueError("Fq1 (Low) debe ser menor que Fq2 (High).")
        except Exception as e:
            QMessageBox.warning(self.widget, "Error de Parámetros", str(e))
            return

        try:
            freq, pxx_all, fs_eff = self._compute_psd(
                X, fs, target_fs, window, nperseg, noverlap, nfft, detrend
            )
        except Exception as e:
            self._log("Error en _compute_psd:", e)
            QMessageBox.critical(self.widget, "Error de Cálculo", f"No se pudo calcular la PSD: {e}")
            return

        # --- Relative PSD (GF) ---
        abs_power, rel_power = self._compute_relative_psd(freq, pxx_all, f1, f2, GF)

        # UI
        self.ui.absPowerValue.setText(f"{abs_power: .4e}")
        self.ui.relPowerValue.setText(f"{rel_power: .2f} %")

        self._notify(f"PSD Relativa [{f1}-{f2} Hz] lista. fs_eff={fs_eff:.1f} Hz, df≈{freq[1]-freq[0]:.2f} Hz")

        # Log bandas estándar (como en MATLAB)
        self._log_bands(freq, pxx_all, GF)

    # ---------- Relative PSD ----------

    # 1) Reemplaza _band_sum(...) con soporte de bordes
    def _band_sum(self, freq: np.ndarray, pxx: np.ndarray, lo: float, hi: float,
                  edges: str = "matlab") -> float:
        """
        Suma potencia en [lo, hi] con dos políticas de bordes:
          - edges='matlab'    -> inclusivo arriba (id2 = find(f>=hi); sum[i1:id2]  )
          - edges='exclusive' -> exclusivo arriba (sum[i1:id2])  sin el bin 'hi'
        """
        i1 = int(np.searchsorted(freq, lo, side="left"))
        if edges == "matlab":
            i2 = int(np.searchsorted(freq, hi, side="left"))  # incluye el bin de hi
            i1 = max(0, min(i1, len(freq) - 1))
            i2 = max(0, min(i2, len(freq) - 1))
            if i2 < i1: i1, i2 = i2, i1
            return float(np.nansum(pxx[i1:i2 + 1]))
        else:
            i2 = int(np.searchsorted(freq, hi, side="left"))  # exclusivo
            i1 = max(0, min(i1, len(freq)))
            i2 = max(0, min(i2, len(freq)))
            if i2 < i1: i1, i2 = i2, i1
            return float(np.nansum(pxx[i1:i2]))


    # 2) Ajusta el cálculo principal para usar esa política
    def _compute_relative_psd(self, freq: np.ndarray, pxx_all: np.ndarray,
                              f1: float, f2: float, GF: int):
        """
        Reproduce f_PSD_Relative:
        - GF=1: pxx_av = pxx_all (todos los trials), luego sumar en eje trials
        - GF=0: pxx_av = mean(pxx_all, eje trials)
        Ptot en [0.5, 490] Hz.
        Utiliza _band_sum para manejar los bordes (inclusivos/exclusivos).
        """
        # sumar (GF=1) o promediar (GF=0)
        pxx_sum = np.nansum(pxx_all, axis=1) if GF == 1 else np.nanmean(pxx_all, axis=1)

        edges_mode = "matlab"     # o "exclusive" si quieres que sumen ≈1

        # Tip rápido para depurar:
        df = freq[1]-freq[0]
        i1 = np.searchsorted(freq, f1, side="left")
        i2_matlab = np.searchsorted(freq, f2, side="left")
        self._log(f"df = {df:.4f} Hz")
        self._log(f"Banda [{f1}-{f2}] Hz: bins [{i1}:{i2_matlab}] (MATLAB-style) -> f[{i1}]={freq[i1]:.4f}, f[{i2_matlab}]={freq[min(i2_matlab,len(freq)-1)]:.4f}")
        # Fin Tip rápido

        Ptot     = self._band_sum(freq, pxx_sum, 0.5, 490.0, edges=edges_mode)
        pow_band = self._band_sum(freq, pxx_sum, f1,  f2,    edges=edges_mode)
        rel      = (pow_band / Ptot) * 100.0 if Ptot > 0 else 0.0

        self._log(f"[GF={GF}, edges={edges_mode}] Band {f1}-{f2} Hz -> Abs={pow_band:.4e}, Rel={rel:.2f}%")
        return pow_band, rel


    # 3) Cambia las bandas del log para igualar tus números de MATLAB
    def _log_bands(self, freq: np.ndarray, pxx_all: np.ndarray, GF: int):
        # sumar (GF=1) o promediar (GF=0)
        pxx_sum = np.nansum(pxx_all, axis=1) if GF == 1 else np.nanmean(pxx_all, axis=1)
        edges_mode = "matlab"  # idem al usado arriba

        def bsum(lo, hi): return self._band_sum(freq, pxx_sum, lo, hi, edges=edges_mode)

        Ptot = bsum(0.5, 490.0)
        if Ptot <= 0:
            self._log("Ptot <= 0; no se loguean bandas."); return

        bands = [
            ("delta",   1.0,   4.0),
            ("theta",   4.0,   8.0),
            ("alpha",   8.0,  12.0),
            ("beta",   12.0,  25.0),
            ("gamma1", 25.0,  59.0),
            ("gamma2", 61.0, 120.0),
            ("HFO1",  121.0, 250.0),
            ("HFO2",  251.0, 490.0),
        ]
        parts = []
        self._log("-" * 40) # Separador para los logs de bandas
        for name, lo, hi in bands:
            val = bsum(lo, hi) / Ptot
            parts.append(val)
            self._log(f"Band {name:6s} [{lo:>5.1f}-{hi:>6.1f}] -> {val:.4f}")

        total_parts = sum(parts)
        self._log(f"Suma bandas (δ+θ+α+β+γ1+γ2+HFO1+HFO2) = {total_parts:.4f} "
                  f"({'≈ 1.0' if edges_mode=='exclusive' else 'puede ser >1 por bordes inclusivos'})")
        self._log("-" * 40)


    # ---------- DATA ----------
    def _load_trials_from_store(self):
        if not self.mainwin:
            return None, None, None
        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
            return None, None, None

        self.active_signal = store.get_active_signal()
        if not self.active_signal or not getattr(self.active_signal, "trials_dataset", None):
            self._log("No hay señal activa o no tiene TrialDataset.")
            return None, None, None

        td = self.active_signal.trials_dataset[-1]
        fs = float(getattr(td, "sampling_rate", 0.0))
        X = np.asarray(getattr(td, "trials", None), dtype=np.float64) 	# (Ns, T)
        ch = getattr(td, "channel_name", "")
        if X is None or X.ndim != 2 or fs <= 0:
            self._log("TrialDataset inválido (fs<=0 o trials no 2D).")
            return None, None, None

        self._log(f"Trials: Ns={X.shape[0]}, T={X.shape[1]}, fs={fs}")
        return fs, X, ch

    # ---------- Welch ----------
    def _compute_psd(self, X: np.ndarray, fs: float, target_fs: float,
                     window: str, nperseg: int, noverlap: int, nfft: int, detrend: str):
        # Downsample entero estilo MATLAB
        srt = max(1, int(round(fs / float(target_fs)))) if (target_fs and target_fs > 0) else 1
        fs_eff = fs / srt
        Xds = X[::srt, :] if srt > 1 else X

        # Limpiar NaN/Inf
        np.nan_to_num(Xds, copy=False, nan=0.0, posinf=0.0, neginf=0.0)

        Ns_eff = Xds.shape[0]
        if nperseg > Ns_eff:
            nperseg = Ns_eff
        if noverlap >= nperseg:
            noverlap = nperseg // 2
        if nfft < nperseg:
            nfft = nperseg
        detrend_arg = False if detrend == "none" else detrend

        self._log(f"Welch params: fs_eff={fs_eff}, window={window}, nperseg={nperseg}, "
                  f"noverlap={noverlap}, nfft={nfft}, detrend={detrend_arg}, axis=0")

        freq, pxx = welch(
            Xds, fs=fs_eff, window=window, nperseg=nperseg, noverlap=noverlap,
            nfft=nfft, detrend=detrend_arg, scaling='density', axis=0
        )

        pxx = np.nan_to_num(pxx, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64) 	# (Nf, T)
        freq = freq.astype(np.float64)
        self._log(f"PSD: srt={srt}, fs_eff={fs_eff:.3f} Hz, Nf={freq.size}, T_calc={pxx.shape[1]}")
        return freq, pxx, fs_eff

    # ---------- util ----------
    def _notify(self, msg: str):
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(msg, 3000)
                return
            except Exception:
                pass
        self._log(msg)
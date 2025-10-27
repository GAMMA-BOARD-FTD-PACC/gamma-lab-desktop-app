from matplotlib import pyplot as plt
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
import numpy as np
import pywt

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset
from plugins.analysis.time_frequency.wavelet.wavelet_plugin_ui import Ui_Wavelet


class Wavelet_plugin(IPlugin):
    """Plugin de análisis tiempo-frecuencia (Wavelet CWT con PyWavelets + visualización VTK)."""

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.ui = None
        self._context_view = None
        self._vtk_renderer = None

    # =====================================================
    # === Ciclo de vida del plugin
    # =====================================================
    def initialize(self, kernel):
        print("Inicializando Wavelet")

    def process(self, data: any):
        print(f"Wavelet recibió datos: {data}")
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(f"Wavelet procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando Wavelet")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("Wavelet tiene acceso a MainWindow")

    def stop(self):
        print("[Wavelet] stop")
        if self.vtk_widget and self.vtk_widget.GetRenderWindow():
            interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
            if interactor:
                interactor.Disable()

    # =====================================================
    # === Creación del widget UI + VTK
    # =====================================================
    def get_widget(self, parent=None):
        if self.widget is not None:
            self.widget.setParent(parent)
            return self.widget

        self.widget = QWidget(parent)
        self.ui = Ui_Wavelet()
        self.ui.setupUi(self.widget)

        # --- Configuración de interfaz ---
        self.ui.sampleDensitySpinBox.setRange(1, 10000)
        self.ui.sampleDensitySpinBox.setValue(1000)

        self.ui.highFrequencySpinBox.setRange(0, 10000)
        self.ui.highFrequencySpinBox.setValue(500)

        self.ui.lowFrequencySpinBox.setRange(0, 10000)
        self.ui.lowFrequencySpinBox.setValue(1)

        self.ui.cyclesSpinBox.setRange(1, 20)
        self.ui.cyclesSpinBox.setValue(2)

        # Normalización
        self.ui.normalizeComboBox.setEnabled(False)
        self.ui.normalizeComboBox.addItems(["Z-Score", "Percent change", "Relative power", "Min-Max"])
        self.ui.normalizeCheckBox.stateChanged.connect(
            lambda state: self.ui.normalizeComboBox.setEnabled(state == Qt.Checked)
        )

        # Escalado
        self.ui.scaleComboBox.setEnabled(False)
        self.ui.scaleComboBox.addItems(["Log"])
        self.ui.scaleCheckBox.stateChanged.connect(
            lambda state: self.ui.scaleComboBox.setEnabled(state == Qt.Checked)
        )

        # --- Contenedor VTK ---
        vtk_layout = QVBoxLayout(self.ui.frame)
        vtk_layout.setContentsMargins(0, 0, 0, 0)
        self.vtk_widget = QVTKRenderWindowInteractor(self.ui.frame)
        vtk_layout.addWidget(self.vtk_widget)

        self.renwin = self.vtk_widget.GetRenderWindow()
        self._context_view = vtk.vtkContextView()
        self._context_view.SetRenderWindow(self.renwin)
        self._context_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        try:
            self.vtk_widget.Initialize()
        except Exception as e:
            print(f"[Wavelet] Error inicializando interactor: {e}")

        # Botón principal
        self.ui.createWaveletButton.clicked.connect(self.on_create_wavelet)
        return self.widget

    # =====================================================
    # === Utilidades
    # =====================================================
    def _log(self, *args):
        print("[Wavelet]", *args)

    def ensure_vtk(self):
        """Asegura que la vista 2D de VTK esté correctamente inicializada."""
        if not self.vtk_widget or not self.renwin:
            return
        if not self._context_view:
            self._context_view = vtk.vtkContextView()
            self._context_view.SetRenderWindow(self.renwin)
        renderer = self._context_view.GetRenderer()
        renderer.SetBackground(0.98, 0.98, 0.98)
        self._vtk_renderer = renderer

    # =====================================================
    # === Lógica principal: CWT + Render
    # =====================================================
    def on_create_wavelet(self):
        """Carga la señal activa, calcula el CWT y renderiza el escalograma."""
        if not self.mainwin:
            return

        active_signal = self._get_active_signal()
        if active_signal is None:
            QMessageBox.warning(self.widget, "Error", "No hay señal activa para calcular el Wavelet.")
            return

        channel_name = active_signal.channel_names[0]
        trials = active_signal.get_active_trials(active_signal.name, channel_name)

        t = trials.time_rel
        if t is None or len(t) < 2:
            QMessageBox.warning(self.widget, "Error", "No hay información de tiempo suficiente.")
            return

        try:
            sig = trials.trials[:, 0] if trials.trials.ndim == 2 else np.ravel(trials.trials)
        except Exception:
            sig = np.array(trials.trials, dtype=float).ravel()

        sig = np.nan_to_num(np.asarray(sig).flatten(), nan=0.0, posinf=0.0, neginf=0.0)
        fs_calculado = round(1.0 / (t[1] - t[0]), 3)

        fs = self.ui.sampleDensitySpinBox.value()
        fmin = self.ui.lowFrequencySpinBox.value()
        fmax = self.ui.highFrequencySpinBox.value()
        cycles = float(self.ui.cyclesSpinBox.value())
        normalize = self.ui.normalizeCheckBox.isChecked()
        scaled = self.ui.scaleCheckBox.isChecked()
        norm_method = self.ui.normalizeComboBox.currentText().lower()
        scale_method = self.ui.scaleComboBox.currentText().lower()

        self._log(f"fmin={fmin}, fmax={fmax}, cycles={cycles}, fs usado={fs}")
        scalogram, times, freqs = self.compute_wavelet(sig, fs_calculado, fs, fmin, fmax, cycles)

        if normalize:
            scalogram = self.normalize_tf(scalogram, norm_method)
        if scaled:
            freqs = self.scale_tf(freqs, scale_method)

        self.ensure_vtk()
        print(np.max(scalogram), np.min(scalogram))
        self.render_scalogram(times, freqs, scalogram, "Scalogram Wavelet (Morlet)", scaled)

    # =====================================================
    # === Cálculo del Wavelet
    # =====================================================
    def compute_wavelet(self, sig, fs_calculado, fs, fmin, fmax, num_cycles):
        """Calcula la transformada continua de wavelet (Morlet compleja)."""
        freq_seg = 2 * int(fmax - fmin)
        factor = int(round(fs_calculado / fs))
        sig = sig[::factor]

        freq_axis = np.linspace(fmin, fmax, freq_seg)[::-1]
        wavelet = f"cmor{num_cycles}-1.0"
        central_freq = pywt.central_frequency(wavelet)
        scales = central_freq * fs / freq_axis

        coef, _ = pywt.cwt(sig, scales, wavelet, sampling_period=1/fs)
        scalogram = np.abs(coef)
        time_axis = np.arange(len(sig)) / fs

        return scalogram, time_axis, freq_axis

    # =====================================================
    # === Normalización y Escalado
    # =====================================================
    def normalize_tf(self, tf, method="z-score"):
        base_mean = np.mean(tf, axis=1, keepdims=True)
        base_std = np.std(tf, axis=1, ddof=0, keepdims=True)
        base_min = round(np.min(tf), 3)
        print("base_min:", base_min)
        base_max = round(np.max(tf), 3)
        print("base_max:", base_max)

        if method == "z-score":
            return (tf - base_mean) / base_std

        elif method == "percent change":
            return ((tf - base_mean) / base_mean) * 100

        elif method == "relative power":
            return tf / base_mean

        elif method == "min-max":
            denom = base_max - base_min
            print("denom:", denom)
            print(np.max((tf-base_min)/denom))
            return (tf - base_min) / denom
        else:
            raise ValueError("Método no reconocido.")
    # end def

    def scale_tf(self, freqs, method="log"):
        if method == "log":
            return np.log10(freqs)
        raise ValueError("Método no reconocido. Use 'log'.")
    # end def

    # =====================================================
    # === Render escalograma 2D en VTK
    # =====================================================
    def render_scalogram(self, t, freqs, scalogram, title="Scalogram", log_scale=False):
        if not self.vtk_widget:
            return

        context_view = self._context_view
        scene = context_view.GetScene()
        scene.ClearItems()

        Z = np.flipud(np.nan_to_num(scalogram.astype(np.float32)))
        n_freqs, n_times = Z.shape

        t0, t_end = float(t[0]), float(t[-1])
        dt = (t_end - t0) / n_times if n_times > 1 else 1.0
        f0, f_end = float(freqs[0]), float(freqs[-1])
        df = (f_end - f0) / n_freqs if n_freqs > 1 else 1.0

        img = vtk.vtkImageData()
        img.SetDimensions(n_times, n_freqs, 1)
        img.SetSpacing(dt, df, 1.0)
        img.SetOrigin(t0, f0, 0.0)
        img.AllocateScalars(vtk.VTK_FLOAT, 1)
        for j in range(n_freqs):
            for i in range(n_times):
                img.SetScalarComponentFromFloat(i, j, 0, 0, Z[j, i])
        img.Modified()

        # Calcula límites
        vmin, vmax = np.min(Z), np.max(Z)
        vmin, vmax = np.round([vmin, vmax], 2)

        lut = self._build_lut("viridis", vmin, vmax)
        chart = vtk.vtkChartHistogram2D()
        chart.SetInputData(img, 0)
        chart.SetTransferFunction(lut)

        ax_bottom, ax_left = chart.GetAxis(vtk.vtkAxis.BOTTOM), chart.GetAxis(vtk.vtkAxis.LEFT)
        ax_bottom.SetTitle("Time (s)")
        ax_left.SetTitle("Frequency (Hz)")
        ax_bottom.SetRange(t0, t_end)
        ax_left.SetRange(f0, f_end)
        ax_bottom.GetLabelProperties().SetColor(0, 0, 0)
        ax_left.GetLabelProperties().SetColor(0, 0, 0)

        scene.AddItem(chart)
        context_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)
        context_view.GetRenderWindow().Render()

        self._log("Escalograma renderizado correctamente.")

    # =====================================================
    # === Colormap LUT
    # =====================================================
    def _build_lut(self, mode: str, vmin: float, vmax: float) -> vtk.vtkLookupTable:
        N = 256
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(N)
        lut.SetRange(vmin, vmax)
        lut.Build()

        for i in range(N):
            t = i / (N - 1)

            # --- Jet clásico suavizado ---
            if t < 0.125:
                r, g, b = 0, 0, 0.5 + 0.5 * (t / 0.125)      # azul oscuro → azul brillante
            elif t < 0.375:
                r, g, b = 0, (t - 0.125) / 0.25, 1           # azul → cyan
            elif t < 0.625:
                r, g, b = (t - 0.375) / 0.25, 1, 1 - (t - 0.375) / 0.25  # cyan → verde → amarillo
            elif t < 0.875:
                r, g, b = 1, 1 - (t - 0.625) / 0.25, 0        # amarillo → rojo
            else:
                r, g, b = 1, 0.15 * (1 - (t - 0.875) / 0.125), 0  # rojo brillante, sin oscurecer

            # Suavizado leve de saturación
            r = 0.9 * r + 0.03
            g = 0.9 * g + 0.03
            b = 0.9 * b + 0.03

            lut.SetTableValue(i, r, g, b, 1.0)

        return lut

    # =====================================================
    # === Convertir LUT a CTF
    # =====================================================
    def _lut_to_ctf(self, lut: vtk.vtkLookupTable) -> vtk.vtkColorTransferFunction:
        ctf = vtk.vtkColorTransferFunction()
        ctf.ClampingOn()
        n = lut.GetNumberOfTableValues()
        if n <= 0:
            return ctf
        vmin, vmax = lut.GetRange()
        if vmax == vmin:
            vmin -= 0.5
            vmax += 0.5
        for i in range(n):
            rgba = lut.GetTableValue(i)
            x = vmin + (vmax - vmin) * (i / (n - 1))
            ctf.AddRGBPoint(x, *rgba[:3])
        return ctf


    def _get_active_signal(self) -> SignalDataset | None:
        """Devuelve la señal activa"""
        try:
            store: DataStore | None = self.mainwin.kernel.get_service("DataStore")
            if store is None:
                QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
                return
            ds = store.get_active_signal() if store else None
            if not ds:
                print("[Average] No hay señal activa registrada en el DataStore.")
                return

            self._log("_get_active_signal:", "ok" if ds else "None")
            return ds
        except Exception as e:
            self._log("_get_active_signal error:", e)
            return None
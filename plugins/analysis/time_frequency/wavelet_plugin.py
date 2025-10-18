from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
import numpy as np
import pywt


class Wavelet_plugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.ui = None
        self._vtk_renderer = None

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
        print("Deteniendo Wavelet")
        self.mainwin = None

    def get_widget(self, parent=None):
        from plugins.analysis.time_frequency.wavelet_plugin_ui import Ui_Wavelet
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Wavelet()
            self.ui.setupUi(self.widget)

            self.ui.highFrequencySpinBox.setRange(0, 10000)
            self.ui.highFrequencySpinBox.setValue(500)

            self.ui.lowFrequencySpinBox.setRange(0, 10000)
            self.ui.lowFrequencySpinBox.setValue(1)


            # --- Configuración del contenedor VTK ---
            vtk_layout = QVBoxLayout(self.ui.frame)
            vtk_layout.setContentsMargins(0, 0, 0, 0)

            self.vtk_widget = QVTKRenderWindowInteractor(self.ui.frame)
            vtk_layout.addWidget(self.vtk_widget)

            self.renwin = self.vtk_widget.GetRenderWindow()
            try:
                self.vtk_widget.Initialize()
            except Exception:
                pass

            self.ui.createWaveletButton.clicked.connect(self.on_create_wavelet)
        else:
            self.widget.setParent(parent)

        return self.widget

    def ensure_vtk(self):
        if self.vtk_widget is None:
            return

        if self.renwin.GetRenderers().GetNumberOfItems() == 0:
            renderer = vtk.vtkRenderer()
            renderer.SetBackground(0.98, 0.98, 0.98)
            self.renwin.AddRenderer(renderer)
        else:
            renderer = self.renwin.GetRenderers().GetFirstRenderer()
            renderer.SetBackground(0.98, 0.98, 0.98)

        self._vtk_renderer = renderer

    # =====================================================
    # ===  HELPER: Colormap LUT (igual que ERP)         ===
    # =====================================================
    def _build_lut(self, mode: str, vmin: float, vmax: float) -> vtk.vtkScalarsToColors:
        mode = (mode or "blue").lower()
        N = 256
        bg = self._vtk_renderer.GetBackground() if self._vtk_renderer else (1.0, 1.0, 1.0)

        def finalize(lut: vtk.vtkLookupTable) -> vtk.vtkLookupTable:
            lut.SetRange(vmin, vmax)
            lut.SetNumberOfTableValues(N)
            lut.Build()
            lut.SetNanColor(*bg, 1.0)
            lut.SetUseBelowRangeColor(True); lut.SetBelowRangeColor(*bg, 1.0)
            lut.SetUseAboveRangeColor(True); lut.SetAboveRangeColor(*bg, 1.0)
            return lut

        # === Azul monocromo (por defecto del ERP)
        if mode in ("blue", "blue_r"):
            light = (0.93, 0.97, 1.00)
            dark  = (0.00, 0.10, 0.60)
            gamma = 0.6
            lut = finalize(vtk.vtkLookupTable())
            for i in range(N):
                s = (i / (N - 1)) ** gamma
                if mode == "blue_r":
                    s = 1.0 - s
                r = light[0] + s * (dark[0] - light[0])
                g = light[1] + s * (dark[1] - light[1])
                b = light[2] + s * (dark[2] - light[2])
                lut.SetTableValue(i, r, g, b, 1.0)
            return lut

        # === Viridis (alternativa más neutra)
        ctf = vtk.vtkColorTransferFunction()
        ctf.ClampingOn()
        ctf.SetRange(vmin, vmax)
        ctf.AddRGBPoint(vmin,                 0.267, 0.005, 0.329)
        ctf.AddRGBPoint((2*vmin+vmax)/3.0,    0.229, 0.322, 0.545)
        ctf.AddRGBPoint((vmin+2*vmax)/3.0,    0.127, 0.566, 0.550)
        ctf.AddRGBPoint(vmax,                 0.993, 0.906, 0.144)

        lut = finalize(vtk.vtkLookupTable())
        gamma = 0.8
        for i in range(N):
            s = (i / (N - 1)) ** gamma
            x = vmin + s * (vmax - vmin)
            r, g, b = ctf.GetColor(x)
            lut.SetTableValue(i, r, g, b, 1.0)
        return lut
    
    def _lut_to_ctf(self, lut):
        """Convierte vtkLookupTable a vtkColorTransferFunction (robusto)."""
        ctf = vtk.vtkColorTransferFunction()
        ctf.ClampingOn()
        n = lut.GetNumberOfTableValues()
        if n <= 0:
            return ctf
        vmin, vmax = lut.GetRange()
        # Si rango inválido, ponemos 0..1
        if vmax == vmin:
            vmin -= 0.5
            vmax += 0.5
        for i in range(n):
            rgba = lut.GetTableValue(i)  # (r,g,b,a)
            r, g, b = rgba[0], rgba[1], rgba[2]
            x = vmin + (vmax - vmin) * (i / (n - 1))
            ctf.AddRGBPoint(x, r, g, b)
        return ctf

    # =====================================================
    # ===  Lógica de cálculo y renderizado del Wavelet  ===
    # =====================================================
    def on_create_wavelet(self):
        """Carga el SignalDataset activo, calcula CWT con PyWavelets y renderiza el escalograma."""
        if not self.mainwin:
            return

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
            return

        active_signal = store.get_active_signal()
        if not active_signal or not active_signal.trials_dataset:
            QMessageBox.warning(self.widget, "Error", "No hay señal activa registrada.")
            return

        td = active_signal.trials_dataset[0]

        # --- Procesar señal ---
        try:
            if td.trials.ndim == 2:
                sig = np.mean(td.trials, axis=0)
            else:
                sig = np.ravel(td.trials)
        except Exception:
            sig = np.array(td.trials, dtype=float).ravel()

        t = td.time_rel
        if t is None or len(t) < 2:
            QMessageBox.warning(self.widget, "Error", "No hay información de tiempo suficiente en el TrialDataset.")
            return

        dt = float(t[1] - t[0])
        fs = 1.0 / dt

        # --- Leer parámetros desde la interfaz ---
        fmin = self.ui.lowFrequencySpinBox.value()
        fmax = self.ui.highFrequencySpinBox.value()
        cycles = float(self.ui.cyclesSpinBox.value())
        n_scales = int(2 * (fmax - fmin))

        scales = np.arange(1, n_scales + 1)
        wavelet_name = f"cmor{cycles}-1.0"

        print(f"[Wavelet] fmin={fmin}, fmax={fmax}, scales={len(scales)}, cycles={cycles}")

        coef, freqs = pywt.cwt(sig, scales, wavelet_name, sampling_period=1/fs)
        scalogram = np.abs(coef) ** 2

        print(f"[Wavelet] scalogram shape: {scalogram.shape}, freqs: {freqs[:5]}...")

        self.ensure_vtk()
        self.render_scalogram(t, freqs, scalogram, title=f"Scalogram - {getattr(td, 'channel_name', '')}")

    def render_scalogram(self, t, freqs, scalogram, title="Scalogram"):
        """Renderiza el escalograma tipo heatmap 2D (tiempo vs frecuencia) con ejes físicos correctos."""
        if not self.vtk_widget:
            return

        if not self._vtk_renderer:
            self.ensure_vtk()

        # === Datos ===
        Z = np.abs(scalogram).astype(np.float32)
        Z = np.nan_to_num(Z)
        n_freqs, n_times = Z.shape

        # --- Reducción opcional si la señal es muy larga ---
        MAX_SAMPLES = 1500
        if n_times > MAX_SAMPLES:
            factor = int(np.ceil(n_times / MAX_SAMPLES))
            Z = Z[:, ::factor]
            t = t[::factor]
            n_times = Z.shape[1]

        # === Crear imagen VTK ===
        img = vtk.vtkImageData()
        img.SetDimensions(n_times, n_freqs, 1)
        img.AllocateScalars(vtk.VTK_FLOAT, 1)

        for j in range(n_freqs):
            for i in range(n_times):
                img.SetScalarComponentFromFloat(i, j, 0, 0, Z[j, i])
        img.Modified()

        # === Colormap (LUT y CTF) ===
        finite = np.isfinite(Z)
        if finite.any():
            vmin, vmax = (
                float(np.percentile(Z[finite], 2)),
                float(np.percentile(Z[finite], 98)),
            )
        else:
            vmin, vmax = (0.0, 1.0)

        lut = self._build_lut("blue", vmin, vmax)
        ctf = self._lut_to_ctf(lut)

        # === Crear vista y gráfico 2D ===
        chart_view = vtk.vtkContextView()
        chart_view.SetRenderWindow(self.renwin)
        chart_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        chart = vtk.vtkChartHistogram2D()
        chart.SetInputData(img, 0)
        chart.SetTransferFunction(ctf)
        chart.SetTitle(title)

        # === Configurar ejes físicos ===
        ax_bottom = chart.GetAxis(vtk.vtkAxis.BOTTOM)
        ax_left = chart.GetAxis(vtk.vtkAxis.LEFT)

        ax_bottom.SetTitle("Time (s)")
        ax_left.SetTitle("Frequency (Hz)")

        # Rango real de tiempo y frecuencia
        ax_bottom.SetRange(float(t[0]), float(t[-1]))
        # Normal: bajas abajo, altas arriba
        # ax_left.SetRange(float(freqs[0]), float(freqs[-1]))
        # Si prefieres invertir el eje Y:
        ax_left.SetRange(float(10), float(500))
        ax_bottom.SetBehavior(vtk.vtkAxis.FIXED)
        ax_left.SetBehavior(vtk.vtkAxis.FIXED)

        # === Render final ===
        scene = chart_view.GetScene()
        scene.ClearItems()
        scene.AddItem(chart)

        self.renwin.Render()
        print("[Wavelet] Escalograma renderizado correctamente con ejes físicos y LUT.")

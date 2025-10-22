from matplotlib import pyplot as plt
from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
import numpy as np
import pywt
from scipy.signal import resample

from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset


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
        print("Deteniendo Wavelet")
        self.mainwin = None

    # =====================================================
    # === Creación del widget UI + VTK
    # =====================================================
    def get_widget(self, parent=None):
        from plugins.analysis.time_frequency.wavelet_plugin_ui import Ui_Wavelet
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Wavelet()
            self.ui.setupUi(self.widget)

            # Parámetros iniciales de la interfaz
            self.ui.highFrequencySpinBox.setRange(0, 10000)
            self.ui.highFrequencySpinBox.setValue(500)

            self.ui.lowFrequencySpinBox.setRange(0, 10000)
            self.ui.lowFrequencySpinBox.setValue(1)

            self.ui.cyclesSpinBox.setRange(1, 20)
            self.ui.cyclesSpinBox.setValue(2)

            self.ui.sampleDensitySpinBox.setRange(1, 10000)
            self.ui.sampleDensitySpinBox.setValue(1000)

            # --- Contenedor VTK ---
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

    # =====================================================
    # === Utilidades
    # =====================================================
    def _log(self, *args):
        print("[Wavelet]", *args)

    def ensure_vtk(self):
        """Prepara un renderer VTK si no existe."""
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

        # --- Verificación de datos ---
        t = trials.time_rel
        if t is None or len(t) < 2:
            QMessageBox.warning(self.widget, "Error", "No hay información de tiempo suficiente.")
            return

        print("los trials")
        # print(trials.trials [:30, :5])

        try:
            if trials.trials.ndim == 2:
                sig = np.mean(trials.trials, axis=1)
            else:
                sig = np.ravel(trials.trials)
        except Exception:
            sig = np.array(trials.trials, dtype=float).ravel()

        # Frecuencia de muestreo real
        fs_calculado = round(1.0 / (t[1] - t[0]), 3)

        self._log(f"Signal len={len(sig)}, fs_calculado={fs_calculado} Hz, t=[{t[0]}, {t[-1]}]")

        # --- Parámetros de interfaz ---
        fmin = self.ui.lowFrequencySpinBox.value()
        fmax = self.ui.highFrequencySpinBox.value()
        cycles = float(self.ui.cyclesSpinBox.value())
        fs = self.ui.sampleDensitySpinBox.value()

        self._log(f"fmin={fmin}, fmax={fmax}, cycles={cycles}, fs usado={fs}")

        # --- Calcular Wavelet ---
        scalogram, times, freqs = self.compute_wavelet(sig, fs_calculado, fs, fmin, fmax, cycles)

        plt.figure(figsize=(10, 6))
        plt.imshow(
            scalogram,
            extent=[times[0], times[-1], freqs[0], freqs[-1]],
            cmap='jet',
            aspect='auto',
            origin='lower'
        )
        plt.xlabel('Tiempo [s]')
        plt.ylabel('Frecuencia [Hz]')
        plt.title('Escalograma Wavelet (Morlet)')
        plt.gca().invert_yaxis()
        plt.colorbar(label='Magnitud')
        plt.show()

        # --- Mostrar información ---
        print("scalogram shape:", scalogram.shape)
        print("freqs head:", freqs[:10])
        print("times head:", times[:10])

        # --- Renderizar ---
        self.ensure_vtk()
        # self.render_scalogram(times, freqs, scalogram, title=f"Scalogram - {channel_name}")

    # =====================================================
    # === Cálculo del Wavelet
    # =====================================================
    def compute_wavelet(
        self,
        sig,
        fs_calculado,
        fs,
        fmin,
        fmax,
        num_cycles
    ):
        """
        Calcula una transformada tipo Morse Wavelet (aproximada con Morlet compleja)
        de forma similar a f_MorseAWTransformMatlab.m.

        Retorna:
            scalogram : matriz tiempo-frecuencia
            time_axis : vector de tiempo
            freq_axis : vector de frecuencias (descendente)
        """

        sig = np.asarray(sig).flatten()

        # --- Reemplazar NaN e Infs por 0 ---
        if np.isnan(sig).any() or np.isinf(sig).any():
            sig = np.nan_to_num(sig, nan=0.0, posinf=0.0, neginf=0.0)
        
        # --- Número de segmentos de frecuencia ---
        freq_seg = 2 * int(fmax - fmin)

        # --- Reducción de muestreo
        reduction_ratio = fs / fs_calculado
        num_samples = int(len(sig) * reduction_ratio)

        # Remuestreo proporcional
        sig = resample(sig, num_samples)
        print(f"[Wavelet] Señal remuestreada a fs={fs} Hz, len={len(sig)})")

        # --- Vector de frecuencias ---
        freq_axis = np.linspace(fmin, fmax, freq_seg)
        freq_axis = np.flip(freq_axis)

        # --- Definir wavelet (Morlet compleja) ---
        wavelet = f"cmor{num_cycles}-1.0"
        central_freq = pywt.central_frequency(wavelet)
        print(f"freq_axis: min={freq_axis.min():.4f}, max={freq_axis.max():.4f}")
        scales = central_freq * fs / freq_axis

        # --- Transformada Wavelet Continua ---
        coef, freqs = pywt.cwt(sig, scales, wavelet, sampling_period=1/fs)

        # --- Eje temporal ---
        time_axis = np.arange(len(sig)) / fs

        # --- Escalograma ---
        scalogram = np.abs(coef)

        # --- Retornar ---
        return scalogram, time_axis, freq_axis

    # =====================================================
    # === Render VTK (heatmap 2D)
    # =====================================================
    def render_scalogram(self, t, freqs, scalogram, title="Scalogram"):
        """Renderiza el escalograma tiempo-frecuencia con ejes físicos."""
        if not self.vtk_widget:
            return
        if not self._vtk_renderer:
            self.ensure_vtk()

        # Datos base
        Z = np.abs(scalogram).astype(np.float32)
        Z = np.nan_to_num(Z)
        n_freqs, n_times = Z.shape

        # --- Reducción si la señal es muy larga ---
        # MAX_SAMPLES = 1500
        # if n_times > MAX_SAMPLES:
        #     factor = int(np.ceil(n_times / MAX_SAMPLES))
        #     Z = Z[:, ::factor]
        #     t = t[::factor]
        #     n_times = Z.shape[1]

        # --- Crear imagen VTK ---
        img = vtk.vtkImageData()
        img.SetDimensions(n_times, n_freqs, 1)
        img.AllocateScalars(vtk.VTK_FLOAT, 1)
        for j in range(n_freqs):
            for i in range(n_times):
                img.SetScalarComponentFromFloat(i, j, 0, 0, Z[j, i])
        img.Modified()

        # --- Rango de color ---
        finite = np.isfinite(Z)
        if finite.any():
            vmin, vmax = np.percentile(Z[finite], [2, 98])
        else:
            vmin, vmax = (0.0, 1.0)

        lut = self._build_lut("blue", vmin, vmax)
        ctf = self._lut_to_ctf(lut)

        # --- Configurar gráfico VTK ---
        chart_view = vtk.vtkContextView()
        chart_view.SetRenderWindow(self.renwin)
        chart_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        chart = vtk.vtkChartHistogram2D()
        chart.SetInputData(img, 0)
        chart.SetTransferFunction(ctf)
        chart.SetTitle(title)

        # === Ejes físicos ===
        ax_bottom = chart.GetAxis(vtk.vtkAxis.BOTTOM)
        ax_left = chart.GetAxis(vtk.vtkAxis.LEFT)

        ax_bottom.SetTitle("Time (s)")
        ax_left.SetTitle("Frequency (Hz)")

        # Rango real (tiempo en segundos, frecuencia real)
        # ax_bottom.SetRange(float(t[0]), float(t[-1]))
        ax_left.SetRange(float(freqs[0]), float(freqs[-1]))
        ax_bottom.SetBehavior(vtk.vtkAxis.FIXED)
        ax_left.SetBehavior(vtk.vtkAxis.FIXED)

        # --- Render final ---
        scene = chart_view.GetScene()
        scene.ClearItems()
        scene.AddItem(chart)

        self.renwin.Render()
        self._log("Escalograma renderizado correctamente con ejes físicos y LUT.")

        # =====================================================
    # ===  HELPER: Colormap LUT (igual que ERP)         ===
    # =====================================================
    def _build_lut(self, mode: str, vmin: float, vmax: float) -> vtk.vtkLookupTable:
        """Construye un vtkLookupTable (256 entries) con modo 'blue' o con gradiente similar a viridis.
           Devuelve vtkLookupTable ya preparado con rango (vmin,vmax)."""
        mode = (mode or "blue").lower()
        N = 256
        bg = (1.0, 1.0, 1.0)
        if hasattr(self, "_vtk_renderer") and self._vtk_renderer:
            try:
                bg = self._vtk_renderer.GetBackground()
            except Exception:
                bg = (1.0, 1.0, 1.0)

        def finalize(lut: vtk.vtkLookupTable) -> vtk.vtkLookupTable:
            lut.SetRange(vmin, vmax)
            lut.SetNumberOfTableValues(N)
            lut.Build()
            # colores para NaN / fuera de rango
            lut.SetNanColor(bg[0], bg[1], bg[2], 1.0)
            lut.SetUseBelowRangeColor(True)
            lut.SetBelowRangeColor(bg[0], bg[1], bg[2], 1.0)
            lut.SetUseAboveRangeColor(True)
            lut.SetAboveRangeColor(bg[0], bg[1], bg[2], 1.0)
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

        # === Gradiente tipo "viridis"-like para alternativa
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

    def _lut_to_ctf(self, lut: vtk.vtkLookupTable) -> vtk.vtkColorTransferFunction:
        """Convierte un vtkLookupTable (discreto) a vtkColorTransferFunction (continua) para usar en histogram2D."""
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
    # === Data access helper
    # =====================================================
    def _get_active_signal(self) -> SignalDataset | None:
        try:
            store: DataStore | None = self.mainwin.kernel.get_service("DataStore")
            if store is None:
                QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
                return
            ds = store.get_active_signal() if store else None
            if not ds:
                print("[Wavelet] No hay señal activa registrada en el DataStore.")
                return
            return ds
        except Exception as e:
            self._log("_get_active_signal error:", e)
            return None

from matplotlib import pyplot as plt
from PyQt5.QtCore import Qt
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
        from plugins.analysis.time_frequency.wavelet.wavelet_plugin_ui import Ui_Wavelet
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Wavelet()
            self.ui.setupUi(self.widget)

            # Parámetros iniciales de la interfaz
            ## Densidad de muestreo
            self.ui.sampleDensitySpinBox.setRange(1, 10000)
            self.ui.sampleDensitySpinBox.setValue(1000)

            # Frecuencias
            self.ui.highFrequencySpinBox.setRange(0, 10000)
            self.ui.highFrequencySpinBox.setValue(500)

            self.ui.lowFrequencySpinBox.setRange(0, 10000)
            self.ui.lowFrequencySpinBox.setValue(1)

            # Tiempos
            self.ui.startSpinBox.setRange(0, 1000)
            self.ui.startSpinBox.setDecimals(2)
            self.ui.startSpinBox.setSingleStep(0.1)
            self.ui.startSpinBox.setValue(0)

            self.ui.finalSpinBox.setRange(0, 1000)
            self.ui.finalSpinBox.setDecimals(2)
            self.ui.finalSpinBox.setSingleStep(0.1)
            self.ui.finalSpinBox.setValue(2)

            # Ciclos
            self.ui.cyclesSpinBox.setRange(1, 20)
            self.ui.cyclesSpinBox.setValue(2)

            # Normalización
            self.ui.normalizeComboBox.setEnabled(False)
            self.ui.normalizeComboBox.addItems([
                "Z-Score",
                "Percent change",
                "Relative power"
            ])
            self.ui.normalizeCheckBox.stateChanged.connect(
                lambda state: self.ui.normalizeComboBox.setEnabled(state == Qt.Checked)
            )

            # Escalado
            self.ui.scaleComboBox.setEnabled(False)
            self.ui.scaleComboBox.addItems([
                "Log"
            ])
            self.ui.scaleCheckBox.stateChanged.connect(
                lambda state: self.ui.scaleComboBox.setEnabled(state == Qt.Checked)
            )

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
        fs = self.ui.sampleDensitySpinBox.value()
        fmin = self.ui.lowFrequencySpinBox.value()
        fmax = self.ui.highFrequencySpinBox.value()
        start = self.ui.startSpinBox.value()
        end = self.ui.finalSpinBox.value()
        cycles = float(self.ui.cyclesSpinBox.value())
        normalize = self.ui.normalizeCheckBox.isChecked()
        scaled = self.ui.scaleCheckBox.isChecked()
        norm_method = self.ui.normalizeComboBox.currentText().lower()
        scale_method = self.ui.scaleComboBox.currentText().lower()

        self._log(f"fmin={fmin}, fmax={fmax}, cycles={cycles}, fs usado={fs}")

        # --- Calcular Wavelet ---
        scalogram, times, freqs = self.compute_wavelet(sig, fs_calculado, fs, start, end, fmin, fmax, cycles)

        # --- Normalización ---
        if normalize:
            scalogram = self.normalize_tf(scalogram, norm_method)
        # end if

        # --- Escalado logarítmico ---
        if scaled:
            freqs = self.scale_tf(freqs, scale_method)
        # end if

        # plt.figure(figsize=(10, 6))
        # plt.imshow(
        #     scalogram,
        #     extent=[times[0], times[-1], freqs[0], freqs[-1]],
        #     cmap='jet',
        #     aspect='auto',
        #     origin='lower'
        # )
        # plt.xlabel('Tiempo [s]')
        # plt.ylabel('Frecuencia [Hz]')
        # plt.title('Escalograma Wavelet (Morlet)')
        # plt.gca().invert_yaxis()
        # plt.colorbar(label='Magnitud')
        # plt.show()
# 
        # # --- Mostrar información ---
        # print("scalogram shape:", scalogram.shape)

        # --- Renderizar ---
        self.ensure_vtk()
        self.render_scalogram(times, freqs, scalogram, title=f"Scalogram Wavelet (Morlet)", log_scale=scaled)

    # =====================================================
    # === Cálculo del Wavelet
    # =====================================================
    def compute_wavelet(
        self,
        sig,
        fs_calculado,
        fs,
        start,
        end,
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
        sig_segment = sig[int(start * fs):int(end * fs)]
        coef, freqs = pywt.cwt(sig_segment, scales, wavelet, sampling_period=1/fs)

        # --- Eje temporal ---
        time_axis = np.arange(int(start * fs), int(start * fs) + len(sig_segment)) / fs
        # time_axis = np.arange(len(sig)) / fs

        # --- Escalograma ---
        scalogram = np.abs(coef)

        # --- Retornar ---
        return scalogram, time_axis, freq_axis

    # =====================================================
    # === Normalize and scale
    # =====================================================
    
    def normalize_tf(self, tf, method="z-score"):
        """
        Normaliza una matriz tiempo-frecuencia según el método indicado.
        """

        base_mean = np.mean(tf, axis=1, keepdims=True)
        base_std  = np.std(tf, axis=1, ddof=0, keepdims=True)
        base_power = np.mean(tf, axis=1, keepdims=True)

        if method == "z-score":
            tf_norm = (tf - base_mean) / base_std
        elif method == "percent change":
            tf_norm = ((tf - base_mean) / base_mean) * 100
        elif method == "relative power":
            tf_norm = tf / base_power
        else:
            raise ValueError("Método no reconocido. Use 'z-score', 'percent change' o 'relative power'.")
        
        return tf_norm
    # end def

    def scale_tf(self, freqs, method="log"):
        """
        Escala un vector de frecuencias según el método indicado.
        """

        if method == "log":
            freqs_scaled = np.log10(freqs)

        else:
            raise ValueError("Método no reconocido. Use 'log'.")
        
        return freqs_scaled
    # end def

    # =====================================================
    # === Render VTK (heatmap 2D)
    # =====================================================
    def render_scalogram(self, t, freqs, scalogram, title="Scalogram", log_scale=False):
        """Renderiza el escalograma con ejes y barra de color."""
        if not self.vtk_widget:
            return
        if not self._vtk_renderer:
            self.ensure_vtk()

        self._vtk_renderer.RemoveAllViewProps()

        # --- Preparar la imagen ---
        Z = np.abs(scalogram).astype(np.float32)
        Z = np.nan_to_num(Z)
        Z = np.flipud(Z)  # invertir frecuencias: bajas abajo
        n_freqs, n_times = Z.shape

        # --- Crear vtkImageData ---
        img = vtk.vtkImageData()
        img.SetDimensions(n_times, n_freqs, 1)
        img.AllocateScalars(vtk.VTK_FLOAT, 1)
        
        for j in range(n_freqs):
            for i in range(n_times):
                img.SetScalarComponentFromFloat(i, j, 0, 0, Z[j, i])

        # --- LUT colores suavizados tipo jet ---
        vmin, vmax = np.percentile(Z, [2, 98])
        lut = self._build_lut("jet_smooth", vmin, vmax)

        # --- ImageActor ---
        image_actor = vtk.vtkImageActor()
        image_actor.GetMapper().SetInputData(img)
        image_actor.GetProperty().SetLookupTable(lut)
        image_actor.GetProperty().UseLookupTableScalarRangeOn()
        image_actor.SetScale(1.0, 1.0, 1.0)

        self._vtk_renderer.AddActor(image_actor)

        # --- Crear ejes ---
        axes = vtk.vtkCubeAxesActor()
        axes.SetBounds(0, n_times-1, 0, n_freqs-1, 0, 0)
        axes.SetCamera(self._vtk_renderer.GetActiveCamera())

        # Títulos de los ejes
        axes.SetXTitle("Time (s)")
        axes.SetYTitle("Frequency (Hz)")
        axes.SetZTitle("Magnitude")

        # Propiedades de los títulos
        axes.GetXAxesTitleProperty().SetFontSize(14)
        axes.GetYAxesTitleProperty().SetFontSize(14)
        axes.GetZAxesTitleProperty().SetFontSize(14)

        # Propiedades de las etiquetas
        axes.GetXAxesLabelProperty().SetFontSize(12)
        axes.GetYAxesLabelProperty().SetFontSize(12)
        axes.GetZAxesLabelProperty().SetFontSize(12)

        # Formato de las etiquetas
        axes.SetXLabelFormat("%0.2f")
        axes.SetYLabelFormat("%0.0f")
        axes.SetZLabelFormat("%0.2f")

        self._vtk_renderer.AddActor(axes)

        # --- Propiedades de las etiquetas ---
        for prop in [axes.GetXAxesLabelProperty(), axes.GetYAxesLabelProperty(), axes.GetZAxesLabelProperty()]:
            prop.SetColor(0.0, 0.0, 0.0)
            prop.SetFontSize(12)

        # --- Propiedades de los títulos ---
        for prop in [axes.GetXAxesTitleProperty(), axes.GetYAxesTitleProperty(), axes.GetZAxesTitleProperty()]:
            prop.SetColor(0.0, 0.0, 0.0)
            prop.SetFontSize(14)

        # --- Barra de color (ScalarBar) ---
        scalar_bar = vtk.vtkScalarBarActor()
        scalar_bar.SetLookupTable(lut)
        scalar_bar.SetTitle("Magnitude")
        scalar_bar.GetLabelTextProperty().SetFontSize(12)
        scalar_bar.GetTitleTextProperty().SetFontSize(14)
        scalar_bar.SetOrientationToVertical()
        scalar_bar.SetPosition(0.85, 0.1)  
        scalar_bar.SetWidth(0.05) 
        scalar_bar.SetHeight(0.7)
        scalar_bar.GetLabelTextProperty().SetColor(0, 0, 0)
        scalar_bar.GetTitleTextProperty().SetColor(0, 0, 0)
        scalar_bar.GetLabelTextProperty().SetFontSize(12)
        scalar_bar.GetTitleTextProperty().SetFontSize(14)           
        self._vtk_renderer.AddActor2D(scalar_bar)

        # --- Configuración final de cámara y render ---
        self._vtk_renderer.ResetCamera()
        self._vtk_renderer.SetBackground(0.98, 0.98, 0.98)
        self.renwin.Render()
        self._log("Escalograma renderizado con ejes y barra de color.")

        # =====================================================
    # ===  HELPER: Colormap LUT (igual que ERP)         ===
    # =====================================================
    def _build_lut(self, mode: str, vmin: float, vmax: float) -> vtk.vtkLookupTable:
        """Construye un vtkLookupTable tipo 'jet' suavizado (menos intenso que matplotlib)."""
        N = 256
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(N)
        lut.SetRange(vmin, vmax)
        lut.Build()

        for i in range(N):
            t = i / (N - 1)
            # Azul oscuro a cyan
            if t < 0.125:
                r, g, b = 0, 0, 0.6 + 0.3 * t # azul oscuro
            elif t < 0.375:
                r, g, b = 0, 0.8*(t-0.125)*4, 1  # cyan
            elif t < 0.625:
                r, g, b = 0.8*(t-0.375)*4, 1, 0.8*(1-(t-0.375)*4)  # amarillo 
            elif t < 0.875:
                r, g, b = 1, 0.8*(1-(t-0.625)*4), 0  # rojo
            else:
                r, g, b = 0.9, 0, 0  # rojo final
            lut.SetTableValue(i, r, g, b, 1.0)

        return lut
    # end def


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

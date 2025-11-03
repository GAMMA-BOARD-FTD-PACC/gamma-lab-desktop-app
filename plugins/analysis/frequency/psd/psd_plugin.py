import sys
import numpy as np
import vtk
from PyQt5 import QtWidgets, QtCore
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from scipy.signal import welch

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
# Importar nuestra UI y el adaptador VTK
from plugins.analysis.frequency.psd.psd_plugin_ui import Ui_Psd
from core.vtk_adapters.adapters import trials_matrix_to_vtk_table

class Psd_plugin(IPlugin):
    """
    Plugin para calcular la Densidad Espectral de Potencia (PSD)
    con modos seleccionables: All Trials, Average, Individual.
    """
    
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.ui: Ui_Psd | None = None

        # VTK
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None
        self.chart: vtk.vtkChartXY | None = None
        self.vtk_menu: VTKContextMenu | None = None


    def stop(self):
        self._log("stop() - cleanup VTK")
        if self.vtk_interactor:
            self.vtk_interactor.Disable()
        
    def process(self, data):
        if self.vtk_interactor:
            self.vtk_interactor.Enable()
        self._log(f"[PSD] Process: enable {data}")

    def get_widget(self, parent=None):
        if self.widget is None:
            self._log("get_widget(): creando UI")
            self.ui = Ui_Psd()
            self.widget = QtWidgets.QWidget(parent)
            self.ui.setupUi(self.widget)
            self.alerts.parent = self.widget

            self._log("UI creada. plotArea:", bool(self.ui.plotArea),
                      "panel:", bool(self.ui.panel),
                      "splitter:", bool(self.ui.splitter))
            
            self._ensure_vtk()
            self._inject_detrend_controls() # Inyectar Detrend
            self._wire_ui()
            self._init_defaults()  # Fija los defaults estilo MATLAB

            # logs post-show (dimensiones reales)
            QtCore.QTimer.singleShot(0, self._log_sizes)
        else:
            self.widget.setParent(parent)
        return self.widget

    def _log_sizes(self):
        if self.widget:
            self._log(f"Widget size={self.widget.size().width()}x{self.widget.size().height()}")
        if self.ui and self.ui.plotArea:
            self._log(f"plotArea size={self.ui.plotArea.size().width()}x{self.ui.plotArea.size().height()}")
    
    # --- NUEVOS MÉTODOS DE CONTROL UI ---
    def _inject_detrend_controls(self):
        """Crea y añade el ComboBox para seleccionar Detrend."""
        lbl = QtWidgets.QLabel("Detrend")
        cmbo = QtWidgets.QComboBox()
        cmbo.addItems(["none", "constant", "linear"])
        self.ui.detrendComboBox = cmbo
        # Intenta insertarlo en el layout de Welch
        try:
            self.ui.formLayoutWelch.addRow(lbl, cmbo)
        except AttributeError:
             # Fallback si el layout no existe (si el UI no tiene el nombre formLayoutWelch)
            if self.ui.panel and self.ui.panel.layout():
                self.ui.panel.layout().addWidget(lbl)
                self.ui.panel.layout().addWidget(cmbo)
        self.ui.detrendComboBox.setCurrentText("none")

    def _init_defaults(self):
        """Fija defaults estilo MATLAB y establece rango de ploteo amplio."""
        # Window: hamming
        try:
            idx = self.ui.windowComboBox.findText("hamming", QtCore.Qt.MatchFixedString)
            if idx >= 0:
                self.ui.windowComboBox.setCurrentIndex(idx)
        except Exception:
            pass
        # nperseg: 256, noverlap: 128, nfft: 256
        self.ui.npersegSpinBox.setValue(256)
        self._sync_noverlap() # Llama a _sync_noverlap que pondrá noverlap=128 y nfft=256
        # Detrend: none
        if hasattr(self.ui, "detrendComboBox"):
            self.ui.detrendComboBox.setCurrentText("none")
            
        # Rango de Ploteo por Defecto (Low=0.0, High=500.0)
        self.ui.lowFrecuencyDoubleSpinBox.setValue(0.0)
        self.ui.highFrecuencyDoubleSpinBox.setValue(500.0)
        
        # Modo: Individual, Trial: 0
        try:
            midx = self.ui.modeComboBox.findText("Individual", QtCore.Qt.MatchFixedString)
            if midx >= 0:
                self.ui.modeComboBox.setCurrentIndex(midx)
        except Exception:
            pass
        self.ui.trialIndexSpinBox.setValue(0)
    # --- FIN NUEVOS MÉTODOS UI ---

    def _wire_ui(self):
        self._log("wire ui")
        self.ui.pushButton.clicked.connect(self._on_calculate_clicked)
        self.ui.lowFrecuencyDoubleSpinBox.valueChanged.connect(self._sync_range)
        self.ui.highFrecuencyDoubleSpinBox.valueChanged.connect(self._sync_range)
        
        # Sincronizar noverlap con nperseg
        self.ui.npersegSpinBox.valueChanged.connect(self._sync_noverlap)
        
        # Conectar el ComboBox de modo
        self.ui.modeComboBox.currentTextChanged.connect(self._on_mode_changed)

    def _on_mode_changed(self, mode_text: str):
        """ Muestra u oculta el selector de trial individual. """
        is_individual = (mode_text == "Individual")
        self.ui.trialIndexLabel.setVisible(is_individual)
        self.ui.trialIndexSpinBox.setVisible(is_individual)
        
        # Habilitamos el spinbox solo si está visible y hay trials cargados
        num_trials = self.ui.trialIndexSpinBox.maximum() + 1
        self.ui.trialIndexSpinBox.setEnabled(is_individual and num_trials > 0)

    def _sync_noverlap(self):
        """Ajusta noverlap a la mitad de nperseg por defecto."""
        nperseg = self.ui.npersegSpinBox.value()
        self.ui.noverlapSpinBox.setValue(nperseg // 2)
        # Asegurar que nfft también siga a nperseg (comportamiento común)
        self.ui.nfftSpinBox.setValue(nperseg)

    # ------- VTK -------
    def _ensure_vtk(self, *args): # Se eliminan los argumentos ya que no se usan
        # (Sin cambios, idéntico al anterior)
        self._log("ensure_vtk(): enter")
        if self.vtk_interactor:
             self.ui.plotArea.layout().addWidget(self.vtk_interactor)
             return

        self.vtk_interactor = QVTKRenderWindowInteractor(self.ui.plotArea)
        self.ui.plotArea.setLayout(QtWidgets.QVBoxLayout())
        self.ui.plotArea.layout().setContentsMargins(0, 0, 0, 0)
        self.ui.plotArea.layout().addWidget(self.vtk_interactor)
        self._log("ensure_vtk(): interactor embebido")

        self.vtk_view = vtk.vtkContextView()
        self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
        self.vtk_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        try:
            self.vtk_interactor.Initialize()
        except Exception:
            pass
        self._log("ensure_vtk(): scheduled init")


    # ------- acciones -------
    def _on_calculate_clicked(self):
        self._log("_on_calculate_clicked()")

        # 1) Cargar trials de la señal activa
        fs, X, ch_name = self._load_trials_from_store()
        if X is None or fs is None:
            self._notify("PSD: No hay trials en la señal activa.")
            # Deshabilitar el selector de trial si fallamos
            self.ui.trialIndexSpinBox.setEnabled(False)
            self.ui.trialIndexSpinBox.setRange(0, 0)
            return
            
        # --- NUEVO: Fija Target Fs y rango como pwelch si no se ha modificado ---
        # Target Fs = fs (sin downsample)
        if self.ui.sampleDensityDoubleSpinBox.value() <= 0:
             self.ui.sampleDensityDoubleSpinBox.setValue(fs)
        # Rango 0..fs/2
        if self.ui.lowFrecuencyDoubleSpinBox.value() >= self.ui.highFrecuencyDoubleSpinBox.value():
            self.ui.lowFrecuencyDoubleSpinBox.setValue(0.0)
            self.ui.highFrecuencyDoubleSpinBox.setValue(fs/2.0)
            
        # --- NUEVO: Actualizar UI con número de trials ---
        num_trials = X.shape[1]
        self.ui.trialIndexSpinBox.setRange(0, num_trials - 1)
        # Habilitar el spinbox si el modo es "Individual"
        is_individual = (self.ui.modeComboBox.currentText() == "Individual")
        self.ui.trialIndexSpinBox.setEnabled(is_individual)


        # 2) Parámetros UI
        try:
            target_fs = float(self.ui.sampleDensityDoubleSpinBox.value())
            lo = float(self.ui.lowFrecuencyDoubleSpinBox.value())
            hi = float(self.ui.highFrecuencyDoubleSpinBox.value())
            
            # Parámetros de Welch
            window = self.ui.windowComboBox.currentText()
            nperseg = self.ui.npersegSpinBox.value()
            noverlap = self.ui.noverlapSpinBox.value()
            nfft = self.ui.nfftSpinBox.value()
            
            # --- NUEVO: Leer Detrend ---
            detrend = self.ui.detrendComboBox.currentText()
            
            # Parámetros de Modo
            mode = self.ui.modeComboBox.currentText()
            trial_idx = self.ui.trialIndexSpinBox.value()

            if lo > hi:
                lo, hi = hi, lo
            
            # 2) Valida parámetros de Welch
            if nperseg <= 1:
                raise ValueError("N-per-seg debe ser > 1.")
            if noverlap < 0:
                raise ValueError("N-overlap no puede ser negativo.")
            # El ajuste de noverlap >= nperseg se hace dentro de _compute_psd (más seguro).
            
        except Exception as e:
            self.alerts.error(f"Error de Parámetros: {str(e)}")
            return

        # 3) PSD (Siempre calculamos para todos los trials)
        try:
            # --- MODIFICADO: Pasar detrend al cálculo ---
            freq, power_all_trials, fs_eff = self._compute_psd(
                X, fs, target_fs, window, nperseg, noverlap, nfft, detrend
            )
            # power_all_trials tiene forma (Nf, T)
            
        except Exception as e:
            self._log(f"Error en _compute_psd: {e}")
            self.alerts.error(f"No se pudo calcular la PSD: {e}")
                                 
            return
            
        # Seleccionar qué plotear basado en el modo
        power_to_plot = None
        plot_title = ""
        
        if mode == "All Trials":
            power_to_plot = power_all_trials
            plot_title = f"PSD (All Trials) - {ch_name}"
            
        elif mode == "Average":
            # Calcular el promedio por frecuencia (eje 1)
            power_to_plot = np.mean(power_all_trials, axis=1, keepdims=True)
            plot_title = f"PSD (Average) - {ch_name}"
            
        elif mode == "Individual":
            if not (0 <= trial_idx < num_trials):
                self._notify(f"Error: Índice de trial {trial_idx} fuera de rango.")
                return
            # Seleccionar solo la columna del trial
            power_to_plot = power_all_trials[:, trial_idx:trial_idx+1]
            plot_title = f"PSD (Trial {trial_idx}) - {ch_name}"
            

        # 4) Plot
        if power_to_plot is not None:
            self._plot_psd(freq, power_to_plot, plot_title, lo, hi)
            self._notify(f"PSD ({mode}) listo: fs_eff={fs_eff:.2f} Hz, {freq.size} bins")
        else:
            self._notify(f"Error: Modo de cálculo '{mode}' no reconocido.")


    def _sync_range(self):
        # 4) Pequeño bug de PyQt: Simplifica _sync_range (sin sender())
        lo = float(self.ui.lowFrecuencyDoubleSpinBox.value())
        hi = float(self.ui.highFrecuencyDoubleSpinBox.value())
        if lo > hi:
            # Solo forzamos que hi se ajuste a lo si es menor
            self.ui.highFrecuencyDoubleSpinBox.setValue(lo)
        self._log(f"range sync: low={self.ui.lowFrecuencyDoubleSpinBox.value()}, "
                  f"high={self.ui.highFrecuencyDoubleSpinBox.value()}")

    # ====== DATA ======
    def _load_trials_from_store(self):
        if not self.mainwin:
            return None, None, None

        if self.get_active_signal() is None:
            return None, None, None

        td = self.get_active_trials()

        if td is None or td.trials.size == 0:
            return None, None, None

        fs = float(getattr(td, "sampling_rate", 0.0))
        X = np.asarray(getattr(td, "trials", None), dtype=np.float64) # (Ns, T)
        ch = getattr(td, "channel_name", "")
        if X is None or X.ndim != 2 or fs <= 0:
            self._log("TrialDataset inválido (fs<=0 o trials no 2D).")
            return None, None, None

        self._log(f"Trials: Ns={X.shape[0]}, T={X.shape[1]}, fs={fs}")
        return fs, X, ch

    # ====== PSD Logic ======
    def _compute_psd(self, X: np.ndarray, fs: float, target_fs: float,
                     window: str, nperseg: int, noverlap: int, nfft: int, detrend: str):
        
        Ns, T = X.shape
        # Downsample
        srt = max(1, int(round(fs / float(target_fs)))) if (target_fs and target_fs > 0) else 1
        fs_eff = fs / srt
        Xds = X[::srt, :] if srt > 1 else X
        Ns_eff = Xds.shape[0]
        
        # --- Clamps de robustez ---
        if nperseg > Ns_eff:
            self._log(f"Advertencia: nperseg ({nperseg}) > Ns_eff ({Ns_eff}). Ajustando nperseg a {Ns_eff}.")
            nperseg = Ns_eff
        if noverlap >= nperseg:
            self._log("Advertencia: noverlap >= nperseg. Ajustando a nperseg//2.")
            noverlap = nperseg // 2
        # nfft < nperseg clamp (fuerza nfft = max(nfft, nperseg))
        if nfft < nperseg:
            self._log("Ajustando nfft a nperseg para cumplir SciPy.")
            nfft = nperseg

        # Detrend SciPy: False para 'none', string para 'constant'/'linear'
        detrend_arg = False if detrend == "none" else detrend

        self._log(f"Welch params: fs_eff={fs_eff}, window={window}, nperseg={nperseg}, "
                  f"noverlap={noverlap}, nfft={nfft}, detrend={detrend_arg}, axis=0")

        freq, power = welch(
            Xds,
            fs=fs_eff,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            nfft=nfft,
            detrend=detrend_arg,  # <- NUEVO: Argumento de detrend
            scaling='density', # V^2/Hz
            axis=0
        )
        
        # --- robustez NaN: Limpiar artefactos NaN/Inf del resultado ---
        power = np.nan_to_num(power, nan=0.0, posinf=np.inf, neginf=0.0).astype(np.float64)
        freq = freq.astype(np.float64) # (Nf,)

        self._log(f"PSD: srt={srt}, fs_eff={fs_eff:.3f} Hz, Nf={freq.size}, T={power.shape[1]}")
        return freq, power, fs_eff

    # ====== Plot en VTK ======
    def _plot_psd(self, freq: np.ndarray, power: np.ndarray, 
                   plot_title: str, lo: float, hi: float):
        """
        Construye vtkTable y dibuja las curvas de 'power'.
        'power' puede ser (Nf, T) o (Nf, 1).
        Aplica filtro de frecuencia y auto-ajuste de límites del eje Y.
        """
        if self.vtk_view is None:
            self._ensure_vtk()

        # Filtro de rango de frecuencias (Eje X)
        sel = (freq >= lo) & (freq <= hi)
        freq_v = freq[sel]
        # 'power' ya es 2D, sea (Nf_sel, T) o (Nf_sel, 1)
        power_v = power[sel, :]

        # --- Modificación: Limitar a MAX_PLOTS si hay demasiados trials ---
        num_curves = power_v.shape[1]
        MAX_PLOTS = 200
        if num_curves > MAX_PLOTS:
            self._log(f"Hay {num_curves} trials → mostrando {MAX_PLOTS}")
            power_v = power_v[:, :MAX_PLOTS]

        table = trials_matrix_to_vtk_table(freq_v, power_v)

        # Crear chart limpio
        scene = self.vtk_view.GetScene()
        scene.ClearItems()
        self.chart = vtk.vtkChartXY()
        scene.AddItem(self.chart)

        ax_b = self.chart.GetAxis(vtk.vtkAxis.BOTTOM)
        ax_l = self.chart.GetAxis(vtk.vtkAxis.LEFT)
        ax_b.SetGridVisible(True); ax_l.SetGridVisible(True)
        ax_b.SetTitle("Frequency (Hz)")
        ax_l.SetTitle("PSD (V²/Hz)")
        
        # --- NUEVO: Auto-ajuste de Eje Y para evitar recorte de picos ---
        if power_v.size > 0:
            # Encontrar el valor máximo global en los datos visibles
            y_max_data = np.max(power_v)
            # Aplicar un margen del 10%
            y_max_limit = y_max_data * 1.10 
            # El límite inferior para PSD es siempre 0.0
            y_min_limit = 0.0 
            
            # Aplicar el rango al Eje Izquierdo (Y).
            ax_l.SetMinimum(y_min_limit)
            ax_l.SetMaximum(y_max_limit)
            self._log(f"Auto-ajuste Eje Y: Range=[{y_min_limit:.2e}, {y_max_limit:.2e}]")
        # --- FIN NUEVO: Auto-ajuste de Eje Y ---

        try:
            # Usar el título dinámico
            self.chart.SetTitle(plot_title)
        except Exception:
            pass
        
        # Un plot por columna (sea 1 o T)
        num_cols = table.GetNumberOfColumns()
        self._log(f"Ploteando {num_cols-1} curvas de PSD.")
        
        # --- Modificación: Si es 1 curva, hacerla más gruesa ---
        line_width = 0.5 if num_curves > 1 else 2.0
        
        for c in range(1, num_cols):
            plot = self.chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, c)
            plot.SetWidth(line_width) 

       # --- Menú contextual---
        try:
            # Extraer ch_name del título (un poco hacky, pero funciona)
            ch_name = plot_title.split('-')[-1].strip()
            # Se asume que self.active_signal está cargado y tiene 'name'
            signal_name = getattr(self.active_signal, 'name', "Unknown Signal")
            self.vtk_menu = VTKContextMenu(self.chart, self.vtk_interactor, 
                                             signal_name, ch_name, 
                                             self.meta.id, parent=self.widget)

        except Exception as e:
            self.alerts.error(f"Error creating the context menu.\n {str(e)}")

        
        self.vtk_view.GetRenderWindow().Render()
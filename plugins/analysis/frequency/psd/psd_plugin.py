# Ubicación: plugins/analysis/frequency/psd/psd_plugin.py

import sys
import numpy as np
import vtk
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from scipy.signal import welch

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
from core.services.signal_dataset import SignalDataset
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
        self.kernel = None
        self.mainwin = None

        # UI
        self.widget: QtWidgets.QWidget | None = None
        self.ui: Ui_Psd | None = None

        # VTK
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None
        self.chart: vtk.vtkChartXY | None = None
        self.vtk_menu: VTKContextMenu | None = None

        self.active_signal: SignalDataset | None = None

    # ---------- util de logs ----------
    def _log(self, *args):
        print("[PSD]", *args)
        sys.stdout.flush()

    def initialize(self, kernel):
        self.kernel = kernel
        self._log("initialize()")

    def start(self, kernel):
        self._log("start() - obteniendo MainWindow")
        self.mainwin = kernel.get_service("MainWindow")

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

            self._log("UI creada. plotArea:", bool(self.ui.plotArea),
                      "panel:", bool(self.ui.panel),
                      "splitter:", bool(self.ui.splitter))
            
            self._ensure_vtk()
            self._wire_ui()

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

    def _wire_ui(self):
        self._log("wire ui")
        self.ui.pushButton.clicked.connect(self._on_calculate_clicked)
        self.ui.lowFrecuencyDoubleSpinBox.valueChanged.connect(self._sync_range)
        self.ui.highFrecuencyDoubleSpinBox.valueChanged.connect(self._sync_range)
        
        # Sincronizar noverlap con nperseg
        self.ui.npersegSpinBox.valueChanged.connect(self._sync_noverlap)
        
        # --- NUEVO: Conectar el ComboBox de modo ---
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
    def _ensure_vtk(self):
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
            
            # --- NUEVO: Parámetros de Modo ---
            mode = self.ui.modeComboBox.currentText()
            trial_idx = self.ui.trialIndexSpinBox.value()


            if lo > hi:
                lo, hi = hi, lo
            
            if noverlap >= nperseg:
                 raise ValueError("N-overlap debe ser menor que N-per-seg.")
        
        except Exception as e:
            QMessageBox.warning(self.widget, "Error de Parámetros", str(e))
            return

        # 3) PSD (Siempre calculamos para todos los trials)
        try:
            freq, power_all_trials, fs_eff = self._compute_psd(X, fs, target_fs,
                                                    window, nperseg, noverlap, nfft)
            # power_all_trials tiene forma (Nf, T)
            
        except Exception as e:
            self._log(f"Error en _compute_psd: {e}")
            QMessageBox.critical(self.widget, "Error de Cálculo", 
                                 f"No se pudo calcular la PSD: {e}")
            return
            
        # --- NUEVO: Seleccionar qué plotear basado en el modo ---
        
        power_to_plot = None
        plot_title = ""
        
        if mode == "All Trials":
            power_to_plot = power_all_trials
            plot_title = f"PSD (All Trials) - {ch_name}"
            
        elif mode == "Average":
            # Calcular el promedio por frecuencia (eje 1)
            # keepdims=True para que el resultado sea (Nf, 1) y no (Nf,)
            # Esto mantiene feliz a trials_matrix_to_vtk_table
            power_to_plot = np.mean(power_all_trials, axis=1, keepdims=True)
            plot_title = f"PSD (Average) - {ch_name}"
            
        elif mode == "Individual":
            if not (0 <= trial_idx < num_trials):
                self._notify(f"Error: Índice de trial {trial_idx} fuera de rango.")
                return
            # Seleccionar solo la columna del trial
            # Usar slicing [:, trial_idx:trial_idx+1] para mantener 2D (Nf, 1)
            power_to_plot = power_all_trials[:, trial_idx:trial_idx+1]
            plot_title = f"PSD (Trial {trial_idx}) - {ch_name}"
            

        # 4) Plot
        if power_to_plot is not None:
            self._plot_psd(freq, power_to_plot, plot_title, lo, hi)
            self._notify(f"PSD ({mode}) listo: fs_eff={fs_eff:.2f} Hz, {freq.size} bins")
        else:
            self._notify(f"Error: Modo de cálculo '{mode}' no reconocido.")


    def _sync_range(self):
        # (Sin cambios, idéntico al anterior)
        lo = float(self.ui.lowFrecuencyDoubleSpinBox.value())
        hi = float(self.ui.highFrecuencyDoubleSpinBox.value())
        if lo > hi:
            sender = self.widget.sender()
            if sender is self.ui.lowFrecuencyDoubleSpinBox:
                self.ui.highFrecuencyDoubleSpinBox.setValue(lo)
            else:
                self.ui.lowFrecuencyDoubleSpinBox.setValue(hi)
        self._log(f"range sync: low={lo}, high={hi}")

    def _notify(self, msg: str):
        # (Sin cambios, idéntico al anterior)
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(msg, 3000)
                return
            except Exception:
                pass
        self._log(msg)

    # ====== DATA ======
    def _load_trials_from_store(self):
        # (Sin cambios, idéntico al anterior)
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

        td = self.active_signal.trials_dataset[-1]  # último TD creado
        fs = float(getattr(td, "sampling_rate", 0.0))
        X  = np.asarray(getattr(td, "trials", None), dtype=np.float64)  # (Ns, T)
        ch = getattr(td, "channel_name", "")
        if X is None or X.ndim != 2 or fs <= 0:
            self._log("TrialDataset inválido (fs<=0 o trials no 2D).")
            return None, None, None

        self._log(f"Trials: Ns={X.shape[0]}, T={X.shape[1]}, fs={fs}")
        return fs, X, ch

    # ====== PSD Logic ======
    def _compute_psd(self, X: np.ndarray, fs: float, target_fs: float,
                     window: str, nperseg: int, noverlap: int, nfft: int):
        # (Sin cambios, idéntico al anterior)
        Ns, T = X.shape
        if target_fs and target_fs > 0:
            srt = max(1, int(round(fs / float(target_fs))))
        else:
            srt = 1

        fs_eff = fs / srt
        Xds = X[::srt, :] if srt > 1 else X
        Ns_eff = Xds.shape[0]
        
        if nperseg > Ns_eff:
            self._log(f"Advertencia: nperseg ({nperseg}) > Ns_eff ({Ns_eff}). "
                      f"Ajustando nperseg a {Ns_eff}.")
            nperseg = Ns_eff
        if noverlap >= nperseg:
            self._log(f"Advertencia: noverlap >= nperseg. Ajustando noverlap.")
            noverlap = nperseg // 2

        self._log(f"Welch params: fs_eff={fs_eff}, window={window}, nperseg={nperseg}, "
                  f"noverlap={noverlap}, nfft={nfft}, axis=0")

        freq, power = welch(
            Xds,
            fs=fs_eff,
            window=window,
            nperseg=nperseg,
            noverlap=noverlap,
            nfft=nfft,
            scaling='density', # V^2/Hz
            axis=0
        )
        
        power = power.astype(np.float64) # (Nf, T)
        freq = freq.astype(np.float64)   # (Nf,)

        self._log(f"PSD: srt={srt}, fs_eff={fs_eff:.3f} Hz, Nf={freq.size}, T={power.shape[1]}")
        return freq, power, fs_eff

    # ====== Plot en VTK ======
    def _plot_psd(self, freq: np.ndarray, power: np.ndarray, 
                  plot_title: str, lo: float, hi: float): # <--- Título añadido
        """
        Construye vtkTable y dibuja las curvas de 'power'.
        'power' puede ser (Nf, T) o (Nf, 1).
        """
        if self.vtk_view is None:
            self._ensure_vtk()

        # Filtro de rango de frecuencias
        sel = (freq >= lo) & (freq <= hi)
        freq_v = freq[sel]
        # 'power' ya es 2D, sea (Nf_sel, T) o (Nf_sel, 1)
        power_v = power[sel, :]  

        # --- Modificación: No limitar a MAX_PLOTS si es (Nf, 1) ---
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
            self.vtk_menu = VTKContextMenu(self.chart, self.vtk_interactor, 
                                           self.active_signal.name, ch_name, 
                                           self.meta.id, parent=self.widget)

        except Exception as e:
            QMessageBox.information(self.widget, "Menú contextual", 
                                    "Error creando el menú contextual.\n" + str(e))
   
        self.vtk_view.GetRenderWindow().Render()
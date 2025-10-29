# Ubicación: plugins/analysis/frequency/psd_average/psd_average_plugin.py

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
# Importar nuestra UI específica y el adaptador VTK
from plugins.analysis.frequency.psd_average.psd_average_plugin_ui import Ui_Psd_average
from core.vtk_adapters.adapters import trials_matrix_to_vtk_table

class Psd_average_plugin(IPlugin):
    """
    Plugin para calcular el PROMEDIO de la Densidad Espectral de Potencia (PSD)
    a través de todos los trials.
    
    Implementa la lógica de f_PSD_Average.
    """
    
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None

        # UI
        self.widget: QtWidgets.QWidget | None = None
        self.ui: Ui_Psd_average | None = None # Usamos la UI de Psd_average

        # VTK
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None
        self.chart: vtk.vtkChartXY | None = None
        self.vtk_menu: VTKContextMenu | None = None

        self.active_signal: SignalDataset | None = None

    # ---------- util de logs ----------
    def _log(self, *args):
        print("[PSD Average]", *args)
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
        self._log(f"[PSD Average] Process: enable {data}")

    def get_widget(self, parent=None):
        if self.widget is None:
            self._log("get_widget(): creando UI")
            self.ui = Ui_Psd_average() # Usamos la UI de Psd_average
            self.widget = QtWidgets.QWidget(parent)
            self.ui.setupUi(self.widget)

            self._log("UI creada. plotArea:", bool(self.ui.plotArea),
                      "panel:", bool(self.ui.panel),
                      "splitter:", bool(self.ui.splitter))
            
            self._ensure_vtk()
            self._wire_ui() # <-- AQUÍ ESTABA EL ERROR (decía self.S())

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

    def _sync_noverlap(self):
        """Ajusta noverlap a la mitad de nperseg por defecto."""
        nperseg = self.ui.npersegSpinBox.value()
        self.ui.noverlapSpinBox.setValue(nperseg // 2)
        # Asegurar que nfft también siga a nperseg (comportamiento común)
        self.ui.nfftSpinBox.setValue(nperseg)

    # ------- VTK -------
    def _ensure_vtk(self):
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
            self._notify("PSD Average: No hay trials en la señal activa.")
            return

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
            # power_all_trials tiene forma (Nf, T) -> Equivale a 'pxx'
            
        except Exception as e:
            self._log(f"Error en _compute_psd: {e}")
            QMessageBox.critical(self.widget, "Error de Cálculo", 
                                 f"No se pudo calcular la PSD: {e}")
            return
            
        # --- LÓGICA DE AVERAGE (HARDCODED) ---
        # Calcular el promedio por frecuencia (eje 1)
        # Equivale a mean(pxx')
        power_to_plot = np.mean(power_all_trials, axis=1, keepdims=True)
        plot_title = f"PSD (Average) - {ch_name}"

        # 4) Plot
        self._plot_psd(freq, power_to_plot, plot_title, lo, hi)
        self._notify(f"PSD (Average) listo: fs_eff={fs_eff:.2f} Hz, {freq.size} bins")


    def _sync_range(self):
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
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(msg, 3000)
                return
            except Exception:
                pass
        self._log(msg)

    # ====== DATA ======
    def _load_trials_from_store(self):
        if not self.mainwin:
            return None, None, None

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
            return None, None, None

        self.active_signal = store.get_active_signal()
        if not self.active_signal or not getattr(self.active_signal, "trials_dataset", None):
            self.active_signal = store.get_active_signal()
            if not self.active_signal or not getattr(self.active_signal, "trials_dataset", None):
                QMessageBox.warning(self.widget, "Error", "No hay señal activa o no tiene TrialDataset.")
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


    # ====== PSD Logic (CON ARREGLO v3: NaN -> 0) ======
    def _compute_psd(self, X: np.ndarray, fs: float, target_fs: float,
                     window: str, nperseg: int, noverlap: int, nfft: int):
        
        Ns, T = X.shape
        if target_fs and target_fs > 0:
            srt = max(1, int(round(fs / float(target_fs))))
        else:
            srt = 1

        fs_eff = fs / srt
        Xds = X[::srt, :] if srt > 1 else X
        Ns_eff = Xds.shape[0]
        
        # --- NUEVO ARREGLO v3: Reemplazar NaNs con Cero ---
        # 1. Encontrar NaNs
        nan_mask = np.isnan(Xds)
        num_nans = np.sum(nan_mask)
        if num_nans > 0:
            self._log(f"Advertencia: Se encontraron {num_nans} puntos NaN. Serán reemplazados por 0.")
            # 2. Reemplazar NaNs con 0
            # copy=False modifica Xds en el lugar
            np.nan_to_num(Xds, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        
        # 3. Usar todos los trials (ahora X_clean = Xds)
        X_clean = Xds
        # --- FIN DEL ARREGLO ---
        
        if nperseg > Ns_eff:
            self._log(f"Advertencia: nperseg ({nperseg}) > Ns_eff ({Ns_eff}). "
                      f"Ajustando nperseg a {Ns_eff}.")
            nperseg = Ns_eff
        if noverlap >= nperseg:
            self._log(f"Advertencia: noverlap >= nperseg. Ajustando noverlap.")
            noverlap = nperseg // 2

        self._log(f"Welch params: fs_eff={fs_eff}, window={window}, nperseg={nperseg}, "
                  f"noverlap={noverlap}, nfft={nfft}, axis=0")

        # 4. Correr Welch en los datos (ahora X_clean = Xds con ceros)
        freq, power = welch(
            X_clean, # <-- Usar X_clean
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

        self._log(f"PSD: srt={srt}, fs_eff={fs_eff:.3f} Hz, Nf={freq.size}, T_calc={power.shape[1]}")
        return freq, power, fs_eff

    # ====== Plot en VTK ======
    def _plot_psd(self, freq: np.ndarray, power: np.ndarray, 
                  plot_title: str, lo: float, hi: float):
        
        if self.vtk_view is None:
            self._ensure_vtk()

        # Filtro de rango de frecuencias
        sel = (freq >= lo) & (freq <= hi)
        freq_v = freq[sel]
        power_v = power[sel, :]  # (Nf_sel, 1)

        # power_v ya es (Nf, 1), así que num_curves será 1
        num_curves = power_v.shape[1] 
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
            self.chart.SetTitle(plot_title)
        except Exception:
            pass
        
        # Solo habrá una columna (c=1)
        self._log(f"Ploteando {table.GetNumberOfColumns()-1} curva de PSD Average.")
        
        plot = self.chart.AddPlot(vtk.vtkChart.LINE)
        plot.SetInputData(table, 0, 1) # Plotea solo la primera (y única) columna
        plot.SetWidth(2.0) # Línea gruesa para el promedio

       # --- Menú contextual---
        try:
            ch_name = plot_title.split('-')[-1].strip()
            self.vtk_menu = VTKContextMenu(self.chart, self.vtk_interactor, 
                                           self.active_signal.name, ch_name, 
                                           self.meta.id, parent=self.widget)

        except Exception as e:
            QMessageBox.information(self.widget, "Menú contextual", 
                                    "Error creando el menú contextual.\n" + str(e))
   
        self.vtk_view.GetRenderWindow().Render()
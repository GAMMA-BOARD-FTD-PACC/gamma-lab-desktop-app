import os
import sys
from core.plugins.interfaces import IPlugin
import vtk
import numpy as np
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox

from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
from core.services.signal_dataset import SignalDataset
from core.vtk_adapters.adapters import trials_matrix_to_vtk_table
from plugins.analysis.frequency.fft_average.fft_average_plugin_ui import Ui_Fft_Average

class Fft_average_plugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        
        self.widget: QtWidgets.QWidget | None = None
        self.ui: Ui_Fft_Average | None = None
        
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None
        self.chart: vtk.vtkChartXY | None = None

        self.active_signal: SignalDataset | None = None
        
    def initialize(self, kernel):
        self.kernel = kernel
        self._log("initialize()")

    def start(self, kernel):
        self._log("start() - obteniendo MainWindow")
        self.mainwin = kernel.get_service("MainWindow")

    def stop(self):
        self._log("stop")
        if self.vtk_interactor:
            self.vtk_interactor.Disable()
    

    def process(self, data):
        self._log(f"process(): {data}")
        if self.vtk_interactor:
            self.vtk_interactor.Enable()
    
    def get_widget(self, parent=None):
        if self.widget is None:
            self._log("get_widget(): creando UI")
            self.ui = Ui_Fft_Average()
            self.widget = QtWidgets.QWidget(parent)
            self.ui.setupUi(self.widget)

            self._log("UI creada. plotArea:", bool(self.ui.plotArea),
                      "panel:", bool(self.ui.panel),
                      "splitter:", bool(self.ui.splitter))
            self._wire_ui()

        else:
            self.widget.setParent(parent)
        return self.widget

    #=== LOGS ===#
    def _notify(self, msg: str):
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(msg, 3000)
                return
            except Exception:
                pass
        self._log(msg)
        
    def _log(self, *args):
        print("[FFT-AVERAGE]", *args)
        sys.stdout.flush()

    ## === UI === ##
    def _wire_ui(self):
        self._log("wire ui")
        self.ui.pushButton.clicked.connect(self._on_calculate_clicked)
        self.ui.lowFrecuencyDoubleSpinBox.valueChanged.connect(self._sync_range)
        self.ui.highFrecuencyDoubleSpinBox.valueChanged.connect(self._sync_range)

    def _on_calculate_clicked(self):
            self._log("_on_calculate_clicked()")
            # 1) Cargar trials de la señal activa
            fs, X, ch_name = self._load_trials_from_store()
            if X is None or fs is None:
                self._notify("FFT Average: no hay trials en la señal activa.")
                return

            # 2) Parámetros UI
            target_fs = float(self.ui.sampleDensityDoubleSpinBox.value())  # 0 = sin remuestreo
            lo = float(self.ui.lowFrecuencyDoubleSpinBox.value())
            hi = float(self.ui.highFrecuencyDoubleSpinBox.value())
            if lo > hi:
                lo, hi = hi, lo

            # 3) FFT
            per_trial = False
            freq, mag_avg, fs_eff = self._compute_fft_average(X, fs, target_fs, per_trial = per_trial)

            # 4) Plot
            self._plot_fft_average(freq, mag_avg, ch_name, lo, hi, fs_eff)
            self._notify(f"FFT listo: fs_eff={fs_eff:.2f} Hz, {freq.size} bins, trials={mag_avg.shape[1]}")

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
    
        # ------- VTK -------
    def _ensure_vtk(self):
        self._log("ensure_vtk(): enter")
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

      
    # ====== DATA ======
    def _load_trials_from_store(self):
        """
        Busca la señal activa en el DataStore y retorna:
          fs: float (sampling_rate del TrialDataset)
          X:  np.ndarray (Ns, T)  matriz de trials (columnas = trials)
          ch_name: nombre de canal (opcional para título)
        """
        if not self.mainwin:
            return None, None, None

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
            return None, None, None

        self.active_signal: SignalDataset = store.get_active_signal()
        if self.active_signal is None:
            QMessageBox.warning(self.widget, "Sin señal activa", "No hay una señal activa seleccionada.")
            return None, None, None

        td = self.active_signal.get_active_trials(self.active_signal.name, None)

        if td is None or td.trials.size == 0:
            QMessageBox.warning(self.widget, "Error", f"No hay trials activos para {self.active_signal.name}.")
            return None, None, None

        fs = float(getattr(td, "sampling_rate", 0.0))
        X  = np.asarray(getattr(td, "trials", None), dtype=np.float64)  # (Ns, T)
        ch = getattr(td, "channel_name", "")
        if X is None or X.ndim != 2 or fs <= 0:
            self._log("TrialDataset inválido (fs<=0 o trials no 2D).")
            return None, None, None

        self._log(f"Trials: Ns={X.shape[0]}, T={X.shape[1]}, fs={fs}")
        return fs, X, ch
    
    # ====== FFT - AVERAGE ======
    def _compute_fft_average(self, X: np.ndarray, fs: float, target_fs: float, *, per_trial: bool = False):
        """
        FFT estilo MATLAB con promedio opcional entre trials.
        - X: (Ns, T)  (columnas = trials)
        - fs: sampling rate original
        - target_fs: si > 0, remuestrea por diezmado (srt = round(fs/target_fs))

        Devuelve:
        freq: (Nf,)
        mag:  (Nf, T) si per_trial=True, o (Nf, 1) si promedio
        fs_eff: float
        """
        Ns, T = X.shape
        # Diezmado como en MATLAB
        if target_fs and target_fs > 0:
            srt = max(1, int(round(fs / float(target_fs))))
        else:
            srt = 1
        fs_eff = fs / srt
        Xds = X[::srt, :] if srt > 1 else X

        # === FFT mean ===
        Ns_eff = Xds.shape[0]
        mFourier = np.fft.fft(Xds, n=Ns_eff, axis=0)           # (Ns_eff, T)
        mFourier = mFourier[: (Ns_eff // 2) + 1, :]            # (Nf, T)
        mag = np.abs(mFourier).astype(np.float64)              # (Nf, T)
        freq = np.linspace(0.0, fs_eff/2.0, mFourier.shape[0])

        if per_trial:
            # Equivalente a GF==1 en MATLAB: devolver todas las curvas
            mag_out = mag  # (Nf, T)
        else:
            # Promedio entre trials (como mean(m_FFT',1) en MATLAB)
            # Usamos nanmean para ignorar NaNs si existieran
            mag_mean = np.nanmean(mag, axis=1)        # (Nf,)
            mag_out  = mag_mean[:, None]              # (Nf, 1) para reutilizar el mismo plotter

        self._log(f"FFT_AVG: srt={srt}, fs_eff={fs_eff:.3f} Hz, Nf={freq.size}, "
                f"T={T}, per_trial={per_trial}")
        return freq, mag_out, fs_eff

    # ====== Plot en VTK ======
    def _plot_fft_average(self, freq: np.ndarray, mag: np.ndarray, ch_name: str, lo: float, hi: float, fs_eff: float):
        """
        Construye vtkTable usando trials_matrix_to_vtk_table(freq, mag)
        y dibuja líneas una por trial. Aplica filtro [lo, hi].
        """
        if self.vtk_view is None:
            self._ensure_vtk()

        hi = min(hi, fs_eff/2.0)
        lo = max(lo, 0.0)
        if lo >= hi:
            self._notify("Rango de frecuencias vacío tras ajustar al Nyquist."); return
        sel = (freq >= lo) & (freq <= hi)
        self._log(f"Plot bins: {sel.sum()} de {freq.size}")
        freq_v = freq[sel]
        mag_v  = mag[sel, :]  # (Nf_sel, T)

        # Limitar cantidad de curvas mostradas
        MAX_PLOTS = 200
        if mag_v.shape[1] > MAX_PLOTS:
            self._log(f"Hay {mag_v.shape[1]} trials → mostrando {MAX_PLOTS}")
            mag_v = mag_v[:, :MAX_PLOTS]

        table = trials_matrix_to_vtk_table(freq_v, mag_v)

        # Crear chart limpio
        scene = self.vtk_view.GetScene()
        scene.ClearItems()
        self.chart = vtk.vtkChartXY()
        scene.AddItem(self.chart)

        ax_b = self.chart.GetAxis(vtk.vtkAxis.BOTTOM)
        ax_l = self.chart.GetAxis(vtk.vtkAxis.LEFT)
        ax_b.SetGridVisible(True); ax_l.SetGridVisible(True)
        ax_b.SetTitle("Frequency (Hz)")
        ax_l.SetTitle("Magnitude")
        try:
            if ch_name:
                self.chart.SetTitle(f"FFT - {ch_name}")
        except Exception:
            pass
        
        # Un plot por columna
        num_cols = table.GetNumberOfColumns()
        print(f"num_cols={num_cols}")
        for c in range(1, num_cols):
            plot = self.chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, c)
            plot.SetWidth(1.0)

           # --- Menú contextual---
    
        try:
            self.vtk_menu = VTKContextMenu(self.chart, self.vtk_interactor, self.active_signal.name, ch_name,self.meta.id,  parent=self.widget)

        except Exception as e:
            QMessageBox.information(self.widget, "Menú contextal", "Error creando el menú contextual.\n" + str(e))
     


        self.vtk_view.GetRenderWindow().Render()
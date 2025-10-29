# plugins/analysis/frequency/fft/fft_plugin.py
import sys
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
import vtk
import numpy as np
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
from core.services.signal_dataset import SignalDataset
from plugins.analysis.frequency.fft.fft_plugin_ui import Ui_Fft
from core.vtk_adapters.adapters import trials_matrix_to_vtk_table

class Fft_plugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None

        # UI
        self.widget: QtWidgets.QWidget | None = None
        self.ui: Ui_Fft | None = None

        # VTK
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None
        self.chart: vtk.vtkChartXY | None = None

        self.active_signal: SignalDataset | None = None

    # ---------- util de logs ----------
    def _log(self, *args):
        print("[FFT]", *args)
        sys.stdout.flush()

    def initialize(self, kernel):
        self.kernel = kernel
        self._log("initialize()")

    def start(self, kernel):
        self._log("start() - obteniendo MainWindow")
        self.mainwin = kernel.get_service("MainWindow")

    def stop(self):
        self._log("stop() - cleanup VTK")
        #self._cleanup_vtk()
        if self.vtk_interactor:
            self.vtk_interactor.Disable()
        
    def process(self, data):
        if self.vtk_interactor:
            self.vtk_interactor.Enable()

        self._log(f"[FFT] Process: enable {data}")

    def get_widget(self, parent=None):
        if self.widget is None:
            self._log("get_widget(): creando UI")
            self.ui = Ui_Fft()
            self.widget = QtWidgets.QWidget(parent)
            self.ui.setupUi(self.widget)

            # log de estructura UI
            self._log("UI creada. plotArea:", bool(self.ui.plotArea),
                      "panel:", bool(self.ui.panel),
                      "splitter:", bool(self.ui.splitter))
            #self._ensure_vtk()
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


    # ------- acciones (placeholder) -------
    def _on_calculate_clicked(self):
            self._log("_on_calculate_clicked()")

            # 1) Cargar trials de la señal activa
            fs, X, ch_name = self._load_trials_from_store()
            if X is None or fs is None:
                self._notify("FFT: no hay trials en la señal activa.")
                return

            # 2) Parámetros UI
            target_fs = float(self.ui.sampleDensityDoubleSpinBox.value())  # 0 = sin remuestreo
            lo = float(self.ui.lowFrecuencyDoubleSpinBox.value())
            hi = float(self.ui.highFrecuencyDoubleSpinBox.value())
            if lo > hi:
                lo, hi = hi, lo

            # 3) FFT
            freq, mag, fs_eff = self._compute_fft(X, fs, target_fs)

            # 4) Plot
            self._plot_fft(freq, mag, ch_name, lo, hi)
            self._notify(f"FFT listo: fs_eff={fs_eff:.2f} Hz, {freq.size} bins, trials={mag.shape[1]}")

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

        self.active_signal = store.get_active_signal()
        if not self.active_signal:
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

    # ====== FFT ======
    def _compute_fft(self, X: np.ndarray, fs: float, target_fs: float):
        """
        Devuelve (freq:(Nf,), mag:(Nf,T), fs_eff:float)
        """
        Ns, T = X.shape
        if target_fs and target_fs > 0:
            srt = max(1, int(round(fs / float(target_fs))))
        else:
            srt = 1

        fs_eff = fs / srt
        Xds = X[::srt, :] if srt > 1 else X
        Ns_eff = Xds.shape[0]

        mFourier = np.fft.rfft(Xds, axis=0)             # (Nf, T)
        mag = np.abs(mFourier).astype(np.float64)       # (Nf, T)
        freq = np.fft.rfftfreq(Ns_eff, d=1.0/fs_eff)    # (Nf,)

        self._log(f"FFT: srt={srt}, fs_eff={fs_eff:.3f} Hz, Nf={freq.size}, T={mag.shape[1]}")
        return freq, mag, fs_eff

    # ====== Plot en VTK con tu adaptador ======
    def _plot_fft(self, freq: np.ndarray, mag: np.ndarray, ch_name: str, lo: float, hi: float):
        """
        Construye vtkTable usando trials_matrix_to_vtk_table(freq, mag)
        y dibuja líneas una por trial. Aplica filtro [lo, hi].
        """
        if self.vtk_view is None:
            self._ensure_vtk()

        # Filtro de rango de frecuencias
        sel = (freq >= lo) & (freq <= hi)
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
            plot.SetWidth(0.5)

         # --- Menú contextual---
    
        try:
            self.vtk_menu = VTKContextMenu(self.chart, self.vtk_interactor, self.active_signal.name, ch_name, self.meta.id, parent=self.widget)

        except Exception as e:
            QMessageBox.information(self.widget, "Menú contextal", "Error creando el menú contextual.\n" + str(e))
     

        self.vtk_view.GetRenderWindow().Render()

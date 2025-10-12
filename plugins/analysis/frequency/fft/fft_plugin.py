# plugins/analysis/frequency/fft/fft_plugin.py
import sys
from PyQt5 import QtWidgets, QtCore
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from plugins.analysis.frequency.fft.fft_plugin_ui import Ui_Fft

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
        self._cleanup_vtk()
        self.mainwin = None
        
    def process(self, data):
        self._log(f"process(): {data}")

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


    def _cleanup_vtk(self):
        self._log("cleanup_vtk()")
        try:
            if self.vtk_interactor:
                rw = self.vtk_interactor.GetRenderWindow()
                if rw:
                    iren = rw.GetInteractor()
                    if iren:
                        try: iren.TerminateApp()
                        except Exception: pass
                    try: rw.Finalize()
                    except Exception: pass
                self.vtk_interactor.SetRenderWindow(None)
        except Exception as e:
            self._log("cleanup_vtk error:", e)
        finally:
            self.vtk_interactor = None
            self.vtk_view = None
            self.chart = None

    # ------- acciones (placeholder) -------
    def _on_calculate_clicked(self):
        self._log("_on_calculate_clicked()")
        try:
            if self.vtk_view and self.chart:
                self.vtk_view.GetRenderWindow().Render()
                self._log("Render tras click OK")
            self._notify("FFT: UI y VTK listos. Integra el cálculo aquí.")
        except Exception as e:
            self._log("Render click exception:", e)

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

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from plugins.analysis.time_frequency.wavelet_plugin_ui import Ui_Wavelet
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
import numpy as np

class Wavelet_plugin(IPlugin):
    def __init__(self, meta:PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.kernel = None
        self.ui = None


    def initialize(self, kernel):
        print("Inicializando Wavelet")

    def process(self, data: any):
        print(f"Wavelet recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
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
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Wavelet()
            self.ui.setupUi(self.widget)

            # Crear el VTK interactor dentro del contenedor del .ui
            vtk_layout = QVBoxLayout(self.ui.frame)
            vtk_layout.setContentsMargins(0, 0, 0, 0)

            self.vtk_widget = QVTKRenderWindowInteractor(self.ui.frame)
            vtk_layout.addWidget(self.vtk_widget)

            self.renwin = self.vtk_widget.GetRenderWindow()
            try:
                self.vtk_widget.Initialize()
            except Exception:
                pass

            # Conectar botón "Create Wavelet”
            self.ui.createWaveletButton.clicked.connect(self.on_create_wavelet)

        else:
            self.widget.setParent(parent)

        return self.widget
    
    def on_create_wavelet():
        print("Creando wavelet")

    # end def 
# end class
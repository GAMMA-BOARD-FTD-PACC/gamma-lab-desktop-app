from core.plugins.interfaces import IPlugin
from PyQt5.QtWidgets import QWidget
import os

from core.plugins.meta import PluginMeta

class Fft_plugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False

    def initialize(self, kernel):
        print("Inicializando Fft")

    def process(self, data: any):
        print(f"Fft recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
            try:
                self.mainwin.statusBar().showMessage(f"Fft procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando Fft")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("Fft tiene acceso a MainWindow")        

    def stop(self):
        print("Deteniendo Fft")
        self.mainwin = None
    
    def get_widget(self, parent=None):
        return None

    # def get_widget(self, parent=None):
    #     if self.widget is None:
    #         self.widget = QWidget(parent)
    #         self.ui = Ui_Form()
    #         self.ui.setupUi(self.widget)

    #         self.ui.pushButton.clicked.connect(lambda: self.process("Fft ejecutado"))
    #     else:
    #         #reasignar el parent si el widget ya existe
    #         self.widget.setParent(parent)
    #     return self.widget
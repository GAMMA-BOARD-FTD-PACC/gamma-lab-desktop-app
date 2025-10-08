import os
from core.plugins.interfaces import IPlugin
from PyQt5.QtWidgets import QWidget

from core.plugins.meta import PluginMeta

class Erp_plugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False

    def initialize(self, kernel):
        print("Inicializando ERP")

    def process(self, data: any):
        print(f"ERP recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
            try:
                self.mainwin.statusBar().showMessage(f"ERP procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando ERP")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("ERP tiene acceso a MainWindow")        

    def stop(self):
        print("Deteniendo ERP")
        self.mainwin = None
    
    def get_widget(self, parent=None):
        return None
    # def get_widget(self, parent=None):
    #     if self.widget is None:
    #         self.widget = QWidget(parent)
    #         self.ui = Ui_Form()
    #         self.ui.setupUi(self.widget)

    #         self.ui.pushButton.clicked.connect(lambda: self.process("Average ejecutado"))
    #     else:
    #         #reasignar el parent si el widget ya existe
    #         self.widget.setParent(parent)
    #     return self.widget
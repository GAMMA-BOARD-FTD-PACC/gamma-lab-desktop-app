import os
from core.interfaces import IPlugin
from PyQt5.QtWidgets import QWidget

class Relative_psd_plugin(IPlugin):
    def __init__(self):
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False

    
    def name(self) -> str:
        return "Relative PSD"
    
    def icon(self) -> str:
        base_path = os.path.dirname(os.path.abspath(__file__))
        ruta = os.path.join(base_path, "src\icn_Relative_psd.png")
        return ruta
    
    def category(self):
        return "Analysis"

    def initialize(self, kernel):
        print("Inicializando Relative_psd")

    def process(self, data: any):
        print(f"Relative_psd recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
            try:
                self.mainwin.statusBar().showMessage(f"Relative_psd procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando Relative_psd")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("Relative_psd tiene acceso a MainWindow")        

    def stop(self):
        print("Deteniendo Relative_psd")
        self.mainwin = None

    # def get_widget(self, parent=None):
    #     if self.widget is None:
    #         self.widget = QWidget(parent)
    #         self.ui = Ui_Form()
    #         self.ui.setupUi(self.widget)

    #         self.ui.pushButton.clicked.connect(lambda: self.process("Relative_psd ejecutado"))
    #     else:
    #         #reasignar el parent si el widget ya existe
    #         self.widget.setParent(parent)
    #     return self.widget
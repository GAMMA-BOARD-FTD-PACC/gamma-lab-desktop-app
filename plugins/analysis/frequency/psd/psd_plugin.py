import os
from core.interfaces import IPlugin
from PyQt5.QtWidgets import QWidget

class Psd_plugin(IPlugin):
    def __init__(self):
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False

    
    def name(self) -> str:
        return "Psd"
    
    def icon(self) -> str:
        base_path = os.path.dirname(os.path.abspath(__file__))
        ruta = os.path.join(base_path, "src\icn_Psd.png")
        return ruta
    
    def category(self):
        return "Analysis"
    
    def subcategory(self):
        return "Frequency"

    def initialize(self, kernel):
        print("Inicializando Psd")

    def process(self, data: any):
        print(f"Psd recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
            try:
                self.mainwin.statusBar().showMessage(f"Psd procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando Psd")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("Psd tiene acceso a MainWindow")        

    def stop(self):
        print("Deteniendo Psd")
        self.mainwin = None

    def get_widget(self, parent=None):
        return None

    # def get_widget(self, parent=None):
    #     if self.widget is None:
    #         self.widget = QWidget(parent)
    #         self.ui = Ui_Form()
    #         self.ui.setupUi(self.widget)

    #         self.ui.pushButton.clicked.connect(lambda: self.process("Psd ejecutado"))
    #     else:
    #         #reasignar el parent si el widget ya existe
    #         self.widget.setParent(parent)
    #     return self.widget
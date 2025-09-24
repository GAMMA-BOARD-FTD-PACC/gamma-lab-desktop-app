from core.interfaces import IPlugin
from PyQt5.QtWidgets import QWidget

class Psd_average_plugin(IPlugin):
    def __init__(self):
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False

    
    def name(self) -> str:
        return "Psd_average"
    
    def icon(self) -> str:
        return "./src/icons/dominios/icn_Psd_average.png"
    
    def category(self):
        return "Analysis"

    def initialize(self, kernel):
        print("Inicializando Psd_average")

    def process(self, data: any):
        print(f"Psd_average recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
            try:
                self.mainwin.statusBar().showMessage(f"Psd_average procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando Psd_average")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("Psd_average tiene acceso a MainWindow")        

    def stop(self):
        print("Deteniendo Psd_average")
        self.mainwin = None

    # def get_widget(self, parent=None):
    #     if self.widget is None:
    #         self.widget = QWidget(parent)
    #         self.ui = Ui_Form()
    #         self.ui.setupUi(self.widget)

    #         self.ui.pushButton.clicked.connect(lambda: self.process("Psd_average ejecutado"))
    #     else:
    #         #reasignar el parent si el widget ya existe
    #         self.widget.setParent(parent)
    #     return self.widget
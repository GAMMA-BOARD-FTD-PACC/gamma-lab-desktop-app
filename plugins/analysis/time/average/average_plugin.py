from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from plugins.analysis.time.average.average_plugin_ui import Ui_Form
from PyQt5.QtWidgets import QWidget
import os

class Average_plugin(IPlugin):
    def __init__(self, meta:PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.kernel = None


    def initialize(self, kernel):
        print("Inicializando Average")

    def process(self, data: any):
        print(f"Average recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
            try:
                self.mainwin.statusBar().showMessage(f"Average procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando Average")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("Average tiene acceso a MainWindow")        

    def stop(self):
        print("Deteniendo Average")
        self.mainwin = None

    def get_widget(self, parent=None):
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Form()
            self.ui.setupUi(self.widget)

            self.ui.pushButton.clicked.connect(self._load_dataset_from_store)

        else:
            self.widget.setParent(parent)

        return self.widget
    

    def _load_dataset_from_store(self):
        """Busca 'trials_dataset' en el DataStore y extrae time y matrix."""
        if not self.mainwin:
            return

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            print("[Average] No hay servicio de DataStore.")
            return

        ds = store.get("trials_dataset", None)
        if ds is None:
            print("No se encontró 'trials_dataset' en DataStore")
            return

        print(f"Data store {store}")
        
        for key, value in store.items():
            print(f"Clave: {key}")
            print(f"Valor: {value}")

        print(f"Ds {ds.trials}")
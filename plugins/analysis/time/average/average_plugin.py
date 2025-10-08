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

            self.ui.pushButton.clicked.connect(self.print_datastore)

        else:
            self.widget.setParent(parent)

        return self.widget
 # ------------------------------------------------------
    def print_datastore(self):
        """Obtiene 'trials_dataset' del DataStore y muestra info de time/matrix."""

        datastore = self.mainwin.kernel.get_service("DataStore")
        if datastore is None:
            print("⚠️ No se encontró el servicio DataStore.")
            return

        print("🧠 Contenido actual del DataStore:")
        # Imprime todas las claves disponibles
        for key in datastore._data.keys():
            print(f"  {key}")

        # Intentamos extraer trials_dataset
        td = datastore.get("trials_dataset", None)
        if td is None:
            print("⚠️ No se encontró 'trials_dataset' en el DataStore")
            return

        # Extraemos time y matrix
        if hasattr(td, "time_rel") and hasattr(td, "trials"):
            t = td.time_rel
            X = td.trials
            print(f"✅ 'trials_dataset' encontrado:")
            print(f"    Time shape: {t.shape}")
            print(f"    Trials shape: {X.shape}")
        else:
            print("⚠️ 'trials_dataset' no tiene atributos 'time_rel' o 'trials'.")
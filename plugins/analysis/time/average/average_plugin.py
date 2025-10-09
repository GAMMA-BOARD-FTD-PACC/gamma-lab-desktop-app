from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
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
        
        # Intentar obtener el SignalDataset principal
        signal_ds: SignalDataset | None = store.get("raw", None)
        if signal_ds is None:
            print("No se encontró 'raw' (SignalDataset) en el DataStore.")
            return

        if not signal_ds.trials_dataset:
            print("El SignalDataset no tiene trials asociados.")
            return

        print(f"Se encontraron {len(signal_ds.trials_dataset)} TrialDataset asociados.\n")

        # Recorrer y mostrar información de cada trial
        for i, td in enumerate(signal_ds.trials_dataset, start=1):
            print(f"── TrialDataset #{i} ──")
            print(f"Canal: {td.channel_name} (índice {td.channel_index})")
            print(f"Archivo origen: {td.source}")
            print(f"Sampling rate: {td.sampling_rate} Hz")
            print(f"Trials shape: {td.trials.shape}")
            print(f"Time_rel shape: {td.time_rel.shape}")
            print(f"Onsets: {len(td.onsets_s)} eventos\n")


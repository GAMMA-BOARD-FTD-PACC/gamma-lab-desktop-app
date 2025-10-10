from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from plugins.analysis.time.average.average_plugin_ui import Ui_Average
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
        self._load_dataset_from_store()
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
            self.ui = Ui_Average()
            self.ui.setupUi(self.widget)

            #self.ui.pushButton.clicked.connect(self._load_dataset_from_store)

        else:
            self.widget.setParent(parent)

        return self.widget
    

    def _load_dataset_from_store(self):
        """Carga el SignalDataset activo desde el DataStore y muestra sus TrialDataset asociados."""
        if not self.mainwin:
            return

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            print("[Average] No hay servicio de DataStore.")
            return

        # Obtener la señal activa
        active_signal = store.get_active_signal()
        if not active_signal:
            print("[Average] No hay señal activa registrada en el DataStore.")
            return
        
        print(f"[Average] Señal activa: '{active_signal}'")
        print(f"Formato: {active_signal.format}")
        print(f"Archivo fuente: {active_signal.source_path}")
        print(f"Sampling rate: {active_signal.sampling_rate} Hz")
        print(f"Canales: {len(active_signal.channel_names)} → {active_signal.channel_names}")
        print(f"Unidades: {active_signal.units}")
        print(f"Dimensiones de signals: {active_signal.signals.shape}\n")

        # Revisar si tiene trials asociados
        if not hasattr(active_signal, "trials_dataset") or not active_signal.trials_dataset:
            print("[Average] El SignalDataset no tiene TrialDataset asociados.")
            return

        print(f"Se encontraron {len(active_signal.trials_dataset)} TrialDataset asociados.\n")

        # Recorrer y mostrar información detallada de cada trial
        for i, td in enumerate(active_signal.trials_dataset, start=1):
            print(f"── TrialDataset #{i} ──")
            print(f"Canal: {td.channel_name} (índice {td.channel_index})")
            print(f"Archivo origen: {td.source}")
            print(f"Sampling rate: {td.sampling_rate} Hz")
            print(f"Trials shape: {td.trials.shape}")
            print(f"Time_rel shape: {td.time_rel.shape}")
            print(f"Onsets: {len(td.onsets_s)} eventos\n")



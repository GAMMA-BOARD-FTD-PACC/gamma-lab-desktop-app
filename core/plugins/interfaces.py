from abc import ABC, abstractmethod
import sys

from core.kernel import Kernel
from core.plugins.meta import PluginMeta
from core.plugins.plugin_alerts import PluginAlerts
from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

'''
Aquí se definen las interfaces para los plugins y servicios, es decir,
el contrato y sistema de comunicación entre los plugins y el kernel.
'''

class IPlugin(ABC):
    
    def __init__(self, meta: PluginMeta) -> None:
        self.meta: PluginMeta = meta
        self.started: bool = False
        self.mainwin = None
        self.widget = None  #Es donde se rendriza todo el UI de PyQt
        self.kernel: Kernel = None
        self.active_signal: SignalDataset = None
        self.active_chanel = None
        self.alerts = PluginAlerts()

        
        
    # ===== getters leen del YAML =====
    def name(self) -> str:
        """Nombre para UI (desde properties.yml)."""
        return self.meta.name

    def category(self) -> str:
        """Categoría del plugin (desde properties.yml)."""
        return self.meta.category

    def subcategory(self) -> str:
        """Subcategoría del plugin (desde properties.yml)."""
        return self.meta.subcategory

    def icon(self) -> str:
        """
        Ruta absoluta del icono (dentro de la carpeta del plugin).
        MainWindow espera una ruta para construir QIcon(icon_path).
        """
        return str(self.meta.icon_path())
    
    def _log(self, *args):
        print(f"[{self.meta.name}]", *args)
        sys.stdout.flush()

    def _notify(self, msg: str):
        try:
            if self.mainwin:
                self.mainwin.statusBar().showMessage(msg, 3000)
                return
        except Exception:
            pass
        self._log(msg)


    def get_datastore(self) -> DataStore | None:
        """Obtiene el servicio DataStore desde el kernel."""
        try:
            if not self.mainwin:
                self.alerts.error("No se encontró el MainWindow para acceder al DataStore.")
                return None
            store: DataStore | None = self.mainwin.kernel.get_service("DataStore")
            if store is None:
                self.alerts.warning("No se encontró el servicio DataStore.")
            return store
        except Exception as e:
            self.alerts.error(f"Error accediendo al DataStore: {e}")
            return None

    def get_active_signal(self) -> SignalDataset | None:
        """Devuelve la señal activa o None si no existe."""
        try:
            store = self.get_datastore()
            if not store:
                return None
            ds = store.get_active_signal()
            if not ds:
                self.alerts.warning("No signal has been loaded.")
                return None
            self.active_signal = ds
            return ds
        except Exception as e:
            self.alerts.error(f"Error obtaining the signal: {e}")
            return None

    def get_active_trials(self, signal: SignalDataset | None = None) -> TrialDataset | None:
        """Devuelve los trials activos de la señal actual."""
        try:
            sig = signal or self.active_signal or self.get_active_signal()
            if sig is None:
                return None

            td : TrialDataset = self.active_signal.get_active_trials(sig.name, None)
            if td is None or td.trials.size == 0:
                self.alerts.warning(f"There are no active trials for {sig.name}.")
                return None
        

            return td
        
        except Exception as e:
            self.alerts.error(f"Error obtaining trials: {e}")
            return None
        
    def on_kernel_event(self, topic: str, payload: object):
        """
        Escucha eventos emitidos por el Kernel.
        """
        if topic == "signal_active_changed" or topic =="signal_added":
            print(f"Nueva señal cambiada: {payload}")
            self.active_signal = self.get_active_signal() 

    def initialize(self, kernel):
        """Se llama cuando se registra el plugin en el kernel y se pasa el kernel como argumento."""
        self.kernel = kernel
        self._log("Inicializando")

    @abstractmethod
    def process(self, data: any):
        """Procesa datos enviados por el kernel u otros plugins."""
        pass

    @abstractmethod
    def start(self, kernel):
        """Se invoca cuando el kernel inicia los plugins."""
        pass

    @abstractmethod
    def stop(self):
        """Se invoca cuando el kernel detiene los plugins."""
        pass

    @abstractmethod
    def get_widget(self, parent=None):
        """Devuelve el widget asociado al plugin"""
        pass


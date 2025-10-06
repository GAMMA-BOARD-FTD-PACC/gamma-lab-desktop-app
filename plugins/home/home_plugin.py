from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta

class Plugin_home(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None

    def initialize(self, kernel):
        print("Inicializando Home")

    def process(self, data: any):
        print(f"Home recibió datos: {data}")

    def start(self, kernel):
        print("Iniciando Home")
        self.mainwin = kernel.get_service("MainWindow")        

    def stop(self):
        print("Deteniendo UIPlugin")

    def get_widget(self, parent=None):
        return None
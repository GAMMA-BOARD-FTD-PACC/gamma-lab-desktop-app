from abc import ABC, abstractmethod

from core.plugins.meta import PluginMeta

'''
Aquí se definen las interfaces para los plugins y servicios, es decir,
el contrato y sistema de comunicación entre los plugins y el kernel.
'''

class IPlugin(ABC):
    
    def __init__(self, meta: PluginMeta) -> None:
        self.meta: PluginMeta = meta
        self.started: bool = False 
        
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

    @abstractmethod
    def initialize(self, kernel):
        """Inicialización del plugin (se llama cuando se registra)."""
        pass

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


class IService(ABC):
    """Marca para servicios expuestos en el kernel (opcional)."""
    pass

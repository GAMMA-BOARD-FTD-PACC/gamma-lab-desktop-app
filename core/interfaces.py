from abc import ABC, abstractmethod

'''
Aquí se definen las interfaces para los plugins y servicios, es decir,
el contrato y sistema de comunicación entre los plugins y el kernel.
'''

class IPlugin(ABC):
    @abstractmethod
    def name(self) -> str:
        """Devuelve el nombre del plugin (utilizado para la representación en la UI del kernel)."""
        pass

    
    @abstractmethod
    def category(self) -> str:
        """Categoría del plugin: 'Home', 'Preprocessing', 'Analysis', etc."""
        pass

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


class IService(ABC):
    """Marca para servicios expuestos en el kernel (opcional)."""
    pass

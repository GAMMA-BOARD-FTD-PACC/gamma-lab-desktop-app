# core/kernel.py
from PyQt5.QtCore import QObject, pyqtSignal
import sys
import importlib
import os

class Kernel(QObject):
  
    event = pyqtSignal(str, object)  # Eventos generales
    plugin_registered = pyqtSignal(str)  # Cuando se registra un plugin


    def __init__(self):
        super().__init__()
        self._plugins = {}
        self._services = {}

    def register_plugin(self, name, plugin):
        if name in self._plugins:
            print(f"El plugin '{name}' ya está registrado, se sobreescribirá.")
        print(f"Registrando plugin: {name}")
        #Agregar el plugin al diccionario de plugins
        self._plugins[name] = plugin

        #Veriricar que el plugin tenga el método start y arrancarlo
        if hasattr(plugin, 'initialize'):
            plugin.start(self)

        #emitir el evento de creación de un plugin
        self.plugin_registered.emit(name)

    #Obtener el nombre todos los plugins registrados
    def get_plugins(self):
        return list(self._plugins.keys())
    
    #Obtener un plugin por su nombre
    def get_plugin(self, name):
        return self._plugins.get(name)

    #Obtener todos los plugins de una categoría
    def get_plugins_by_category(self, category: str):
        return [name for name, p in self._plugins.items() if hasattr(p, "category") and p.category() == category]

    

    #Cargar dinámicamente y arrancar todos los plugins registrados
    def load_and_register(self, name: str, module_path: str, class_name: str):
        """
        Carga dinámicamente un plugin desde un módulo de Python y lo registra.
        - name: nombre con el que se registrará el plugin
        - module_path: ruta del módulo (ej: 'plugins.my_plugin')
        - class_name: nombre de la clase dentro del módulo
        """
        try:
            if module_path in sys.modules:
                del sys.modules[module_path]

            module = importlib.import_module(module_path)
            PluginClass = getattr(module, class_name)
            plugin_instance = PluginClass()
            self.register_plugin(name, plugin_instance)
            return True
        except Exception as e:
            print(f"ERROR: no se pudo cargar el plugin '{name}' desde {module_path}: {e}")
            return False
        
    '''
    def execute(self, name, data=None):
        """
        Ejecuta un método 'process(data)' en el plugin indicado.
        """
        if name in self._plugins:
            plugin = self._plugins[name]
            if hasattr(plugin, "process"):
                plugin.process(data)
                return {"success": True, "message": f"Plugin '{name}' ejecutado."}
            else:
                return {"success": False, "message": f"Plugin '{name}' no tiene método process()."}
        else:
            msg = f"ERROR: el plugin '{name}' no está registrado."
            print(msg)
            return {"success": False, "message": msg}
    '''

    def stop_plugins(self):
        for plugin in self._plugins.values():
            plugin.stop()

    def register_service(self, key, service):
        self._services[key] = service

    def get_service(self, key):
        return self._services.get(key)

    def emit_event(self, topic, payload=None):
        self.event.emit(topic, payload)

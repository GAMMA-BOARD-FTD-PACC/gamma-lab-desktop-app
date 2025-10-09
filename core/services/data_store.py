'''
    Es el servicio donde se van a almacenar todas las entidades procesadas, como la señal cruda, y los trials_dataset
    Se accede a ella usando clave valor
'''

from core.services.signal_dataset import SignalDataset

class DataStore:
    def __init__(self):
        self._data = {}

    #Guardar una entidad por una clave núnica
    def set(self, key, value):
        self._data[key] = value

    #Obtener una entidad por su clave
    def get(self, key, default=None):
        return self._data.get(key, default)

    #Verificar si exsite una clave
    def has(self, key):
        return key in self._data
    
    #Regresa todos los items (clave, valor)
    def items(self):
        return list(self._data.items())
    
    #Eliminar una entidad por su clave
    def remove(self, key):
        del self._data[key]


    """
        Agrega una nueva señal al DataStore usando el nombre del archivo como clave
        Retorna la clave usada.
    """

    def add_signal(self, signal, key: str = None):
        if key is None:
            base_key = "raw_signal"
            i = 1
            while f"{base_key}_{i}" in self._data:
                i += 1
            key = f"{base_key}_{i}"
        self._data[key] = signal
        return key
    

    #Retorna todas las señales almacenadas que sean instancias de SignalDataset.
    def get_signals(self):
        return {k: v for k, v in self._data.items() if isinstance(v, SignalDataset)}
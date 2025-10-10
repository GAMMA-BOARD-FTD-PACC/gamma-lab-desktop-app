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
    

    def set_active_signal(self, key: str):
        """
        Define la señal activa usando la clave de una señal almacenada.
        Lanza ValueError si la clave no existe o no corresponde a una señal.
        """
        if key not in self._data:
            raise ValueError(f"La señal con clave '{key}' no existe en el DataStore.")
        if not isinstance(self._data[key], SignalDataset):
            raise ValueError(f"El elemento '{key}' no es una señal válida (SignalDataset).")

        self._data["active_signal"] = key


    #Retornar la señal activa (instancia de SignalDataset). - Devuelve None si no hay una activa definida.
    def get_active_signal(self):
        key = self._data.get("active_signal")
        if key and key in self._data:
            return self._data[key]
        return None

    #Retornar la clave del signal activo (string) o None si no hay.
    def get_active_signal_key(self):
        return self._data.get("active_signal")

    #Eliminar la referencia a la señal activa (no borra la señal del DataStore).
    def clear_active_signal(self):
        if "active_signal" in self._data:
            del self._data["active_signal"]
    
    #Verificar si una clave corresponde a la señal activa

    def is_active_signal(self, key: str):
        return self._data.get("active_signal") == key
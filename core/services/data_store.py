'''
    Es el servicio donde se van a almacenar todas las entidades procesadas, como la señal cruda, y los trials_dataset
    Se accede a ella usando clave valor
'''
class DataStore:
    def __init__(self):
        self._data = {}

    def set(self, key, value):
        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def has(self, key):
        return key in self._data
    
    def items(self):
        return list(self._data.items())
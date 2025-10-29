import os
import json

class SettingsService:
    """
    Servicio simple para guardar y cargar configuraciones persistentes en un archivo JSON.
    """
    def __init__(self, filename="gamma_lab_settings.json"):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.filename = os.path.join(base_dir, filename)
        self.data = {}
        self.load()

    def load(self):
        """Carga el archivo si existe."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def save(self):
        """Guarda los cambios al archivo."""
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[SettingsService] Error al guardar configuración: {e}")

    def get(self, key, default=None):
        """Obtiene un valor guardado."""
        return self.data.get(key, default)

    def set(self, key, value):
        """Guarda un valor y persiste."""
        self.data[key] = value
        self.save()

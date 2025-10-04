import os
from PyQt5.QtGui import QIcon

class AssetManager:
    """
    Resuelve iconos a partir de rutas lógicas.
    Ej.: "plugins/analysis/frequency/psd.png"
    -> assets/icons/plugins/analysis/frequency/psd.png
    """
    def __init__(self, root="assets/icons"):
        self.root = root

    def path(self, logical_path: str) -> str:
        return os.path.join(self.root, logical_path.replace("/", os.sep))

    def icon(self, logical_path: str) -> QIcon:
        return QIcon(self.path(logical_path))
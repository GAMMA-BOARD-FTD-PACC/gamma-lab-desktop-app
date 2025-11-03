from PyQt5.QtWidgets import QMessageBox, QWidget


class PluginAlerts:

    def __init__(self, parent: QWidget = None):
        self.parent = parent

    def __show_message(self, title: str, message: str, level: str):
        """Método interno para mostrar alertas con diferentes niveles."""
        print(f"[PluginAlerts] {level.upper()}: {message}")

        if not self.parent:
            # No hay contexto de interfaz (modo consola o prueba)
            return

        if level == "error":
            QMessageBox.critical(self.parent, title, message)
        elif level == "warning":
            QMessageBox.warning(self.parent, title, message)
        elif level == "info":
            QMessageBox.information(self.parent, title, message)
        else:
            raise ValueError(f"Nivel de alerta desconocido: {level}")

    def error(self, message: str, title: str = "Error"):
        self.__show_message(title, message, "error")

    def warning(self, message: str, title: str = "Warning"):
        self.__show_message(title, message, "warning")

    def info(self, message: str, title: str = "Information"):
        self.__show_message(title, message, "info")
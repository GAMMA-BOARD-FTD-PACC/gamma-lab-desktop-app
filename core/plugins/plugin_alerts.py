from PyQt5.QtWidgets import QMessageBox, QWidget, QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt5.QtCore import Qt, QTimer, QEventLoop
from PyQt5.QtGui import QMovie


class PluginAlerts:

    def __init__(self, parent: QWidget = None):
        self.parent = parent
        self._spinner_dialog = None


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

    #  SPINNER DE CARGA
    def show_spinner(self, text: str = "Procesando...", gif_path: str = None):
        """
        Muestra un spinner de carga modal sobre la ventana principal.
        Si se llama otra vez sin ocultarlo, no crea un nuevo diálogo.
        """
        if self._spinner_dialog and self._spinner_dialog.isVisible():
            return  # Ya se está mostrando un spinner

        self._spinner_dialog = QDialog(self.parent)
        self._spinner_dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._spinner_dialog.setModal(True)
        self._spinner_dialog.setAttribute(Qt.WA_TranslucentBackground)
        self._spinner_dialog.setObjectName("spinnerDialog")

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        # Spinner GIF o barra
        if gif_path:
            spinner_label = QLabel()
            movie = QMovie(gif_path)
            spinner_label.setMovie(movie)
            movie.start()
            layout.addWidget(spinner_label, alignment=Qt.AlignCenter)
        else:
            # Fallback: barra indeterminada si no hay GIF
            bar = QProgressBar()
            bar.setRange(0, 0)  # modo indeterminado
            bar.setFixedWidth(150)
            layout.addWidget(bar, alignment=Qt.AlignCenter)

        # Texto
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: white; font-size: 14px;")
        layout.addWidget(label)

        # Fondo oscuro semitransparente
        self._spinner_dialog.setStyleSheet("""
            #spinnerDialog {
                background-color: rgba(0, 0, 0, 150);
                border-radius: 10px;
            }
        """)

        self._spinner_dialog.setLayout(layout)
        self._spinner_dialog.resize(200, 120)
        self._spinner_dialog.show()

        # Forzar render inmediato
        QEventLoop().processEvents()

    def hide_spinner(self):
        """Cierra el spinner de carga si está activo."""
        if self._spinner_dialog:
            self._spinner_dialog.accept()
            self._spinner_dialog = None
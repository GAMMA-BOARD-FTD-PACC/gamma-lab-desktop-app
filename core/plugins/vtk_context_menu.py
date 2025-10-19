from PyQt5.QtWidgets import QMenu, QAction, QMessageBox, QApplication
from PyQt5.QtCore import Qt
from vtk import vtkChartXY


class VTKContextMenu:
    """
    Menú contextual general para vistas basadas en VTK.
    Incluye zoom configurable, atajos de teclado (Ctrl/Shift + rueda)
    y permite registrar acciones personalizadas desde los plugins.
    """

    def __init__(self, chart: vtkChartXY, vtk_widget, parent=None):
        """
        :param chart: instancia de vtkChartXY (u otro objeto compatible)
        :param vtk_widget: widget PyQt asociado
        :param parent: ventana principal o plugin padre
        """
        self.chart = chart
        self.vtk_widget = vtk_widget
        self.parent = parent
        self.custom_actions = []  # Acciones registradas por los plugins
        self._install_wheel_shortcuts()

        # Configuración inicial
        self.chart.SetZoomWithMouseWheel(True)
        self.chart.SetAxisZoom(0, True)
        self.chart.SetAxisZoom(1, False)

        # Conexión del menú contextual
        self.vtk_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vtk_widget.customContextMenuRequested.connect(self.show_menu)

    # Integración con rueda del mouse
    def _install_wheel_shortcuts(self):
        """
        Intercepta el evento wheelEvent del vtk_widget para implementar:
         - Ctrl + rueda → zoom horizontal
         - Shift + rueda → zoom vertical
         - Rueda sola → zoom normal
        """
        old_wheel_event = self.vtk_widget.wheelEvent

        def custom_wheel_event(event):
            modifiers = QApplication.keyboardModifiers()

            if modifiers == Qt.ControlModifier:
                self.chart.SetZoomWithMouseWheel(True)
                self.chart.SetAxisZoom(0, True)
                self.chart.SetAxisZoom(1, False)

            elif modifiers == Qt.ShiftModifier:
                self.chart.SetZoomWithMouseWheel(True)
                self.chart.SetAxisZoom(0, False)
                self.chart.SetAxisZoom(1, True)

            else:
                # Zoom normal (ambos ejes)
                self.chart.SetZoomWithMouseWheel(True)
                self.chart.SetAxisZoom(0, True)
                self.chart.SetAxisZoom(1, True)

            # Llama al comportamiento original
            old_wheel_event(event)

        # Sobrescribimos el método wheelEvent
        self.vtk_widget.wheelEvent = custom_wheel_event

    # -------------------------------
    # Registro de acciones personalizadas
    # -------------------------------
    def add_action(self, text, callback):
        """
        Permite a los plugins registrar acciones personalizadas.
        Ejemplo:
            menu.add_action("Marcar pico", self.on_mark_peak)
        """
        self.custom_actions.append((text, callback))

    # Mostrar menú contextual
    def show_menu(self, pos):
        menu = QMenu()

        # Sección de zoom
        zoom_menu = menu.addMenu("Zoom")
        zoom_menu.addAction("Horizontal (X)", lambda: self.set_zoom_mode("x"))
        zoom_menu.addAction("Vertical (Y)", lambda: self.set_zoom_mode("y"))
        zoom_menu.addAction("Ambos ejes (X+Y)", lambda: self.set_zoom_mode("xy"))
        zoom_menu.addAction("Restablecer vista", self.reset_zoom)

        # Sección de marcadores
        marker_menu = menu.addMenu("Marcadores")
        marker_menu.addAction("Agregar marcador", self.add_marker)
        marker_menu.addAction("Eliminar marcadores", self.clear_markers)

        # Acciones personalizadas
        if self.custom_actions:
            menu.addSeparator()
            for text, callback in self.custom_actions:
                menu.addAction(text, callback)

        # Mostrar menú contextual
        menu.exec_(self.vtk_widget.mapToGlobal(pos))

    # -------------------------------
    # Funciones base de zoom
    # -------------------------------
    def set_zoom_mode(self, mode):
        if mode == "x":
            self.chart.SetAxisZoom(0, True)
            self.chart.SetAxisZoom(1, False)
        elif mode == "y":
            self.chart.SetAxisZoom(0, False)
            self.chart.SetAxisZoom(1, True)
        elif mode == "xy":
            self.chart.SetAxisZoom(0, True)
            self.chart.SetAxisZoom(1, True)

    def reset_zoom(self):
        try:
            self.chart.ResetZoom()
        except AttributeError:
            QMessageBox.information(self.parent, "Zoom", "No se pudo restablecer el zoom en esta versión de VTK.")

    # -------------------------------
    # Funciones de marcador (placeholder)
    # -------------------------------
    def add_marker(self):
        QMessageBox.information(self.parent, "Marcador", "Función de agregar marcador aún no implementada.")

    def clear_markers(self):
        QMessageBox.information(self.parent, "Marcadores", "Función de eliminar marcadores aún no implementada.")

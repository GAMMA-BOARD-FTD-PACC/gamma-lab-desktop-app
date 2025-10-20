from datetime import datetime
from PyQt5.QtWidgets import QMenu, QAction, QMessageBox, QApplication, QFileDialog
from PyQt5.QtCore import Qt
from vtk import vtkChartXY

import csv
import json
import csv
import os
import vtk
import pandas as pd


class VTKContextMenu:
    """
    Menú contextual general para vistas basadas en VTK.
    Incluye zoom configurable, atajos de teclado (Ctrl/Shift + rueda)
    y permite registrar acciones personalizadas desde los plugins.
    """
    last_export_dir = os.getcwd()



    def __init__(self, chart: vtkChartXY, vtk_widget, singal_name=None, channel_name=None, plugin_name=None, parent=None):
        """
        :param chart: instancia de vtkChartXY (u otro objeto compatible)
        :param vtk_widget: widget PyQt asociado
        :param parent: ventana principal o plugin padre
        """
        self.chart = chart
        self.vtk_widget = vtk_widget
        self.parent = parent
        self.signal_name = singal_name
        self.chanel_name = channel_name
        self.plugin_name = plugin_name
        self.custom_actions = []  # Acciones registradas por los plugins
        self._install_wheel_shortcuts()


        # Configuración inicial (uno o varios charts)
        charts = self._get_charts()
        for ch in charts:
            if ch is not None:
                ch.SetZoomWithMouseWheel(True)
                ch.SetAxisZoom(0, True)
                ch.SetAxisZoom(1, False)   

        # Conexión del menú contextual
        self.vtk_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vtk_widget.customContextMenuRequested.connect(self.show_menu)

    def _get_charts(self):
        """Devuelve una lista con todos los charts activos."""
        if isinstance(self.chart, list):
            return [ch for ch in self.chart if ch is not None]
        elif self.chart is not None:
            return [self.chart]
        return []

    def set_signal_name(self, name):
        self.signal_name = name
    
    def set_channel_name(self, name):
        self.chanel_name = name
    
    def set_plugin_name(self, name):
        self.plugin_name = name

    def set_chart(self, chart):
        self.chart = chart

    # Integración con rueda del mouse
    def _install_wheel_shortcuts(self):
        """
        Intercepta el evento wheelEvent del vtk_widget para implementar:
         - Ctrl + rueda → zoom horizontal
         - Shift + rueda → zoom vertical
         - Rueda sola → zoom normal
        """
        old_wheel_event = self.vtk_widget.wheelEvent

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
            charts = self._get_charts()

            for ch in charts:
                if ch is None:
                    continue

                ch.SetZoomWithMouseWheel(True)

                if modifiers == Qt.ControlModifier:
                    ch.SetAxisZoom(0, True)
                    ch.SetAxisZoom(1, False)
                elif modifiers == Qt.ShiftModifier:
                    ch.SetAxisZoom(0, False)
                    ch.SetAxisZoom(1, True)
                else:
                    ch.SetAxisZoom(0, True)
                    ch.SetAxisZoom(1, True)

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

        # Sección para exportar
        menu.addSeparator()
        export_img_menu = menu.addMenu("Export as image")
        export_img_menu.addAction("png", lambda: self.export_image("png"))
        export_img_menu.addAction("jpg", lambda: self.export_image("jpg"))
        export_img_menu.addAction("jpegpg", lambda: self.export_image("jpeg"))
        export_img_menu.addAction("bmp", lambda: self.export_image("bmp"))
        export_img_menu.addAction("tiff", lambda: self.export_image("tiff"))

        export_table_menu = menu.addMenu("Exportar tabla")
        export_table_menu.addAction("csv", lambda: self.export_table("csv"))
        export_table_menu.addAction("json", lambda: self.export_table("json"))
        export_table_menu.addAction("xlsx", lambda: self.export_table("xlsx"))

        export_table_menu.addAction("Exportar tabla")


        # Acciones personalizadas
        if self.custom_actions:
            menu.addSeparator()
            for text, callback in self.custom_actions:
                menu.addAction(text, callback)

        # Mostrar menú contextual
        menu.exec_(self.vtk_widget.mapToGlobal(pos))

    #Funciones para exportar

    def export_image(self, format: str, filename: str = None):
        """
        Exporta el contenido actual del widget VTK como imagen.
        Abre un diálogo para que el usuario elija la carpeta y el nombre final.
        :param format: Formato ('png', 'jpg', 'bmp', 'tiff')
        :param filename: Ruta completa opcional (si se pasa, no se abre diálogo)
        """
        try:

            # Generar nombre sugerido
            if self.chanel_name:
                base_name = f"{self.signal_name}_{self.chanel_name}_{self.plugin_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"
            else:
                base_name = f"{self.signal_name}_{self.plugin_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"


            initial_path = os.path.join(VTKContextMenu.last_export_dir or os.getcwd(), base_name)

            # Si no se da filename, abrir diálogo
            if not filename:
                
                file_filter = f"Imagen (*.{format})"
                filename, _ = QFileDialog.getSaveFileName(
                    self.parent,
                    "Guardar imagen como...",
                    initial_path,
                    file_filter
                )

                # Si el usuario canceló
                if not filename:
                    return
            
            # Guardar la carpeta usada como última ruta
            VTKContextMenu.last_export_dir = os.path.dirname(filename)

            # Obtener la ventana VTK
            window = self.vtk_widget.GetRenderWindow()

            # Capturar contenido del render
            w2i = vtk.vtkWindowToImageFilter()
            w2i.SetInput(window)
            w2i.Update()

            # Seleccionar writer según formato
            ext = format if format != "jpeg" else "jpg"
            if ext == "png":
                writer = vtk.vtkPNGWriter()
            elif ext in ["jpg", "jpeg"]:
                writer = vtk.vtkJPEGWriter()
            elif ext == "bmp":
                writer = vtk.vtkBMPWriter()
            elif ext in ["tiff", "tif"]:
                writer = vtk.vtkTIFFWriter()
            else:
                QMessageBox.warning(self.parent, "Error", f"Formato '{format}' no soportado.")
                return

            writer.SetFileName(filename)
            writer.SetInputConnection(w2i.GetOutputPort())
            writer.Write()

            QMessageBox.information(
                self.parent,
                "Exportación exitosa",
                f"Imagen exportada correctamente {base_name}"
            )

        except Exception as e:
            QMessageBox.warning(self.parent, "Error al exportar imagen", str(e))

    def export_table(self,  fmt: str, filename: str = None):
        """
        Exporta los datos de las series del vtkChartXY a un archivo CSV, XLSX o JSON.
        Cada serie se guarda con sus valores X e Y.
        
        Parámetros:
            filename (str): ruta de archivo opcional
            fmt (str): formato de salida ("csv", "xlsx", "json")
        """
        try:
            charts = self._get_charts()
            if not charts:
                QMessageBox.warning(self.parent, "Error", "No hay gráficos para exportar.")
                return

            chart = charts[0]
            if chart.GetNumberOfPlots() == 0:
                QMessageBox.warning(self.parent, "Error", "El gráfico no contiene datos para exportar.")
                return


            # Nombre base del archivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = (
                f"{self.signal_name}_{self.chanel_name}_{self.plugin_name}_{timestamp}.{fmt}"
                if self.chanel_name else
                f"{self.signal_name}_{self.plugin_name}_{timestamp}.{fmt}"
            )

            initial_path = os.path.join(VTKContextMenu.last_export_dir or os.getcwd(), base_name)

            # Diálogo si no se da filename
            if not filename:
                filters = {
                    "csv": "Archivo CSV (*.csv)",
                    "xlsx": "Archivo Excel (*.xlsx)",
                    "json": "Archivo JSON (*.json)"
                }
                filename, _ = QFileDialog.getSaveFileName(
                    self.parent,
                    f"Guardar tabla como {fmt.upper()}...",
                    initial_path,
                    filters[fmt]
                )
                if not filename:
                    return

            # Guardar carpeta global
            VTKContextMenu.last_export_dir = os.path.dirname(filename)

            # Extraer datos de las series
            data_rows = []
            headers = []

            for i in range(chart.GetNumberOfPlots()):
                plot = chart.GetPlot(i)
                table = plot.GetInput()
                if table is None:
                    continue

                x_col = table.GetColumn(0)
                y_col = table.GetColumn(1)
                num_points = table.GetNumberOfRows()

                series_name = plot.GetLabel() or f"Serie_{i + 1}"
                headers.extend([f"{series_name}_X", f"{series_name}_Y"])

                for row_idx in range(num_points):
                    x_val = x_col.GetValue(row_idx)
                    y_val = y_col.GetValue(row_idx)
                    if len(data_rows) <= row_idx:
                        data_rows.append([])
                    data_rows[row_idx].extend([x_val, y_val])

            # Guardar según formato
            if fmt == "csv":
                with open(filename, mode="w", newline="", encoding="utf-8") as file:
                    writer = csv.writer(file)
                    writer.writerow(headers)
                    writer.writerows(data_rows)

            elif fmt == "xlsx":
                df = pd.DataFrame(data_rows, columns=headers)
                df.to_excel(filename, index=False)

            elif fmt == "json":
                data_dict = [dict(zip(headers, row)) for row in data_rows]
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data_dict, f, ensure_ascii=False, indent=4)

            QMessageBox.information(
                self.parent,
                "Exportación exitosa",
                f"Datos exportados correctamente a:\n{base_name}"
            )

        except Exception as e:
            QMessageBox.warning(self.parent, "Error al exportar tabla", str(e))

    # Funciones base de zoom
    def set_zoom_mode(self, mode):
        charts = self._get_charts()
        for ch in charts:
            if ch is None:
                continue
            if mode == "x":
                ch.SetAxisZoom(0, True)
                ch.SetAxisZoom(1, False)
            elif mode == "y":
                ch.SetAxisZoom(0, False)
                ch.SetAxisZoom(1, True)
            elif mode == "xy":
                ch.SetAxisZoom(0, True)
                ch.SetAxisZoom(1, True)

    def reset_zoom(self):
        charts = self._get_charts()
        for ch in charts:
            try:
                ch.RecalculateBounds()  # método más seguro que ResetZoom
            except AttributeError:
                QMessageBox.information(
                    self.parent,
                    "Zoom",
                    "No se pudo restablecer el zoom en esta versión de VTK."
                )
   
    # Funciones de marcador (placeholder)
    def add_marker(self):
        QMessageBox.information(self.parent, "Marcador", "Función de agregar marcador aún no implementada.")

    def clear_markers(self):
        QMessageBox.information(self.parent, "Marcadores", "Función de eliminar marcadores aún no implementada.")

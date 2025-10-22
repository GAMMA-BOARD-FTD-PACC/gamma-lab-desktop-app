
from datetime import datetime
from PyQt5.QtWidgets import QMenu, QAction, QMessageBox, QApplication, QFileDialog, QToolTip
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from vtk import vtkChartXY, vtkTable, vtkPen, vtkFloatArray, vtkChart
import math
import itertools
import bisect

from core.filters.measurements import two_point_metrics

try:
    from vtkmodules.vtkChartsCore import vtkPlotPoints
except Exception:
    vtkPlotPoints = None

# para re-ligar columnas por nombre y evitar caches raros
try:
    from vtkmodules.vtkCommonDataModel import vtkDataObject
except Exception:
    vtkDataObject = None

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
    
    _PALETTE = [
        (220, 20, 60), (30, 144, 255), (50, 205, 50), (255, 140, 0),
        (148, 0, 211), (0, 191, 255), (255, 99, 71), (0, 128, 128),
    ]
    _CLICK_EPS = 8
    _PICK_RADIUS_PX = 10

    def __init__(self, chart: vtkChartXY, vtk_widget, singal_name=None, channel_name=None, plugin_name=None, parent=None):
        self.chart = chart
        self.vtk_widget = vtk_widget
        self.parent = parent
        self.signal_name = singal_name
        self.chanel_name = channel_name
        self.plugin_name = plugin_name
        self.custom_actions = []

        # Estado medición
        self._meas_state = 'idle'
        self._current = None      # dict con keys: type, p1, p2, plot, table, color
        self._down_pos = None

        # Mediciones persistentes (overlay en pantalla)
        self._measurements = []
        self._color_cycle = itertools.cycle(self._PALETTE)

        # Interacción / ejes
        self._saved_actions = {}
        self._saved_ranges = None      # {'x':(min,max),'y':(min,max)}
        self._ref_axes = None          # {'x':vtkAxis,'y':vtkAxis}
        self._invert_y = False

        # Datos de referencia para snap
        self._ref_data = None          # {'xs': list[float], 'ys': list[float]}

        # Callback externo
        self._on_measure_result = None

        # DataStore (inyectable)
        self._datastore = None  # <-- NUEVO

        # DEBUG
        self._debug = True

        self._install_wheel_shortcuts()
        self._install_mouse_observers()

        for ch in self._get_charts():
            if ch:
                ch.SetZoomWithMouseWheel(True)
                ch.SetAxisZoom(0, True); ch.SetAxisZoom(1, True)

        self.vtk_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vtk_widget.customContextMenuRequested.connect(self.show_menu)

    # ---------- utils ----------
    def _log(self, *args):
        if self._debug:
            print(*args)

    def _get_charts(self):
        if isinstance(self.chart, list):
            return [ch for ch in self.chart if ch is not None]
        return [self.chart] if self.chart is not None else []

    def _active_chart(self):
        return (self.chart[0] if isinstance(self.chart, list) and self.chart
                else self.chart)
    def set_signal_name(self, name):
        self.signal_name = name
    
    def set_channel_name(self, name):
        self.chanel_name = name
    
    def set_plugin_name(self, name):
        self.plugin_name = name

    def set_chart(self, chart):
        self.chart = chart

    # API externa
    def set_measurement_callback(self, cb):
        self._on_measure_result = cb

    def set_datastore(self, store):  # <-- NUEVO
        """Inyecta el servicio DataStore para persistir mediciones."""
        self._datastore = store

    def get_measurements(self):
        return [
            {'type': m['type'], 'p1': m['p1'], 'p2': m['p2'], 'color': m['color']}
            for m in self._measurements
        ]

    def clear_all_measurements(self):
        ch = self._active_chart()
        for m in self._measurements:
            try:
                if ch and m.get('plot'):
                    ch.RemovePlotInstance(m['plot'])
            except Exception:
                pass
        self._measurements.clear()
        self.vtk_widget.GetRenderWindow().Render()

    def remove_last_measurement(self):
        if not self._measurements:
            return
        ch = self._active_chart()
        m = self._measurements.pop()
        try:
            if ch and m.get('plot'):
                ch.RemovePlotInstance(m['plot'])
        except Exception:
            pass
        self.vtk_widget.GetRenderWindow().Render()

    # ---------- rueda ----------
    def _install_wheel_shortcuts(self):
        old_wheel_event = self.vtk_widget.wheelEvent

        def custom_wheel_event(event):
            modifiers = QApplication.keyboardModifiers()
            for ch in self._get_charts():
                if not ch: continue
                ch.SetZoomWithMouseWheel(True)
                if modifiers == Qt.ControlModifier:
                    ch.SetAxisZoom(0, True);  ch.SetAxisZoom(1, False)
                elif modifiers == Qt.ShiftModifier:
                    ch.SetAxisZoom(0, False); ch.SetAxisZoom(1, True)
                else:
                    ch.SetAxisZoom(0, True);  ch.SetAxisZoom(1, True)

            old_wheel_event(event)

            if self._meas_state != 'idle':
                self._save_axes_ranges()
                #self._log("[ZOOM] Ranges updated during measure:", self._saved_ranges)

        self.vtk_widget.wheelEvent = custom_wheel_event

    # ---------- menú ----------
    def add_action(self, text, callback):
        self.custom_actions.append((text, callback))

    def show_menu(self, pos):
        menu = QMenu()
        zoom_menu = menu.addMenu("Zoom")
        zoom_menu.addAction("Horizontal (X)", lambda: self.set_zoom_mode("x"))
        zoom_menu.addAction("Vertical (Y)",   lambda: self.set_zoom_mode("y"))
        zoom_menu.addAction("Ambos ejes (X+Y)", lambda: self.set_zoom_mode("xy"))
        zoom_menu.addAction("Restablecer vista", self.reset_zoom)

        measure_menu = menu.addMenu("Medidas")
        measure_menu.addAction("Pendiente (2 puntos – clic IZQ.)",lambda: self.start_measure('slope'))
        measure_menu.addSeparator()
        measure_menu.addAction("Eliminar última medición", self.remove_last_measurement)
        measure_menu.addAction("Eliminar todas las mediciones", self.clear_all_measurements)

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
            for text, cb in self.custom_actions:
                menu.addAction(text, cb)

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
        for ch in self._get_charts():
            if not ch: continue
            if mode == "x":
                ch.SetAxisZoom(0, True);  ch.SetAxisZoom(1, False)
            elif mode == "y":
                ch.SetAxisZoom(0, False); ch.SetAxisZoom(1, True)
            elif mode == "xy":
                ch.SetAxisZoom(0, True);  ch.SetAxisZoom(1, True)

    def reset_zoom(self):
        for ch in self._get_charts():
            try:
                ch.RecalculateBounds()
            except AttributeError:
                QMessageBox.information(self.parent, "Zoom",
                    "No se pudo restablecer el zoom en esta versión de VTK.")

    # ---------- medición (flujo) ----------
    def _install_mouse_observers(self):
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        iren.AddObserver("LeftButtonPressEvent", self._on_left_press, 1.0)
        iren.AddObserver("LeftButtonReleaseEvent", self._on_left_release, 1.0)
        iren.AddObserver("MouseMoveEvent", self._on_mouse_move_block_hover, 1.0)
        
    def _on_mouse_move_block_hover(self, obj, evt):
        if self._meas_state == 'idle':
            return
        return 1
    
    def start_measure(self, measure_type: str):
        if self._meas_state != 'idle':
            self._cancel_current_overlay()

        self.vtk_widget.GetRenderWindow().Render()
        self._meas_state = 'waiting_p1'

        self._detect_reference_axes()
        self._save_axes_ranges()
        self._autodetect_y_inversion()
        self._load_reference_data_for_pick()

        # Creamos overlay YA para que __plot_one__ sea transversal
        color = next(self._color_cycle)
        plot, table = self._create_overlay_plot(color)
        self._current = {'type': measure_type, 'p1': None, 'p2': None,
                         'plot': plot, 'table': table, 'color': color}

        self._suspend_left_actions(True)

        #self._log("[MEAS] Start", measure_type,"ranges:", self._saved_ranges,"invert_y:", self._invert_y,"ref_data len:", 0 if not self._ref_data else len(self._ref_data.get('xs', [])))

        QMessageBox.information(self.parent, "Medición",
                                "Selecciona el PRIMER punto con CLIC IZQUIERDO.")

    def cancel_measurement(self):
        self._cancel_current_overlay()

    def _cancel_current_overlay(self):
        ch = self._active_chart()
        if self._current and self._current.get('plot') and ch:
            try:
                ch.RemovePlotInstance(self._current['plot'])
            except Exception:
                pass
        self._current = None
        self._meas_state = 'idle'
        self._suspend_left_actions(False)
        self._saved_ranges = None
        self._ref_axes = None
        self._ref_data = None
        self.vtk_widget.GetRenderWindow().Render()

    # ---------- eventos mouse ----------
    def _on_left_press(self, obj, evt):
        if self._meas_state != 'idle':
            iren = self.vtk_widget.GetRenderWindow().GetInteractor()
            self._down_pos = iren.GetEventPosition()

    def _on_left_release(self, obj, evt):
        if self._meas_state == 'idle':
            return

        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        sx, sy = iren.GetEventPosition()
        dx = dy = 0
        if self._down_pos is not None:
            dx = abs(sx - self._down_pos[0]); dy = abs(sy - self._down_pos[1])
        self._down_pos = None

        if dx > self._CLICK_EPS or dy > self._CLICK_EPS:
            self._log(f"[MEAS] Ignored drag release ({dx},{dy})")
            return

        self._save_axes_ranges()
        if self._meas_state == 'waiting_p2':
            self._log(f"[MEAS][P2] release at screen=({sx},{sy}) with ranges={self._saved_ranges}")

        p = self._pick_nearest_data_point(sx, sy)
        if p is None:
            QMessageBox.warning(self.parent, "Medición",
                                "Debes seleccionar sobre un punto válido de la señal.")
            return

        if self._meas_state == 'waiting_p1':
            self._current['p1'] = p
            self._log(f"[MEAS] P1 set = {p}")
            self.__plot_one__(p, clear=True)
            self._show_point_tooltip(p, "P1")
            self._meas_state = 'waiting_p2'
            QMessageBox.information(self.parent, "Medición", "Ahora selecciona el SEGUNDO punto con CLIC IZQUIERDO.")
            return

        if self._meas_state == 'waiting_p2':
            self._current['p2'] = p
            self._log(f"[MEAS] P2 set = {p}")
            self.__plot_one__(p, clear=False)
            self._show_point_tooltip(p, "P2")
            self._finalize_current_measurement()
            self._meas_state = 'idle'
            self._suspend_left_actions(False)
            self._saved_ranges = None
            self._ref_axes = None
            self._ref_data = None
            return

    # ---------- ejes / rangos ----------
    def _detect_reference_axes(self):
        ch = self._active_chart()
        self._ref_axes = None
        if not ch:
            return
        try:
            n = ch.GetNumberOfPlots()
        except Exception:
            n = 0

        ref_plot = None
        for i in range(n):
            pl = ch.GetPlot(i)
            if pl is None:
                continue
            if any(pl is m.get('plot') for m in self._measurements):
                continue
            if self._current and pl is self._current.get('plot'):
                continue
            ref_plot = pl
            break

        if ref_plot and hasattr(ref_plot, "GetXAxis") and hasattr(ref_plot, "GetYAxis"):
            x_axis = ref_plot.GetXAxis(); y_axis = ref_plot.GetYAxis()
            if x_axis and y_axis:
                self._ref_axes = {'x': x_axis, 'y': y_axis}
                self._log("[MEAS] Ref axes from series.")
                return

        self._ref_axes = {'x': ch.GetAxis(0), 'y': ch.GetAxis(1)}
        self._log("[MEAS] Ref axes default (BOTTOM/LEFT).")

    def _save_axes_ranges(self):
        ch = self._active_chart()
        if not ch: return
        if self._ref_axes:
            ax_x = self._ref_axes['x']; ax_y = self._ref_axes['y']
        else:
            ax_x = ch.GetAxis(0); ax_y = ch.GetAxis(1)
        self._saved_ranges = {
            'x': (ax_x.GetMinimum(), ax_x.GetMaximum()),
            'y': (ax_y.GetMinimum(), ax_y.GetMaximum()),
        }
        #self._log("[RANGES] Saved:", self._saved_ranges)

    def _restore_axes_ranges(self):
        ch = self._active_chart()
        if not ch or not self._saved_ranges: return
        if self._ref_axes:
            ax_x = self._ref_axes['x']; ax_y = self._ref_axes['y']
        else:
            ax_x = ch.GetAxis(0); ax_y = ch.GetAxis(1)
        xmin, xmax = self._saved_ranges['x']
        ymin, ymax = self._saved_ranges['y']
        try:
            ax_x.SetRange(xmin, xmax)
            ax_y.SetRange(ymin, ymax)
        except Exception:
            pass
        self.vtk_widget.GetRenderWindow().Render()

    def _autodetect_y_inversion(self):
        if not self._saved_ranges:
            self._save_axes_ranges()
        rect = self._plot_rect_pixels()
        if rect is None:
            return
        x_min_px, x_max_px, y_min_px, y_max_px = rect
        x_mid = (self._saved_ranges['x'][0] + self._saved_ranges['x'][1]) * 0.5

        sy_min = self._plot_to_screen(x_mid, self._saved_ranges['y'][0])
        sy_max = self._plot_to_screen(x_mid, self._saved_ranges['y'][1])
        if sy_min is None or sy_max is None:
            self._invert_y = False
            return
        sy_min = sy_min[1]; sy_max = sy_max[1]
        self._invert_y = (sy_max < sy_min)
        self._log("[Y-INVERT] invert_y =", self._invert_y,
                  " sy(y_min)=", sy_min, " sy(y_max)=", sy_max,
                  " rect y_min_px/y_max_px=", y_min_px, y_max_px)

    # ---------- datos para snap ----------
    def _load_reference_data_for_pick(self):
        self._ref_data = None
        ch = self._active_chart()
        if not ch: return

        ref_plot = None
        try:
            n = ch.GetNumberOfPlots()
        except Exception:
            n = 0
        for i in range(n):
            pl = ch.GetPlot(i)
            if pl is None: continue
            if any(pl is m.get('plot') for m in self._measurements):
                continue
            if self._current and pl is self._current.get('plot'):
                continue
            ref_plot = pl
            break
        if ref_plot is None: return

        try:
            table = ref_plot.GetInput()
        except Exception:
            table = None
        if table is None: return

        def _find_col_by_name(names):
            for nm in names:
                try:
                    arr = table.GetColumnByName(nm)
                    if arr is not None:
                        return arr
                except Exception:
                    pass
            return None

        x_arr = _find_col_by_name(("Time", "time", "X", "x"))
        y_arr = _find_col_by_name(("Value", "value", "Y", "y"))

        if x_arr is None or y_arr is None:
            num_cols = table.GetNumberOfColumns()
            cols = []
            for j in range(num_cols):
                arr = table.GetColumn(j)
                if hasattr(arr, "GetNumberOfTuples"):
                    cols.append(arr)
            if len(cols) >= 2:
                x_arr = cols[0] if x_arr is None else x_arr
                y_arr = cols[1] if y_arr is None else y_arr

        if x_arr is None or y_arr is None:
            #self._log("[PICK] No columns for snap.")
            return

        nrows = min(x_arr.GetNumberOfTuples(), y_arr.GetNumberOfTuples())
        xs, ys = [], []
        for i in range(nrows):
            xs.append(float(x_arr.GetValue(i)))
            ys.append(float(y_arr.GetValue(i)))

        pairs = sorted(zip(xs, ys), key=lambda t: t[0])
        if pairs:
            xs_sorted, ys_sorted = [pairs[0][0]], [pairs[0][1]]
            eps = 1e-12
            for j in range(1, len(pairs)):
                xj, yj = pairs[j]
                if xj <= xs_sorted[-1]:
                    xj = xs_sorted[-1] + eps
                xs_sorted.append(xj)
                ys_sorted.append(yj)
            self._ref_data = {'xs': xs_sorted, 'ys': ys_sorted}
        else:
            self._ref_data = {'xs': [], 'ys': []}

        self._log("[PICK] Loaded ref data: N =", len(self._ref_data['xs']))

    # ---------- mapeos pantalla<->datos ----------
    def _vec2_to_xy(self, v):
        if isinstance(v, (tuple, list)) and len(v) == 2:
            return float(v[0]), float(v[1])
        if hasattr(v, "GetX") and hasattr(v, "GetY"):
            return float(v.GetX()), float(v.GetY())
        if hasattr(v, "x") and hasattr(v, "y"):
            return float(v.x), float(v.y)
        return None, None

    def _plot_rect_pixels(self):
        ch = self._active_chart()
        if not ch: return None
        p1 = ch.GetPoint1(); p2 = ch.GetPoint2()
        x1, y1 = self._vec2_to_xy(p1); x2, y2 = self._vec2_to_xy(p2)
        if x1 is None or x2 is None: return None
        return x1, x2, y1, y2

    def _plot_to_screen(self, x_val, y_val):
        rect = self._plot_rect_pixels()
        if rect is None or self._saved_ranges is None:
            return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect
        x_min, x_max = self._saved_ranges['x']
        y_min, y_max = self._saved_ranges['y']

        dx_pix = (x_max_px - x_min_px); dy_pix = (y_max_px - y_min_px)
        if dx_pix <= 0 or dy_pix <= 0: return None

        sx = x_min_px + (x_val - x_min) * dx_pix / (x_max - x_min)
        if not self._invert_y:
            sy = y_min_px + (y_val - y_min) * dy_pix / (y_max - y_min)
        else:
            sy = y_min_px + (y_max - y_val) * dy_pix / (y_max - y_min)
        return float(sx), float(sy)

    def _screen_to_plot(self, sx: float, sy: float):
        ch = self._active_chart()
        if not ch: return None

        rect = self._plot_rect_pixels()
        if rect is None: return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect

        if sx < x_min_px or sx > x_max_px or sy < y_min_px or sy > y_max_px:
            return None

        if self._saved_ranges:
            x_min, x_max = self._saved_ranges['x']
            y_min, y_max = self._saved_ranges['y']
        else:
            if self._ref_axes:
                x_min, x_max = self._ref_axes['x'].GetMinimum(), self._ref_axes['x'].GetMaximum()
                y_min, y_max = self._ref_axes['y'].GetMinimum(), self._ref_axes['y'].GetMaximum()
            else:
                ax_x = ch.GetAxis(0); ax_y = ch.GetAxis(1)
                x_min, x_max = ax_x.GetMinimum(), ax_x.GetMaximum()
                y_min, y_max = ax_y.GetMinimum(), ax_y.GetMaximum()

        dx_pix = (x_max_px - x_min_px); dy_pix = (y_max_px - y_min_px)
        if dx_pix <= 0 or dy_pix <= 0:
            return None

        x_val = x_min + (sx - x_min_px) * (x_max - x_min) / dx_pix
        if not self._invert_y:
            y_val = y_min + (sy - y_min_px) * (y_max - y_min) / dy_pix
        else:
            y_val = y_min + (y_max - sy) * (y_max - y_min) / dy_pix

        return float(x_val), float(y_val)

    def _pick_nearest_data_point(self, sx_click, sy_click):
        if not self._ref_data or not self._ref_data.get('xs'):
            self._log("[PICK] No ref_data; cannot snap.")
            return None

        rect = self._plot_rect_pixels()
        if rect is None:
            self._log("[PICK] No plot rect.")
            return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect
        if not (x_min_px <= sx_click <= x_max_px and y_min_px <= sy_click <= y_max_px):
            self._log(f"[PICK] Click out of rect: ({sx_click},{sy_click}) not in "
                      f"x[{x_min_px},{x_max_px}] y[{y_min_px},{y_max_px}]")
            return None

        guess = self._screen_to_plot(sx_click, sy_click)
        if guess is None:
            self._log("[PICK] screen_to_plot returned None.")
            return None
        xg, yg = guess

        xs = self._ref_data['xs']; ys = self._ref_data['ys']

        i = bisect.bisect_left(xs, xg)
        cand_idx = [max(0, i-2), max(0, i-1), min(len(xs)-1, i), min(len(xs)-1, i+1)]
        seen = set(); cand_idx = [c for c in cand_idx if not (c in seen or seen.add(c))]

        best = None; best_d2 = None; best_idx = None
        dist_log = []
        for idx in cand_idx:
            sp = self._plot_to_screen(xs[idx], ys[idx])
            if sp is None:
                continue
            sx, sy = sp
            d2 = (sx - sx_click)**2 + (sy - sy_click)**2
            dist_log.append((idx, xs[idx], ys[idx], sx, sy, d2))
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best = (xs[idx], ys[idx])
                best_idx = idx

        self._log(f"[PICK] click=({sx_click},{sy_click}) guess=({xg:.6f},{yg:.6f}) "
                  f"i={i} cand={cand_idx} ranges={self._saved_ranges} invert_y={self._invert_y}")
        for (idx, x, y, sx, sy, d2) in dist_log:
            self._log(f"       cand idx={idx} x={x:.6f} y={y:.6f} "
                      f"→ screen=({sx:.1f},{sy:.1f}) d2={d2:.1f}")
        if best is None:
            self._log("[PICK] No candidate projected.")
            return None
        self._log(f"[PICK] best idx={best_idx} point=({best[0]:.6f},{best[1]:.6f}) "
                  f"d={math.sqrt(best_d2):.2f}px (thr={self._PICK_RADIUS_PX}px)")

        if best_d2 <= (self._PICK_RADIUS_PX * self._PICK_RADIUS_PX):
            return best
        return None


    def _bind_plot_to_table_axes(self, plot, table):
        """Enlaza (o re-enlaza) el plot a la tabla/columnas/ejes cada vez."""
        try:
            plot.SetInputData(table, 0, 1)
        except Exception:
            pass
        try:
            plot.SetUseIndexForXSeries(False)
        except Exception:
            pass

        # Re-ligar por nombre para evitar que VTK ignore indices
        try:
            from vtkmodules.vtkCommonDataModel import vtkDataObject
            plot.SetInputArray(vtkDataObject.FIELD_ASSOCIATION_ROWS, "X", 0)
            plot.SetInputArray(vtkDataObject.FIELD_ASSOCIATION_ROWS, "Y", 1)
        except Exception:
            try:
                plot.SetInputArray(0, "X")
                plot.SetInputArray(1, "Y")
            except Exception:
                pass

        # Volver a fijar ejes de referencia (evita que el plot se vaya a ejes por default)
        if self._ref_axes:
            try:
                plot.SetXAxis(self._ref_axes['x'])
                plot.SetYAxis(self._ref_axes['y'])
            except Exception:
                pass

        # Logs de control
        try:
            use_idx = plot.GetUseIndexForXSeries()
        except Exception:
            use_idx = "?"
        try:
            cols = (table.GetColumn(0).GetName(), table.GetColumn(1).GetName())
        except Exception:
            cols = ("?", "?")
        #self._log(f"[BIND] UseIndex={use_idx} cols={cols}")
    # -----------------------------------------------------------------------------

    # --- overlay helpers ---
    def __ensure_overlay__(self, color=None):
        if not self._current or not self._current.get('plot') or not self._current.get('table'):
            if color is None:
                color = next(self._color_cycle)
            plot, table = self._create_overlay_plot(color)
            self._current = {'type': 'slope', 'p1': None, 'p2': None,
                            'plot': plot, 'table': table, 'color': color}
        else:
            self._bind_plot_to_table_axes(self._current['plot'], self._current['table'])

    def __set_overlay_points__(self, points, expected_points=None):
        if not self._current or not self._current.get('plot') or not self._current.get('table'):
            return
        table = self._current['table']
        plot  = self._current['plot']

        table.SetNumberOfRows(0)
        for (x, y) in points:
            r = table.InsertNextBlankRow()
            table.SetValue(r, 0, float(x)); table.SetValue(r, 1, float(y))

        self._log(f"[PLOT][SET] before rows={table.GetNumberOfRows()}")
        self._dump_overlay_table(table, "[PLOT] dump after set_points")

        try:
            self._bind_plot_to_table_axes(plot, table)
            self._log("[BIND] UseIndex=False cols=('X','Y')")
        except Exception:
            pass

        try:
            plot.SetVisible(table.GetNumberOfRows() > 0)
        except Exception:
            pass

        try: plot.Modified()
        except Exception: pass
        table.Modified()
        self._restore_axes_ranges()
        self.vtk_widget.GetRenderWindow().Render()

        if expected_points is None:
            expected_points = points
        self._verify_overlay_consistency(expected_points)

    def __plot_one__(self, point, *, clear=False):
        self.__append_overlay_point__(point, clear=clear)

    def __append_overlay_point__(self, point, clear=False):
        self.__ensure_overlay__(self._current['color'] if self._current else None)
        if not self._current or not self._current.get('table') or not self._current.get('plot'):
            return

        table = self._current['table']
        plot  = self._current['plot']

        if clear:
            table.SetNumberOfRows(0)

        r = table.InsertNextBlankRow()
        table.SetValue(r, 0, float(point[0]))
        table.SetValue(r, 1, float(point[1]))

        try:
            self._bind_plot_to_table_axes(plot, table)
            plot.SetVisible(table.GetNumberOfRows() > 0)
        except Exception:
            pass

        try: plot.Modified()
        except Exception: pass
        table.Modified()
        self._restore_axes_ranges()
        self.vtk_widget.GetRenderWindow().Render()
        
    def _create_overlay_plot(self, color_rgb):
        ch = self._active_chart()
        if not ch:
            return None, None
        try: ch.Modified()
        except Exception: pass

        table = vtkTable()
        arr_x = vtkFloatArray(); arr_x.SetName("X")
        arr_y = vtkFloatArray(); arr_y.SetName("Y")
        table.AddColumn(arr_x); table.AddColumn(arr_y)
        table.SetNumberOfRows(0)

        plot = ch.AddPlot(vtkChart.POINTS)

        self._bind_plot_to_table_axes(plot, table)
        self._log(f"[PLOT] bind axes ok -> X{self._saved_ranges['x']} Y{self._saved_ranges['y']}")

        if vtkPlotPoints is not None:
            pts = vtkPlotPoints.SafeDownCast(plot)
            if pts:
                pts.SetMarkerStyle(vtkPlotPoints.CIRCLE)
                pts.SetMarkerSize(6)
        try:
            plot.GetBrush().SetColor(color_rgb[0], color_rgb[1], color_rgb[2], 255)
        except Exception:
            pass
        pen = plot.GetPen()
        pen.SetLineType(vtkPen.SOLID_LINE); pen.SetWidth(2.0)
        try:
            pen.SetColor(color_rgb[0], color_rgb[1], color_rgb[2], 255)
        except TypeError:
            pen.SetColor(*color_rgb)

        try: plot.SetVisible(False)
        except Exception: pass

        try:
            if ch.GetScene():
                ch.GetScene().SetDirty(True)
        except Exception:
            pass

        self._restore_axes_ranges()
        return plot, table

    def _dump_overlay_table(self, table, tag="[PLOT] dump"):
        try:
            n = table.GetNumberOfRows()
            self._log(f"{tag}: rows={n}")
            for r in range(n):
                x = table.GetValue(r, 0).ToDouble()
                y = table.GetValue(r, 1).ToDouble()
                self._log(f"   row {r}: X={x:.9f}, Y={y:.9f}")
        except Exception:
            pass

    def _finalize_current_measurement(self):
        if not self._current:
            return
        if not (self._current.get('p1') and self._current.get('p2')):
            self._cancel_current_overlay()
            return

        # Verificación antes del cálculo
        self._verify_overlay_consistency()

        x1, y1 = self._current['p1']; x2, y2 = self._current['p2']
        result = two_point_metrics((x1, y1), (x2, y2), kind=self._current['type'])

        # Persistir en DataStore (si está disponible)  ---------- NUEVO ----------
        meas_id = self._save_measurement_to_store(result, (x1, y1), (x2, y2))

        # Guardar overlay en memoria local (para remover/limpiar)
        self._measurements.append(self._current)
        self._current = None

        self._log(f"[MEAS] ({result['type']}) dx={result['dx']:.6f} "
                  f"dy={result['dy']:.6f} slope={result['slope']:.6f} "
                  f"dist={result['dist']:.6f}")

        # Mensaje informativo al usuario  ------------------------ NUEVO ----------
        try:
            msg = (f"Result '{result['type']}' saved (ID: {meas_id}).\n"
                   f"Slope = {result['slope']:.6f}\n\n"
                   f"For more information go to 'Measure / Slope'.")
            QMessageBox.information(self.parent, "Slope saved", msg)
        except Exception:
            pass

        if callable(self._on_measure_result):
            self._on_measure_result(result)

        self._restore_axes_ranges()

    # ---------- Persistencia en DataStore (NUEVO) ----------
    def _save_measurement_to_store(self, result: dict, p1, p2):
        """
        Guarda la medición en DataStore['measurements'] como lista de dicts:
         {id, type, p1, p2, dx, dy, slope, dist, timestamp}
        Genera un id incremental por tipo: 'slope-001', etc.
        Devuelve el id usado (string).
        """
        t = result.get("type", "measure")
        if self._datastore is None:
            self._log("[STORE] DataStore no inyectado; no se persiste.")
            # Fallback: id local con contador por longitud
            seq = sum(1 for m in self._measurements if m.get('type') == t) + 1
            return f"{t}-{seq:03d}"

        try:
            lst = self._datastore.get("measurements", None)
            if not isinstance(lst, list):
                lst = []
        except Exception:
            lst = []

        # Calcular siguiente consecutivo por tipo
        seq = 0
        prefix = f"{t}-"
        for it in lst:
            if isinstance(it, dict) and it.get("type") == t:
                mid = str(it.get("id", ""))
                if mid.startswith(prefix):
                    try:
                        n = int(mid[len(prefix):])
                        seq = max(seq, n)
                    except Exception:
                        pass
        seq += 1
        meas_id = f"{t}-{seq:03d}"

        record = {
            "id": meas_id,
            "type": t,
            "p1": (float(p1[0]), float(p1[1])),
            "p2": (float(p2[0]), float(p2[1])),
            "dx": float(result.get("dx", float(p2[0]) - float(p1[0]))),
            "dy": float(result.get("dy", float(p2[1]) - float(p1[1]))),
            "slope": float(result.get("slope", 0.0)),
            "dist": float(result.get("dist", 0.0)),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        lst.append(record)

        try:
            self._datastore.set("measurements", lst)
            self._log(f"[STORE] Guardado {meas_id} en DataStore['measurements'] (total={len(lst)})")
        except Exception as e:
            self._log(f"[STORE] Error guardando medición: {e}")

        return meas_id

    # === LECTURA DEL OVERLAY =====================================================
    def _read_overlay_points(self):
        if not self._current or not self._current.get('table'):
            return []
        table = self._current['table']
        pts = []
        try:
            n = table.GetNumberOfRows()
            for r in range(n):
                x = table.GetValue(r, 0).ToDouble()
                y = table.GetValue(r, 1).ToDouble()
                pts.append((x, y))
        except Exception:
            pass
        return pts

    def _dump_overlay_points(self, tag="[VERIFY] overlay"):
        pts = self._read_overlay_points()
        self._log(f"{tag}: rows={len(pts)}")
        for i, (x, y) in enumerate(pts):
            sp = self._plot_to_screen(x, y)
            self._log(f"   row {i}: X={x:.9f}, Y={y:.9f} → screen={sp}")
        return pts

    def _verify_overlay_consistency(self, expected_points=None, tol=1e-7):
        if expected_points is None:
            if not self._current:
                expected_points = []
            else:
                p1 = self._current.get('p1')
                p2 = self._current.get('p2')
                expected_points = [p for p in (p1, p2) if p is not None]

        pts = self._read_overlay_points()
        self._log(f"[VERIFY] after draw: rows={len(pts)}")
        for i, (x, y) in enumerate(pts):
            sp = self._plot_to_screen(x, y)
            self._log(f"   row {i}: X={x:.9f}, Y={y:.9f} → screen={sp}")

        if len(pts) != len(expected_points):
            self._log(f"[VERIFY] MISMATCH len: tabla={len(pts)} esperado={len(expected_points)}")
            return False

        ok = True
        for i, (xa, ya) in enumerate(pts):
            xb, yb = expected_points[i]
            dx = abs(xa - xb); dy = abs(ya - yb)
            self._log(f"[VERIFY] idx={i} table=({xa:.9f},{ya:.9f}) "
                      f"expected=({xb:.9f},{yb:.9f}) Δ=({dx:.3e},{dy:.3e})")
            if dx > tol or dy > tol:
                ok = False

        self._log("[VERIFY] overlay OK" if ok else "[VERIFY] overlay MISMATCH")
        return ok
		
	
    def _suspend_left_actions(self, suspend: bool):
        ch = self._active_chart()
        if not ch: return
        maybe = []
        for name in ("PAN", "ZOOM", "SELECT", "ZOOM_RECT", "ZOOM_BOX"):
            if hasattr(vtkChart, name):
                maybe.append(getattr(vtkChart, name))
        if suspend:
            self._saved_actions = {}
            for act in maybe:
                try:
                    btn = ch.GetActionToButton(act)
                    self._saved_actions[act] = btn
                    if btn == 1:  # LEFT
                        ch.SetActionToButton(act, -1)
                except Exception:
                    pass
        else:
            for act, btn in self._saved_actions.items():
                try:
                    ch.SetActionToButton(act, btn)
                except Exception:
                    pass
            self._saved_actions = {}
            
    def _show_point_tooltip(self, point, label="P"):
        """
        Muestra un tooltip junto al cursor con la coordenada seleccionada.
        """
        try:
            x, y = point
            QToolTip.showText(
                QCursor.pos(),
                f"{label} = ({x:.6f}, {y:.6f})",
                self.vtk_widget,
                self.vtk_widget.rect(),
                2000,  # ms
            )
        except Exception:
            pass
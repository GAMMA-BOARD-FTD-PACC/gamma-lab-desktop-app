# ui/vtk_context_menu.py
from PyQt5.QtWidgets import QMenu, QApplication
from PyQt5.QtCore import Qt
from vtk import vtkChartXY, vtkChart

import os

# Servicios externos
from core.services.export_service import ExportService
from core.services.measurement_service import MeasurementService


class VTKContextMenu:
    """
    Menú contextual general para vistas basadas en VTK.
    - Zoom y atajos (Ctrl/Shift + rueda)
    - Acciones personalizadas registrables
    - Delegación en servicios: ExportService y MeasurementService
    """
    last_export_dir = os.getcwd()

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

        # DataStore (inyectable por set_datastore)
        self._datastore = None

        # DEBUG
        self._debug = True

        # --- wiring de zoom/ratón ---
        self._install_wheel_shortcuts()
        self._install_mouse_observers()

        # Asegurar zoom con rueda en todos los charts
        for ch in self._get_charts():
            if ch:
                ch.SetZoomWithMouseWheel(True)
                ch.SetAxisZoom(0, True)
                ch.SetAxisZoom(1, True)

        # Menú contextual
        self.vtk_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vtk_widget.customContextMenuRequested.connect(self.show_menu)

        # --- Servicios ---

        # Helpers para nombres y last_dir (se leen siempre "al vuelo")
        def _get_names():
            return (self.signal_name or "signal",
                    self.chanel_name or None,
                    self.plugin_name or "plugin")

        def _get_last_dir():
            return VTKContextMenu.last_export_dir or os.getcwd()

        def _set_last_dir(path):
            VTKContextMenu.last_export_dir = path

        # Servicio de exportación
        self.export_service = ExportService(
            parent=self.parent,
            vtk_widget=self.vtk_widget,
            get_active_chart=self._active_chart,
            get_names=_get_names,
            last_dir_getter=_get_last_dir,
            last_dir_setter=_set_last_dir
        )

        # Adaptadores de datastore (leen el self._datastore actual)
        def _ds_get(k, default=None):
            try:
                return self._datastore.get(k, default) if self._datastore else default
            except Exception:
                return default

        def _ds_set(k, v):
            try:
                if self._datastore:
                    self._datastore.set(k, v)
            except Exception:
                pass

        # Servicio de mediciones (usa SIEMPRE el chart activo)
        self.measure_service = MeasurementService(
            parent=self.parent,
            vtk_widget=self.vtk_widget,
            get_active_chart=self._active_chart,
            datastore_get=_ds_get,
            datastore_set=_ds_set,
            pick_radius_px=self._PICK_RADIUS_PX,
            debug=self._debug
        )

    # ---------- utils ----------
    def _log(self, *args):
        if self._debug:
            print(*args)

    def _get_charts(self):
        if isinstance(self.chart, list):
            return [ch for ch in self.chart if ch is not None]
        return [self.chart] if self.chart is not None else []

    def _active_chart(self):
        return (self.chart[0] if isinstance(self.chart, list) and self.chart else self.chart)

    # ---------- setters públicos ----------
    def set_signal_name(self, name):
        self.signal_name = name

    def set_channel_name(self, name):
        self.chanel_name = name

    def set_plugin_name(self, name):
        self.plugin_name = name

    def set_chart(self, chart):
        self.chart = chart
        # avisar al servicio que cambió el chart (invalida rangos, refs, etc.)
        if hasattr(self, "measure_service") and self.measure_service:
            if hasattr(self.measure_service, "on_chart_changed"):
                self.measure_service.on_chart_changed()

    def set_datastore(self, store):
        """Inyecta el servicio DataStore (dict-like con get/set)."""
        self._datastore = store

    # ---------- rueda ----------
    def _install_wheel_shortcuts(self):
        old_wheel_event = self.vtk_widget.wheelEvent

        def custom_wheel_event(event):
            modifiers = QApplication.keyboardModifiers()
            for ch in self._get_charts():
                if not ch:
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

            # ejecutar comportamiento original
            old_wheel_event(event)

        self.vtk_widget.wheelEvent = custom_wheel_event

    # ---------- menú ----------
    def add_action(self, text, callback):
        self.custom_actions.append((text, callback))

    def show_menu(self, pos):
        menu = QMenu()

        # Zoom
        zoom_menu = menu.addMenu("Zoom")
        zoom_menu.addAction("Horizontal (X)", lambda: self.set_zoom_mode("x"))
        zoom_menu.addAction("Vertical (Y)", lambda: self.set_zoom_mode("y"))
        zoom_menu.addAction("Ambos ejes (X+Y)", lambda: self.set_zoom_mode("xy"))
        zoom_menu.addAction("Restablecer vista", self.reset_zoom)

        # Medidas (delegado a servicio)
        measure_menu = menu.addMenu("Medidas")
        act_start = measure_menu.addAction("Pendiente (2 puntos – clic IZQ.)",lambda: self.measure_service.start('slope'))
        act_start.setEnabled(self.measure_service.state == 'idle')

        act_cancel = measure_menu.addAction("Cancelar medición (Esc)", self.measure_service.cancel)
        act_cancel.setEnabled(self.measure_service.state != 'idle')
        measure_menu.addSeparator()
        
        measure_menu.addAction("Mostrar/Ocultar todas las líneas", self.measure_service.toggle_overlay)
        measure_menu.addAction("Eliminar última medición", self.measure_service.remove_last_measurement)
        measure_menu.addAction("Eliminar TODAS las mediciones", self.measure_service.clear_all_measurements)

        # Exportar (delegado a servicio)
        menu.addSeparator()
        export_img_menu = menu.addMenu("Export as image")
        export_img_menu.addAction("png",  lambda: self.export_service.export_image("png"))
        export_img_menu.addAction("jpg",  lambda: self.export_service.export_image("jpg"))
        export_img_menu.addAction("jpegpg", lambda: self.export_service.export_image("jpeg"))
        export_img_menu.addAction("bmp",  lambda: self.export_service.export_image("bmp"))
        export_img_menu.addAction("tiff", lambda: self.export_service.export_image("tiff"))

        export_table_menu = menu.addMenu("Exportar tabla")
        export_table_menu.addAction("csv",  lambda: self.export_service.export_table("csv"))
        export_table_menu.addAction("json", lambda: self.export_service.export_table("json"))
        export_table_menu.addAction("xlsx", lambda: self.export_service.export_table("xlsx"))
        export_table_menu.addAction("Exportar tabla")  # (si quieres, elimínala; era redundante)

        # Acciones personalizadas
        if self.custom_actions:
            menu.addSeparator()
            for text, cb in self.custom_actions:
                menu.addAction(text, cb)

        menu.exec_(self.vtk_widget.mapToGlobal(pos))

    # ---------- export  ----------
    def export_image(self, fmt: str, filename: str = None):
        self.export_service.export_image(fmt, filename)

    def export_table(self, fmt: str, filename: str = None):
        self.export_service.export_table(fmt, filename)

    # ---------- zoom ----------
    def set_zoom_mode(self, mode):
        for ch in self._get_charts():
            if not ch:
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
        for ch in self._get_charts():
            try:
                ch.RecalculateBounds()
            except AttributeError:
                # algunas versiones de VTK no lo soportan
                pass

    # ---------- eventos mouse----------
    def _install_mouse_observers(self):
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        iren.AddObserver("LeftButtonPressEvent", self._on_left_press, 1.0)
        iren.AddObserver("LeftButtonReleaseEvent", self._on_left_release, 1.0)
        iren.AddObserver("MouseMoveEvent", self._on_mouse_move_block_hover, 1.0)

    def _on_left_press(self, obj, evt):
        # Pasar coordenadas al servicio
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        sx, sy = iren.GetEventPosition()
        self.measure_service.on_left_press(sx, sy)

    def _on_left_release(self, obj, evt):
        # Si el servicio está idle, no hace nada
        if self.measure_service.state == 'idle':
            return
        iren = self.vtk_widget.GetRenderWindow().GetInteractor()
        sx, sy = iren.GetEventPosition()
        self.measure_service.on_left_release(sx, sy, click_eps=self._CLICK_EPS)

    def _on_mouse_move_block_hover(self, obj, evt):
        if self.measure_service.state == 'idle':
            return
        return 1 

    def set_measurement_context(self, *, view_id: str, trial_id: int, channel_name: str):
        if hasattr(self, "measure_service") and self.measure_service:
            self.measure_service.set_context(view_id=view_id, trial_id=trial_id, channel_name=channel_name)

    def rebuild_measurement_overlays(self):
        if hasattr(self, "measure_service") and self.measure_service:
            self.measure_service.rebuild_overlays_for_current_context()

    def clear_measurement_overlays(self):
        if hasattr(self, "measure_service") and self.measure_service:
            self.measure_service.clear_visual_overlays()

    def on_view_rebuilt(self, chart, *, view_id: str, trial_id: int, channel_name: str):
        """
        Llamar SIEMPRE desde el plugin después de reconstruir la gráfica y hacer Render().
        """
        # 1) Asociar el nuevo chart (esto invalida caches en MeasurementService)
        self.set_chart(chart)

        # 2) Forzar un render y recalcular bounds para que los ejes del chart estén actualizados
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass
        try:
            if chart and hasattr(chart, "RecalculateBounds"):
                chart.RecalculateBounds()
        except Exception:
            pass

        # 3) Contexto + reconstrucción de overlays del contexto actual
        try:
            self.set_measurement_context(view_id=view_id, trial_id=trial_id, channel_name=channel_name)
            self.rebuild_measurement_overlays()
        except Exception:
            pass

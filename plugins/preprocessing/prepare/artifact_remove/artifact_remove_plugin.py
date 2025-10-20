# plugins/preprocessing/prepare/artifact_remove/artifact_remove_plugin.py
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QWidget, QMessageBox, QVBoxLayout
import numpy as np
import vtk
from typing import Optional, List, Set
from pathlib import Path
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

from plugins.preprocessing.prepare.artifact_remove.artifact_remove_ui import Ui_ArtifactRemove
from plugins.preprocessing.prepare.artifact_remove.artifact_logic import apply_artifact_modification

# --- Intento de importación de clases personalizadas ---
try:
    # Estas clases mejoran la experiencia de usuario si están disponibles
    from core.plugins.vtk_context_menu import VTKInteractorStyleZoomAxis, VTXContextMenu
except ImportError:
    # Si no se encuentran, usamos las clases por defecto de VTK.
    # El código seguirá funcionando, pero con la interacción estándar.
    VTKInteractorStyleZoomAxis = vtk.vtkContextInteractorStyle 
    VTXContextMenu = None

LOGP = "[ArtifactRemovePlugin]"
LOGP_WIDGET = "[ArtifactRemoveWidget]"

# --- Widget Personalizado para Recarga Automática ---
class ArtifactRemoveWidget(QWidget):
    """
    Un QWidget personalizado que sabe cómo recargar su contenido
    cada vez que se muestra, solucionando el problema de la pantalla en blanco.
    """
    def __init__(self, plugin: "ArtifactRemovePlugin", parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.first_show = True

    def showEvent(self, event):
        """Se dispara CADA VEZ que el widget se hace visible."""
        print(f"{LOGP_WIDGET} showEvent() triggered.")
        
        if self.first_show:
            self.first_show = False
            print(f"{LOGP_WIDGET} Primera muestra. No se recarga.")
        else:
            # En las siguientes veces que se muestra, reconstruye el VTK y recarga los datos
            print(f"{LOGP_WIDGET} Muestra subsecuente: Recargando VTK y datos.")
            self.plugin._ensure_vtk()
            self.plugin._load_and_display_trials()
            if self.plugin.vtk_interactor:
                self.plugin.vtk_interactor.Enable()

        super().showEvent(event)

# --- Clase Principal del Plugin ---
class ArtifactRemovePlugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        self.meta = meta
        print(f"{LOGP} __init__")
        self.kernel, self.mainwin, self.widget, self.ui = None, None, None, None
        
        # Atributos de VTK
        self.vtk_interactor: Optional[QVTKRenderWindowInteractor] = None
        self.vtk_view: Optional[vtk.vtkContextView] = None
        self.chart: Optional[vtk.vtkChartXY] = None
        self.vtk_menu: Optional[VTXContextMenu] = None
        
        # Atributos de Estado
        self.current_display_index: int = -1 
        self.valid_indices: List[int] = [] 
        self.total_original_trials: int = 0
        self.discarded_indices: Set[int] = set()
        self.modified_indices: Set[int] = set()

    def initialize(self, kernel): pass
    def process(self, data): pass

    def start(self, kernel):
        print(f"{LOGP} start()")
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        try: 
            self.kernel.event.connect(self._on_data_updated)
            print(f"{LOGP} Conectado a eventos.")
        except Exception as e: 
            print(f"{LOGP} Error al conectar a eventos: {e}")
        
    def stop(self):
        print(f"{LOGP} stop() - Limpiando VTK, pero conservando UI.")
        if self.vtk_view and self.vtk_view.GetInteractor():
            try:
                self.vtk_view.GetInteractor().RemoveObservers(vtk.vtkCommand.MouseMoveEvent)
            except Exception: pass
        
        if self.vtk_view:
            self.vtk_view.GetScene().ClearItems()
            
        if self.vtk_interactor:
            self.vtk_interactor.Disable()
            self.vtk_interactor.deleteLater()
        
        # Limpiar referencias para forzar la recreación
        self.vtk_interactor = None
        self.vtk_view = None
        self.chart = None
        self.vtk_menu = None

    def get_widget(self, parent=None):
        if self.widget is None:
            print(f"{LOGP} get_widget(): Creando UI por primera vez...")
            self.widget = ArtifactRemoveWidget(self, parent)
            self.ui = Ui_ArtifactRemove()
            self.ui.setupUi(self.widget)
            self._ensure_vtk()
            self._wire_controls()
            
            print(f"{LOGP} get_widget(): Cargando datos (primera vez)...")
            self._load_and_display_trials()
            
        self.widget.setParent(parent)
        
        if self.vtk_interactor:
            self.vtk_interactor.Enable()
            
        return self.widget

    # --- Lógica de la Interfaz de Usuario ---

    def _wire_controls(self):
        panel = self.ui.artifact_panel
        panel.apply_button.clicked.connect(self._on_apply_changes)
        panel.prev_button.clicked.connect(self._go_to_previous_trial)
        panel.next_button.clicked.connect(self._go_to_next_trial)
        
    def _on_apply_changes(self):
        panel = self.ui.artifact_panel
        mode_text = panel.mode_combo.currentText()
        mode = 'cut' if mode_text == "Cut From Start" else 'interpolate'

        if self.current_display_index == -1:
            QMessageBox.warning(self.widget, "Acción no Válida",
                                "Esta acción solo se puede aplicar a un trial individual. "
                                "Por favor, seleccione un trial usando los botones 'Next' o 'Previous'.")
            return

        target_original_index = None
        if 0 <= self.current_display_index < len(self.valid_indices):
            target_original_index = self.valid_indices[self.current_display_index]
        else:
            QMessageBox.warning(self.widget, "Error", "Índice de trial inválido.")
            return

        try:
            point_a = float(panel.point_a.text())
            point_b = float(panel.point_b.text()) if panel.point_b.isVisible() else 0.0
            
            modified_td = apply_artifact_modification(
                kernel=self.kernel, mode=mode, point_a=point_a, point_b=point_b,
                target_original_index=target_original_index
            )
            
            if modified_td:
                message = f"Cambios aplicados exitosamente al trial {target_original_index + 1}."
                self.modified_indices.add(target_original_index)
                self._load_and_display_trials()
                QMessageBox.information(self.widget, "Éxito", message)

        except Exception as e:
            QMessageBox.critical(self.widget, "Error de Aplicación", f"Ocurrió un error: {e}")

    # --- Lógica de Navegación y Carga de Datos ---
    
    def _go_to_previous_trial(self):
        num_valid = len(self.valid_indices)
        if num_valid == 0: return
        
        if self.current_display_index == 0: self.current_display_index = -1
        elif self.current_display_index == -1: self.current_display_index = num_valid - 1
        else: self.current_display_index -= 1
        
        self._load_and_display_trials()

    def _go_to_next_trial(self):
        num_valid = len(self.valid_indices)
        if num_valid == 0: return

        if self.current_display_index == num_valid - 1: self.current_display_index = -1
        elif self.current_display_index == -1: self.current_display_index = 0
        else: self.current_display_index += 1
            
        self._load_and_display_trials()

    def _load_and_display_trials(self):
        # ... (código de carga de datos, sin cambios)
        if not self.kernel: return
        store = self.kernel.get_service("DataStore")
        if not store: return self._clear_render("Error: DataStore no disponible.")
        
        active_signal = store.get_active_signal()
        if not isinstance(active_signal, SignalDataset):
            return self._clear_render("No hay señal activa cargada.")

        original_td = None
        if active_signal.trials_dataset:
            original_td = active_signal.trials_dataset[-1]
            key = (Path(original_td.source).name, original_td.channel_name)
            self.discarded_indices = active_signal.discarded_trials.get(key, set())
            self.modified_indices = original_td.metadata.get("modified_trials", set())
            self.total_original_trials = original_td.trials.shape[1]
            self.valid_indices = [i for i in range(self.total_original_trials) if i not in self.discarded_indices]
        else:
            return self._clear_render("Fallo: No se encontraron datos de trials originales.")

        td = self._find_active_trials_dataset()
        num_valid = td.trials.shape[1] if td else 0
        
        if not (-1 <= self.current_display_index < num_valid):
            self.current_display_index = 0 if num_valid > 0 else -1

        status_text, display_data, title = "", None, ""
        if self.current_display_index == -1:
            if num_valid == 0: return self._clear_render("Todos los trials están descartados.")
            display_data = np.nanmean(td.trials, axis=1)
            title = f"Promedio de {num_valid} Válidos - {td.channel_name}"
            status_text = f"Viendo Promedio / {num_valid} Válidos ({self.total_original_trials} Orig.)"
        else:
            original_index = self.valid_indices[self.current_display_index]
            display_data = original_td.trials[:, original_index]
            status_suffix = " (modificado)" if original_index in self.modified_indices else ""
            title = f"Trial Original {original_index + 1} - {td.channel_name}"
            status_text = f"Viendo Trial {original_index + 1}{status_suffix} / {self.total_original_trials} Originales"
            
        if self.ui: self.ui.artifact_panel.trial_status_label.setText(status_text)
        self._plot_curve(original_td.time_rel, display_data, title)

    # --- Lógica de Visualización VTK (CORREGIDA Y FINAL) ---

    def _ensure_vtk(self):
        """
        Prepara el entorno de VTK.
        Esta es la versión definitiva que respeta la configuración por defecto
        de vtkContextView para asegurar la interactividad completa.
        """
        if self.vtk_view is not None and self.vtk_interactor is not None:
            return

        print(f"{LOGP} _ensure_vtk(): Configurando VTK por primera vez...")
        container = self.ui.plotArea

        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
        
        self.vtk_interactor = QVTKRenderWindowInteractor(container)
        layout.addWidget(self.vtk_interactor)
        
        self.vtk_view = vtk.vtkContextView()
        self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
        self.vtk_view.GetRenderer().SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke")) 
        
        # --- LA CLAVE DE LA SOLUCIÓN ---
        # No establecemos un estilo manualmente. Dejamos que vtkContextView use el suyo.
        # Simplemente obtenemos su interactor y le añadimos nuestro observador de coordenadas.
        # El estilo por defecto ya incluye zoom (clic derecho) y paneo (botón central).
        interactor = self.vtk_view.GetInteractor()
        interactor.AddObserver(vtk.vtkCommand.MouseMoveEvent, self._on_mouse_move)
        
        print(f"{LOGP} Observador 'MouseMoveEvent' añadido al interactor por defecto de la vista.")

        # Inicializamos el widget de Qt, que se encargará de gestionar el bucle de eventos.
        self.vtk_interactor.Initialize()
        
        print(f"{LOGP} VTK configurado e inicializado correctamente.")
        
    def _on_mouse_move(self, interactor, event):
        if not self.chart or not self.mainwin or not self.vtk_view: return
        pos = interactor.GetEventPosition()
        coords = vtk.vtkVector2f()
        try:
            transform = self.chart.GetPlotTransform()
            if transform:
                 transform.GetInverse().TransformPoint(pos, coords)
                 message = f"Tiempo: {coords[0]:.4f} s, Amplitud: {coords[1]:.6f}"
                 self.mainwin.statusBar().showMessage(message)
        except Exception: pass
        
    def _plot_curve(self, t, y, title=""):
        # ... (código de ploteo, sin cambios)
        if not self.vtk_view: self._ensure_vtk()
        
        scene = self.vtk_view.GetScene()
        scene.ClearItems() 
        self.vtk_view.GetRenderer().SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))

        table = vtk.vtkTable()
        arr_t = vtk.vtkFloatArray()
        arr_t.SetName("Time (s)")
        arr_y = vtk.vtkFloatArray()
        arr_y.SetName("Amplitude")
        table.AddColumn(arr_t)
        table.AddColumn(arr_y)
        
        valid_indices = ~np.isnan(y)
        t_valid, y_valid = t[valid_indices], y[valid_indices]
        
        n_points = len(t_valid)
        table.SetNumberOfRows(n_points)
        for i in range(n_points):
            table.SetValue(i, 0, t_valid[i])
            table.SetValue(i, 1, y_valid[i])
        
        self.chart = vtk.vtkChartXY()
        scene.AddItem(self.chart) 

        plot = self.chart.AddPlot(vtk.vtkChart.LINE)
        plot.SetInputData(table, 0, 1)
        plot.SetWidth(1.5)
        plot.GetPen().SetColor(vtk.vtkNamedColors().GetColor4ub("SteelBlue"))
        self.chart.SetTitle(title)
        self.chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle("Tiempo (s)")
        self.chart.GetAxis(vtk.vtkAxis.LEFT).SetTitle("Amplitud")
        
        if VTXContextMenu and self.vtk_interactor:
             try:
                 self.vtk_menu = VTXContextMenu(self.chart, self.vtk_interactor, parent=self.widget)
                 self.vtk_menu.add_action("Reset Zoom", lambda: self.chart.RecalculateBounds())
             except Exception: pass
                 
        self.vtk_view.GetRenderWindow().Render()

    # --- Funciones de utilidad ---
    def _reset_state(self):
        # ... (código de reseteo, sin cambios)
        self.current_display_index = -1
        self.valid_indices = []
        self.total_original_trials = 0
        self.discarded_indices = set()
        self.modified_indices = set()
        
    def _find_active_trials_dataset(self) -> Optional[TrialDataset]:
        # ... (código de búsqueda, sin cambios)
        if not self.kernel: return None
        store = self.kernel.get_service("DataStore")
        if not store: return None
        active_signal = store.get_active_signal()
        if not isinstance(active_signal, SignalDataset): return None
        active_signal_key = store.get_active_signal_key()
        if not active_signal_key or not active_signal.channel_names: return None
        channel_name = active_signal.channel_names[0]
        try: 
            td = active_signal.get_active_trials(file_name=active_signal_key, channel_name=channel_name)
            return td if isinstance(td, TrialDataset) else None
        except Exception: 
            return None
            
    def _clear_render(self, message=""):
        # ... (código de limpieza, sin cambios)
        if not self.vtk_view: self._ensure_vtk()
        scene = self.vtk_view.GetScene()
        scene.ClearItems()
        self.vtk_view.GetRenderer().SetBackground(0.1, 0.1, 0.2)
        if message:
            text_actor = vtk.vtkTextActor()
            text_actor.SetInput(message)
            prop = text_actor.GetTextProperty()
            prop.SetColor(1.0, 1.0, 1.0)
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToCentered()
            prop.SetFontSize(16)
            self.vtk_view.GetRenderer().AddActor2D(text_actor)
        self.vtk_view.GetRenderWindow().Render()
        
    def _on_data_updated(self, topic: str, payload: object):
        # ... (código de actualización, sin cambios)
        if topic in ["signal_added", "trials_generated", "trial_discard_updated"]:
            if self.widget and self.widget.isVisible():
                print(f"{LOGP} Evento '{topic}' recibido. Reseteando y actualizando...")
                self._reset_state()
                if self.vtk_interactor: self.vtk_interactor.Enable() 
                self._load_and_display_trials()

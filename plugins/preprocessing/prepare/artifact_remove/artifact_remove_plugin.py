# Ubicación: plugins/preprocessing/prepare/artifact_remove/artifact_remove_plugin.py
# VERSIÓN REFACTORIZADA Y COMPLETA (Restaurada)

from vtk.util import numpy_support as nps # <--- 1. IMPORTACIÓN SEGURA AÑADIDA
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QWidget, QMessageBox, QVBoxLayout, QLabel
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
# Importar la función de lógica correcta
from plugins.preprocessing.prepare.artifact_remove.artifact_logic import apply_modification_to_all_valid

# Intento de importación de clases personalizadas
try:
    # Asumiendo que esta clase existe para un mejor zoom 2D
    from core.plugins.vtk_context_menu import VTKInteractorStyleZoomAxis
except ImportError:
    # Fallback si no existe, para evitar un error de importación
    VTKInteractorStyleZoomAxis = None 

try:
    from core.plugins.vtk_context_menu import VTKContextMenu
except ImportError:
    VTKContextMenu = None

LOGP = "[ArtifactRemovePlugin]"
# --- Worker para ejecutar la lógica pesada en otro hilo ---
class _ApplyWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int)      # opcional
    # CAMBIO CRÍTICO: Usar un tipo más específico (TrialDataset) o None en la señal.
    # Como el valor es un TrialDataset o None, usamos object, pero lo forzamos abajo.
    finished = QtCore.pyqtSignal(object)   
    error = QtCore.pyqtSignal(str)

    def __init__(self, kernel, mode, point_a, point_b):
        super().__init__()
        self.kernel = kernel
        self.mode = mode
        self.point_a = point_a
        self.point_b = point_b

    @QtCore.pyqtSlot()
    def run(self):
        try:
            # Import dentro del hilo para evitar dependencias cruzadas al importar el plugin
            from plugins.preprocessing.prepare.artifact_remove.artifact_logic import apply_modification_to_all_valid
            td = apply_modification_to_all_valid(
                kernel=self.kernel,
                mode=self.mode,
                point_a=self.point_a,
                point_b=self.point_b
            )
            self.finished.emit(td)
        except Exception as e:
            self.error.emit(f"{type(e).__name__}: {e}")

# Clase Principal del Plugin
class ArtifactRemovePlugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.meta = meta
        print(f"{LOGP} __init__")
        self.kernel, self.mainwin = None, None
        self.widget: Optional[QWidget] = None
        self.ui: Optional[Ui_ArtifactRemove] = None
        self.vtk_interactor: Optional[QVTKRenderWindowInteractor] = None
        self.vtk_view: Optional[vtk.vtkContextView] = None
        self.chart: Optional[vtk.vtkChartXY] = None
        self.vtk_menu: Optional[VTKContextMenu] = None

        # Hilo para aplicar cambios sin bloquear la UI
        self._apply_thread = None
        self._apply_worker = None

        # Timer para coalescer/refrescar (debounce) tras eventos del kernel
        self._refresh_timer = QtCore.QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)  # ms
        self._refresh_timer.timeout.connect(self._refresh_view_coalesced)

        
        # Estado
        self.current_display_index: int = -1 # -1 = Promedio
        self.valid_indices: List[int] = []
        self.total_original_trials: int = 0
        self.discarded_indices: Set[int] = set()
        self.modified_indices: Set[int] = set()

    def initialize(self, kernel): 
        pass

    def process(self, data): 
        pass

    def _refresh_view_coalesced(self):
        """Refresca la vista una sola vez aunque lleguen varios eventos seguidos."""
        try:
            self._reset_state()
            if self.vtk_interactor and not self.vtk_interactor.isEnabled():
                try:
                    self.vtk_interactor.Enable()
                except Exception:
                    pass
            self._load_and_display_trials()
            QtCore.QTimer.singleShot(50, self._force_render)
        except Exception as e:
            print(f"{LOGP} _refresh_view_coalesced error: {e}")


    def start(self, kernel):
        """ Se llama cuando el plugin se carga inicialmente. """
        print(f"{LOGP} start()")
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        try:
            self.kernel.event.connect(self._on_data_updated)
            print(f"{LOGP} Connected to kernel events.")
        except Exception as e:
            print(f"{LOGP} Error connecting to events: {e}")

    def stop(self):
        """ Se llama cuando el plugin se cierra o deshabilita. """
        print(f"{LOGP} stop() - Disabling VTK interactor.")
        if self.vtk_interactor and self.vtk_interactor.isEnabled():
            try:
                self.vtk_interactor.Disable()
            except Exception as e: 
                print(f"{LOGP} Error disabling interactor: {e}")

    def get_widget(self, parent=None):
        """
        Entrega el widget principal del plugin a la ventana principal.
        Maneja la creación inicial y la reutilización.
        """
        
        # --- CREACIÓN INICIAL ---
        if self.widget is None:
            print(f"{LOGP} get_widget(): Creating UI for the first time...")
            
            self.widget = QWidget(parent)
            
            try:
                self.ui = Ui_ArtifactRemove()
                self.ui.setupUi(self.widget)
                self._wire_controls()

                if self.kernel is None:
                    if hasattr(parent, 'kernel'): 
                        self.kernel = parent.kernel
                    if self.kernel:
                        print(f"{LOGP} Kernel obtained in get_widget.")
                        self.mainwin = self.kernel.get_service("MainWindow")
                        try: 
                            self.kernel.event.connect(self._on_data_updated)
                            print(f"{LOGP} Connected events in get_widget.")
                        except Exception as e: 
                            print(f"{LOGP} Error connecting events: {e}")
                    else: 
                        raise RuntimeError("Kernel not available.")

                # No llamamos a _ensure_vtk() aquí.
                # Se llamará la primera vez desde _plot_curve

                print(f"{LOGP} get_widget(): Loading initial data...")
                self._load_and_display_trials()
                if self.ui and self.ui.artifact_panel:
                    self._on_mode_changed(self.ui.artifact_panel.mode_combo.currentText())

            except Exception as e: 
                error_message = f"Failed to initialize Remove Artifact plugin:\n{type(e).__name__}: {e}"
                print(f"{LOGP} CRITICAL ERROR during initial setup: {e}")
                QMessageBox.critical(self.widget, "Plugin Initialization Error", error_message)
                self._cleanup_vtk_references()
                self.widget.deleteLater() 
                self.widget = None
                self.ui = None
                return None 

        # --- REUTILIZACIÓN DEL WIDGET ---
        else:
            print(f"{LOGP} get_widget(): Reusing existing UI.")
            self.widget.setParent(parent)
            
            try:
                if self.vtk_interactor and not self.vtk_interactor.isEnabled():
                    self.vtk_interactor.Enable()
                
                print(f"{LOGP} get_widget(): Reloading data...")
                self._load_and_display_trials()
                QtCore.QTimer.singleShot(50, self._force_render) 
                
            except Exception as e:
                print(f"{LOGP} Error re-ensuring VTK or reloading data: {e}")
                self._clear_render(f"Error reloading view:\n{e}")

        return self.widget

    def _force_render(self):
        """ Intenta forzar un renderizado si el widget está visible. """
        if self.vtk_interactor and self.vtk_view and self.widget and self.widget.isVisible():
            try: 
                print(f"{LOGP} DEBUG: Forcing Render.")
                self.vtk_view.GetRenderWindow().Render()
                print(f"{LOGP} DEBUG: Render successful.")
            except Exception as e: 
                print(f"{LOGP} Error during forced render: {e}")

    def _wire_controls(self):
        """ Conecta señales de la UI a slots. """
        if not self.ui or not hasattr(self.ui, 'artifact_panel'):
            print(f"{LOGP} Error: UI o artifact_panel no inicializado en _wire_controls.")
            return
            
        panel = self.ui.artifact_panel
        panel.apply_button.clicked.connect(self._on_apply_changes)
        panel.prev_button.clicked.connect(self._go_to_previous_trial)
        panel.next_button.clicked.connect(self._go_to_next_trial)
        panel.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        
        print(f"{LOGP} UI Controls connected.")

    def _on_mode_changed(self, mode_text: str):
        """ Actualiza visibilidad de Point B según el modo. """
        if not self.ui or not hasattr(self.ui, 'artifact_panel'): 
            return
            
        panel = self.ui.artifact_panel
        show_point_b = (mode_text == "Interpolate Interval")
        
        getattr(panel, 'label_b', QWidget()).setVisible(show_point_b)
        getattr(panel, 'point_b', QWidget()).setVisible(show_point_b)
        
        label_a = getattr(panel, 'label_a', None)
        if label_a:
            label_a.setText("Cut until (s):" if mode_text == "Cut From Start" else "Point A (s):")

    def _on_apply_changes(self):
        """Lanza la modificación en un hilo para no bloquear la UI."""
        if not self.ui or not self.widget:
            return

        panel = self.ui.artifact_panel

        if self.current_display_index != -1:
            QMessageBox.warning(self.widget, "Invalid Action",
                                 "Apply changes only from the 'Average' view (Index -1).")
            return

        try:
            mode_text = panel.mode_combo.currentText()
            mode = 'cut' if mode_text == "Cut From Start" else 'interpolate'

            point_a_str = panel.point_a.text().strip()
            if not point_a_str:
                raise ValueError("Point A cannot be empty.")
            point_a = float(point_a_str)

            point_b = 0.0
            if mode == 'interpolate':
                point_b_str = panel.point_b.text().strip()
                if not point_b_str:
                    raise ValueError("Point B cannot be empty for interpolation.")
                point_b = float(point_b_str)
                if point_a == point_b:
                    raise ValueError("Points A and B cannot be the same.")

            # --- Feedback y bloqueo de reentradas
            panel.apply_button.setEnabled(False)
            panel.mode_combo.setEnabled(False)
            panel.prev_button.setEnabled(False)
            panel.next_button.setEnabled(False)
            if self.vtk_interactor:
                try:
                    self.vtk_interactor.Disable()
                except Exception:
                    pass
            self._clear_render("")

            # --- Crear y lanzar worker en un QThread
            self._apply_thread = QtCore.QThread(self.widget)
            self._apply_worker = _ApplyWorker(self.kernel, mode, point_a, point_b)
            self._apply_worker.moveToThread(self._apply_thread)

            # Conexiones
            self._apply_thread.started.connect(self._apply_worker.run)
            # Conexión directa a un callable Python normal (sin decorador @pyqtSlot)
            self._apply_worker.finished.connect(self._on_apply_finished) 
            self._apply_worker.error.connect(self._on_apply_error)

            # Limpieza automática
            self._apply_worker.finished.connect(self._apply_thread.quit)
            self._apply_worker.finished.connect(self._apply_worker.deleteLater)
            self._apply_thread.finished.connect(self._apply_thread.deleteLater)
            self._apply_worker.error.connect(self._apply_thread.quit)
            self._apply_worker.error.connect(self._apply_worker.deleteLater)

            self._apply_thread.start()

        except ValueError as ve:
            QMessageBox.critical(self.widget, "Parameter Error", str(ve))
        except RuntimeError as re:
            QMessageBox.critical(self.widget, "Data Error", str(re))
        except Exception as e:
            QMessageBox.critical(self.widget, "Error", f"An unexpected error occurred: {e}")
            print(f"{LOGP} Error on apply: {e}")

    def _go_to_previous_trial(self):
        num_valid = len(self.valid_indices)
        idx_before = self.current_display_index
        if num_valid == 0: 
            return
            
        if self.current_display_index == 0:
            self.current_display_index = -1 
        elif self.current_display_index == -1:
            self.current_display_index = num_valid - 1 
        else:
            self.current_display_index -= 1
            
        print(f"{LOGP} Nav Prev: {idx_before} -> {self.current_display_index}")
        self._load_and_display_trials()
        # **Añadido para asegurar la actualización gráfica después de la navegación**
        QtCore.QTimer.singleShot(50, self._force_render)

    def _go_to_next_trial(self):
        num_valid = len(self.valid_indices)
        idx_before = self.current_display_index
        if num_valid == 0: 
            return
            
        if self.current_display_index == num_valid - 1:
            self.current_display_index = -1 
        elif self.current_display_index == -1:
            self.current_display_index = 0 
        else:
            self.current_display_index += 1
            
        print(f"{LOGP} Nav Next: {idx_before} -> {self.current_display_index}")
        self._load_and_display_trials()
        # **Añadido para asegurar la actualización gráfica después de la navegación**
        QtCore.QTimer.singleShot(50, self._force_render)

    # --- Carga de Datos y Lógica de Ploteo ---

    def _load_and_display_trials(self):
        """ Carga los datos del trial actual (o promedio) y los muestra. """
        print(f"{LOGP} _load_and_display_trials(). Index: {self.current_display_index}")
        
        if not self.kernel:
            print(f"{LOGP} Info: Kernel missing.")
            return self._clear_render("Kernel missing.")
            
        store = self.kernel.get_service("DataStore")
        if not store:
            print(f"{LOGP} Info: DataStore missing.")
            return self._clear_render("DataStore missing.")
            
        active_signal = store.get_active_signal()
        if not isinstance(active_signal, SignalDataset):
            print(f"{LOGP} Info: No active signal.")
            self._reset_state()
            return self._clear_render("No active signal selected.")

        current_td: Optional[TrialDataset] = None
        if active_signal.trials_dataset:
            current_td = active_signal.trials_dataset[-1]
            f_name = Path(current_td.source).name if current_td.source else "?"
            d_key = (f_name, current_td.channel_name)
            
            self.discarded_indices = active_signal.discarded_trials.get(d_key, set())
            if not isinstance(self.discarded_indices, set):
                self.discarded_indices = set()

            mods = current_td.metadata.get("modified_trials", set())
            if isinstance(mods, set):
                self.modified_indices = mods
            else:
                try: 
                    self.modified_indices = set(mods)
                except TypeError: 
                    self.modified_indices = set()
            
            self.total_original_trials = current_td.trials.shape[1]
            self.valid_indices = [i for i in range(self.total_original_trials) if i not in self.discarded_indices]
        else:
            print(f"{LOGP} Info: No trial data found.")
            self._reset_state()
            return self._clear_render("No trial data in active signal.\n(Please run 'Trials' first).")

        num_valid = len(self.valid_indices)
        if not (-1 <= self.current_display_index < num_valid):
            self.current_display_index = -1 

        status, data, title = "", None, ""
        t = current_td.time_rel # Obtener t (tiempo)

        valid_cols = None
        if num_valid > 0:
            try:
                valid_cols = current_td.trials[:, self.valid_indices]
            except Exception as e:
                print(f"{LOGP} Error selecting valid trials: {e}")
                self._reset_state()
                return self._clear_render("Error selecting trials.")

        apply_ok = (self.current_display_index == -1 and num_valid > 0)
        if self.ui:
            self.ui.artifact_panel.apply_button.setEnabled(apply_ok)

        if self.current_display_index == -1: # Modo Promedio
            if num_valid == 0:
                print(f"{LOGP} Info: All trials discarded.")
                self._reset_state()
                return self._clear_render("All trials discarded.")
            if valid_cols is None: 
                return self._clear_render("Error getting valid trials.")
                
            data = np.nanmean(valid_cols, axis=1)
            title = f"Average ({num_valid} Valid) - {current_td.channel_name}"
            status = f"Viewing Average / {num_valid} Valid ({self.total_original_trials} Total)"
        
        else: # Modo Individual
            try:
                orig_idx = self.valid_indices[self.current_display_index]
                data = current_td.trials[:, orig_idx]
                suffix = " (mod)" if orig_idx in self.modified_indices else ""
                title = f"Trial {orig_idx + 1} - {current_td.channel_name}"
                status = f"Viewing Valid {self.current_display_index+1}/{num_valid} (Orig. {orig_idx+1}{suffix}) / {self.total_original_trials} Total"
            except Exception as e:
                print(f"{LOGP} Error accessing trial: {e}. Resetting.")
                self._reset_state()
                self._load_and_display_trials() 
                return

        if self.ui:
            self.ui.artifact_panel.trial_status_label.setText(status)
        
        # --- sanity check: t (tiempo) vs y (data) ---
        if not isinstance(t, np.ndarray):
            t = np.asarray(t)
        if not isinstance(data, np.ndarray):
            data = np.asarray(data)

        if t.ndim != 1:
            raise RuntimeError(f"time_rel debe ser 1D, recibido shape={t.shape}")
        if data.ndim != 1:
            raise RuntimeError(f"serie a graficar debe ser 1D, recibido shape={data.shape}")
        if t.shape[0] != data.shape[0]:
            # Intento de autocorrección común si las trials están transpuestas
            # (samples, trials) es lo esperado. Si vino (trials, samples), avisamos.
            raise RuntimeError(
                f"Inconsistencia: len(t)={t.shape[0]} y len(y)={data.shape[0]}. "
                "Revisa la forma de trials: se espera (samples, trials)."
            )
        # --- fin sanity check ---

        self._plot_curve(t, data, title)

    # --- Lógica de Visualización VTK ---

    # --- INICIO SOLUCIÓN DEFINITIVA (V_FINAL) ---
    def _ensure_vtk(self):
        """ 
        Asegura que el interactor y la vista VTK existan y estén en el layout.
        Esta versión restaura la interacción 2D correcta para EVITAR DEFORMACIÓN
        y DESHABILITA el observador de mouse para EVITAR CRASH.
        """
        
        # 1. Chequear si ya existe (lógica nuestra, pero es segura)
        if (self.vtk_interactor and self.vtk_view and 
            self.ui.plotArea.layout() and 
            self.ui.plotArea.layout().indexOf(self.vtk_interactor) != -1):
            
            if not self.vtk_interactor.isEnabled():
                try: 
                    self.vtk_interactor.Enable()
                except Exception as e:
                    print(f"{LOGP} Error re-enabling VTK: {e}")
            return # Ya está listo

        print(f"{LOGP} _ensure_vtk(): Setting up VTK...")
        
        try:
            # 2. Lógica de layout (estilo FFT para robustez)
            self.vtk_interactor = QVTKRenderWindowInteractor(self.ui.plotArea)
            self.ui.plotArea.setLayout(QtWidgets.QVBoxLayout())
            self.ui.plotArea.layout().setContentsMargins(0, 0, 0, 0)
            self.ui.plotArea.layout().addWidget(self.vtk_interactor)
            print(f"{LOGP} VTK Interactor embedded.")

            self.vtk_view = vtk.vtkContextView()
            
            # LOG 1: Antes de SetRenderWindow
            print(f"{LOGP} DEBUG: Setting RenderWindow on vtkContextView.")
            self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
            # LOG 2: Después de SetRenderWindow
            print(f"{LOGP} DEBUG: RenderWindow set. Setting background.")
            
            self.vtk_view.GetRenderer().SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))

            # 3. CORRECCIÓN DE DEFORMACIÓN/CRASH (Decisión Drástica):
            # Se ha ELIMINADO la línea self.vtk_view.SetInteractor(self.vtk_interactor)
            # para evitar la doble conexión y el conflicto de bucle de eventos que causaba el crash.
            print(f"{LOGP} Using QVTKRenderWindowInteractor directly.")
            
            # --- INICIO DEL ARREGLO DE ZOOM (NO DEFORMANTE) ---
            # Se obtiene el interactor de VTK para establecer el estilo 2D (Context).
            # LOG 3: Antes de GetInteractor
            print(f"{LOGP} DEBUG: Attempting to get VTK Interactor.")
            interactor = self.vtk_interactor.GetRenderWindow().GetInteractor()
            # LOG 4: Después de GetInteractor
            print(f"{LOGP} DEBUG: VTK Interactor object retrieved: {interactor is not None}")
            
            if interactor and not interactor.GetInteractorStyle():
                # Esta es la línea crítica que asegura el zoom 2D correcto y la estabilidad.
                # LOG 5: Antes de SetInteractorStyle
                print(f"{LOGP} DEBUG: Setting vtkContextInteractorStyle.")
                interactor.SetInteractorStyle(vtk.vtkContextInteractorStyle())
                # LOG 6: Después de SetInteractorStyle
                print(f"{LOGP} Explicitly set vtkContextInteractorStyle to fix zoom deformation and crash.")
            # --- FIN DEL ARREGLO DE ZOOM ---
            
            # 4. CORRECCIÓN DE CRASH:
            # NO añadimos el observador de MouseMoveEvent.
            print(f"{LOGP} MouseMove observer is DISABLED to prevent interaction crash.")
            
            # LOG 7: Antes de Initialize
            print(f"{LOGP} DEBUG: Calling Initialize.")
            self.vtk_interactor.Initialize()
            # LOG 8: Después de Initialize
            print(f"{LOGP} DEBUG: Initialize finished.")
            
            # Se elimina self.vtk_interactor.Start() para evitar conflicto con el bucle de eventos de Qt.
            # self.vtk_interactor.Start() 
            print(f"{LOGP} VTK Initialized.")
            
        except Exception as e:
            print(f"{LOGP} CRITICAL VTK Setup Error: {e}")
            self._cleanup_vtk_references()
            if self.ui and self.ui.plotArea:
                lbl = QLabel(f"VTK Error:\n{e}", self.ui.plotArea)
                lbl.setAlignment(QtCore.Qt.AlignCenter)
                if self.ui.plotArea.layout():
                    self.ui.plotArea.layout().addWidget(lbl)
    # --- FIN SOLUCIÓN DEFINITIVA (V_FINAL) ---

    def _cleanup_vtk_references(self):
       """ Limpia referencias VTK para evitar memory leaks. """
       self.vtk_interactor = None
       self.vtk_view = None
       self.chart = None
       self.vtk_menu = None
       print(f"{LOGP} VTK references cleaned.")

    # --- INICIO CORRECCIÓN CRASH ---
    # La función _on_mouse_move está deshabilitada
    # porque su observador fue eliminado en _ensure_vtk.
    #
    # def _on_mouse_move(self, style_obj, event):
    #     """ Muestra coordenadas en la barra de estado. """
    #     
    #     try:
    #         if style_obj.GetState() != 0:
    #             return 
    #         ...
    #     except Exception as e:
    #         print(f"{LOGP} Error in _on_mouse_move: {e}")
    # --- FIN CORRECCIÓN CRASH ---


    def _plot_curve(self, t: np.ndarray, y: np.ndarray, title: str = ""):
        """ Dibuja los arrays 't' y 'y' en el chart VTK. """
        
        if self.vtk_view is None:
            self._ensure_vtk()

        if not self.vtk_view or not self.vtk_interactor:
            if self.widget: 
                QMessageBox.critical(self.widget, "VTK Error", "Failed to initialize VTK view.")
            return

        try:
            scene = self.vtk_view.GetScene()
            scene.ClearItems()
            renderer = self.vtk_view.GetRenderer()
            
            # CORRECCIÓN: Asegurarse de que los actores 2D (mensajes de texto) se limpien.
            renderer.GetActors2D().RemoveAllItems() 
            
            # NUEVO: Forzar un renderizado inmediato para limpiar la caché visual del mensaje de texto.
            self.vtk_view.GetRenderWindow().Render() 
            
            renderer.SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))

            # --- limpiar datos y convertir a VTK de forma segura (Reemplazo Bloque 3) ---
            finite_mask = np.isfinite(t) & np.isfinite(y)
            valid_mask = finite_mask.copy()
            
            t_valid = t[valid_mask]
            y_valid = y[valid_mask]
            
            n_points = t_valid.shape[0]

            if n_points == 0:
                raise RuntimeError("No hay puntos válidos para graficar (NaN/Inf).")
            
            # Conversión segura a VTK (sin SetVoidArray)
            vtk_t = nps.numpy_to_vtk(t_valid.astype(np.float64), deep=True)  # usa double para evitar overflow
            vtk_t.SetName("Time (s)")
            vtk_y = nps.numpy_to_vtk(y_valid.astype(np.float64), deep=True)  # idem
            vtk_y.SetName("Amplitude")

            table = vtk.vtkTable()
            table.AddColumn(vtk_t)
            table.AddColumn(vtk_y)

            self.chart = vtk.vtkChartXY()
            scene.AddItem(self.chart)
            plot = self.chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, "Time (s)", "Amplitude")
            plot.SetWidth(1.5)

            color = "Crimson" if self.current_display_index == -1 else "SteelBlue"
            plot.GetPen().SetColor(vtk.vtkNamedColors().GetColor4ub(color))

            self.chart.SetTitle(title)
            axis_b = self.chart.GetAxis(vtk.vtkAxis.BOTTOM); axis_b.SetTitle("Time (s)")
            axis_l = self.chart.GetAxis(vtk.vtkAxis.LEFT);   axis_l.SetTitle("Amplitude")
            axis_b.SetGridVisible(True); axis_l.SetGridVisible(True)

            # Si los valores son absurdamente grandes, advierte en log
            max_abs = float(np.nanmax(np.abs(y_valid)))
            if not np.isfinite(max_abs) or max_abs > 1e12:
                print(f"{LOGP} WARNING: amplitud muy grande (|y| max ≈ {max_abs:.3e}). Revisa unidades/escala de la señal.")

            self.chart.RecalculateBounds()
            print(f"{LOGP} _plot_curve: Plot '{title}' con {n_points} puntos válidos (carga segura).")
            # --- FIN Reemplazo Bloque 3 ---

        except RuntimeError as re:
            # Manejar el error de "No hay puntos válidos" o de inconsistencia de shape
            print(f"{LOGP} _plot_curve: Error al plotear (runtime): {re}")
            self.chart = None
            txt = vtk.vtkTextActor()
            txt.SetInput(f"No data to display for:\n{title}\nError: {re}")
            prop = txt.GetTextProperty()
            prop.SetColor(0.2, 0.2, 0.2); prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToCentered(); prop.SetFontSize(16)
            
            size = renderer.GetSize()
            txt.SetPosition(size[0] / 2, size[1] / 2)
            renderer.AddActor2D(txt)
            
        except Exception as e:
            print(f"{LOGP} Error during _plot_curve: {e}")
            self._clear_render(f"Error plotting:\n{e}")

    # --- Funciones de utilidad ---

    def _reset_state(self):
        """ Resetea el estado interno del plugin. """
        print(f"{LOGP} Resetting state...")
        self.current_display_index = -1
        self.valid_indices = []
        self.total_original_trials = 0
        self.discarded_indices = set()
        self.modified_indices = set()
        
        if self.ui:
            try:
                self.ui.artifact_panel.trial_status_label.setText("Status: N/A")
                self.ui.artifact_panel.point_a.setText("0.0")
                self.ui.artifact_panel.point_b.setText("0.0")
                self.ui.artifact_panel.apply_button.setEnabled(False)
            except Exception as e:
                print(f"{LOGP} Error resetting UI state: {e}")

    def _clear_render(self, message=""):
        """ Limpia la vista VTK y muestra un mensaje opcional. """
        
        if self.vtk_view is None:
            self._ensure_vtk()
        
        if not self.vtk_view or not self.vtk_interactor:
            print(f"{LOGP} VTK not available to clear.")
            return
            
        print(f"{LOGP} Clearing render. Msg: '{message}'")
        try:
            scene = self.vtk_view.GetScene()
            scene.ClearItems()
            renderer = self.vtk_view.GetRenderer()
            
            # El actor de texto de carga se añade aquí, así que hay que asegurarse de que se borre.
            # Ya lo estamos haciendo en _plot_curve y GetActors2D().RemoveAllItems() se encarga.
            renderer.GetActors2D().RemoveAllItems()
            
            renderer.SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))
            
            if message:
                txt = vtk.vtkTextActor()
                txt.SetInput(message)
                prop = txt.GetTextProperty()
                prop.SetColor(0.2, 0.2, 0.2)
                prop.SetJustificationToCentered()
                prop.SetVerticalJustificationToCentered()
                prop.SetFontSize(16)
                
                size = renderer.GetSize()
                if size[0] > 0 and size[1] > 0:
                   txt.SetPosition(size[0] / 2, size[1] / 2)
                else:
                   txt.SetPosition(200, 200) 
                    
                renderer.AddActor2D(txt)
                
            self.vtk_view.GetRenderWindow().Render()
        except Exception as e:
            print(f"{LOGP} Error during _clear_render: {e}")

    def _on_data_updated(self, topic: str, payload: object):
        """Escucha eventos del kernel y agrupa refrescos (debounce) para evitar lag o bloqueos."""
        try:
            if topic in ["signal_added", "active_signal_changed", "trials_generated", "trial_discard_updated"]:
                if self.widget and self.widget.isVisible():
                    print(f"{LOGP} Event '{topic}' received. Coalescing update...")

                    # En lugar de refrescar de inmediato, programamos un refresh único en 120 ms.
                    # Esto evita múltiples renders seguidos cuando el kernel dispara varios eventos.
                    if hasattr(self, "_refresh_timer"):
                        self._refresh_timer.start()
                    else:
                        # fallback si el timer aún no existe
                        self._reset_state()
                        if self.vtk_interactor and not self.vtk_interactor.isEnabled():
                            try:
                                self.vtk_interactor.Enable()
                            except Exception:
                                pass
                        self._load_and_display_trials()
                        QtCore.QTimer.singleShot(50, self._force_render)
        except Exception as e:
            print(f"{LOGP} Error in _on_data_updated: {e}")

    def _on_apply_finished(self, modified_td):
        """Señal: el worker terminó correctamente."""
        print(f"{LOGP} finished received, type={type(modified_td)}")
        try:
            if modified_td:
                QMessageBox.information(self.widget, "Success", "Changes applied to all valid trials.")
            else:
                QMessageBox.information(self.widget, "No Changes", "No modifications were applied.")
        finally:
            # Rehabilitar UI y refrescar
            try:
                if self.vtk_interactor:
                    try:
                        self.vtk_interactor.Enable()
                    except Exception:
                        pass
                panel = self.ui.artifact_panel
                panel.apply_button.setEnabled(True)
                panel.mode_combo.setEnabled(True)
                panel.prev_button.setEnabled(True)
                panel.next_button.setEnabled(True)

                # Recarga y render forzado
                self._reset_state()
                self._load_and_display_trials()
                QtCore.QTimer.singleShot(50, self._force_render)
            except Exception as e:
                print(f"{LOGP} _on_apply_finished UI restore error: {e}")

    def _on_apply_error(self, msg):
        """Señal: el worker reportó un error."""
        try:
            QMessageBox.critical(self.widget, "Apply Error", msg)
        finally:
            try:
                if self.vtk_interactor:
                    try:
                        self.vtk_interactor.Enable()
                    except Exception:
                        pass
                panel = self.ui.artifact_panel
                panel.apply_button.setEnabled(True)
                panel.mode_combo.setEnabled(True)
                panel.prev_button.setEnabled(True)
                panel.next_button.setEnabled(True)
                QtCore.QTimer.singleShot(50, self._force_render)
            except Exception as e:
                print(f"{LOGP} _on_apply_error UI restore error: {e}")

# --- FIN DEL ARCHIVO ---

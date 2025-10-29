# Ubicación: plugins/preprocessing/prepare/artifact_remove/artifact_remove_plugin.py
# VERSIÓN REFACTORIZADA Y COMPLETA (Restaurada)

from vtk.util import numpy_support as nps # Importación segura para VTK/NumPy
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QWidget, QMessageBox, QVBoxLayout, QLabel
import numpy as np
import vtk
from typing import Optional, List, Set
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from types import SimpleNamespace # Para el helper de trials

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

from plugins.preprocessing.prepare.artifact_remove.artifact_remove_ui import Ui_ArtifactRemove
# Importar la función de lógica correcta
from plugins.preprocessing.prepare.artifact_remove.artifact_logic import apply_modification_to_all_valid

# Intento de importación de clases personalizadas
try:
    from core.plugins.vtk_context_menu import VTKContextMenu
except ImportError:
    VTKContextMenu = None

LOGP = "[ArtifactRemovePlugin]"
# --- Worker para ejecutar la lógica pesada en otro hilo ---
class _ApplyWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int)
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

        self._apply_thread = None
        self._apply_worker = None

        self._refresh_timer = QtCore.QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120) # ms
        self._refresh_timer.timeout.connect(self._refresh_view_coalesced)

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
        """ Entrega el widget principal del plugin a la ventana principal. """
        
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
        show_point_b = (mode_text == "Interpolate Interval" or mode_text == "Blank Interval")
        
        getattr(panel, 'label_b', QWidget()).setVisible(show_point_b)
        getattr(panel, 'point_b', QWidget()).setVisible(show_point_b)
        
        label_a = getattr(panel, 'label_a', None)
        if label_a:
            if mode_text == "Cut From Start":
                 label_a.setText("Cut until (s):")
            else:
                 label_a.setText("Point A (s):")

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
            # Ajuste de modo basado en la lógica de modificación de valores.
            mode = 'blank' if mode_text in ("Cut From Start", "Blank Interval") else 'interpolate'

            point_a_str = panel.point_a.text().strip()
            if not point_a_str:
                raise ValueError("Point A cannot be empty.")
            point_a = float(point_a_str)

            point_b = 0.0
            if mode == 'interpolate' or mode_text == "Blank Interval": # Si es interpolación o blanking por intervalo (debe tener B)
                point_b_str = panel.point_b.text().strip()
                if not point_b_str:
                    # En el modo "Cut From Start", B no es obligatorio, por eso se omite el raise aquí.
                    if mode_text != "Cut From Start":
                         raise ValueError("Point B cannot be empty for interval modification.")
                else:
                    point_b = float(point_b_str)
                    if point_a == point_b and mode_text != "Cut From Start":
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
        if num_valid <= 0: 
            return
        idx_before = self.current_display_index
        if self.current_display_index == 0:
            self.current_display_index = -1 
        elif self.current_display_index == -1:
            self.current_display_index = num_valid - 1 
        else:
            self.current_display_index -= 1
            
        print(f"{LOGP} Nav Prev: {idx_before} -> {self.current_display_index}")
        self._load_and_display_trials()
        QtCore.QTimer.singleShot(50, self._force_render)

    def _go_to_next_trial(self):
        num_valid = len(self.valid_indices)
        if num_valid <= 0: 
            return
        idx_before = self.current_display_index
        if self.current_display_index == num_valid - 1:
            self.current_display_index = -1 
        elif self.current_display_index == -1:
            self.current_display_index = 0 
        else:
            self.current_display_index += 1
            
        print(f"{LOGP} Nav Next: {idx_before} -> {self.current_display_index}")
        self._load_and_display_trials()
        QtCore.QTimer.singleShot(50, self._force_render)

    # --- HELPERS PARA OBTENER TRIALS ACTIVOS ---
    def _get_active_signal_and_name(self):
        store = self.kernel.get_service("DataStore")
        if not store:
            raise RuntimeError("DataStore missing.")
        sd = store.get_active_signal()
        if not isinstance(sd, SignalDataset):
            raise RuntimeError("No active signal selected.")
        sig_name = getattr(sd, "name", None) or getattr(sd, "signal_name", None) or getattr(sd, "id", None)
        if not sig_name and hasattr(sd, "get_name"):
            sig_name = sd.get_name()
        if not sig_name:
            raise RuntimeError("Active Signal has no name.")
        return sd, sig_name
        
    def _get_current_channel_name(self, sd: SignalDataset) -> str:
        """
        Devuelve el nombre de canal a usar para get_active_trials.
        """
        # 1) último TrialDataset
        try:
            tds = getattr(sd, "trials_dataset", None)
            if tds and len(tds) > 0:
                last_td = tds[-1]
                ch = getattr(last_td, "channel_name", None)
                if ch:
                    return str(ch)
        except Exception:
            pass

        # 2) lista de nombres conocida
        try:
            names = getattr(sd, "channel_names", None)
            if names and len(names) > 0:
                return str(names[0])
        except Exception:
            pass

        # 3) fallback si hay señales
        sig = getattr(sd, "signals", None)
        if sig is not None and getattr(sig, "shape", None) and sig.shape[0] > 0:
            # si no hay nombres, asumimos "ch-1"
            return "ch-1"

        raise RuntimeError("No channel selected/found. Generate Trials first or select a channel.")


    def _fetch_active_trials(self):
        sd, sig_name = self._get_active_signal_and_name()
        if not hasattr(sd, "get_active_trials"):
            raise RuntimeError("SignalDataset.get_active_trials(...) not available.")

        # NUEVO: resolver canal
        channel_name = self._get_current_channel_name(sd)

        # Llamada correcta (con canal)
        result = sd.get_active_trials(sig_name, channel_name)

        td = None; meta = {}
        if isinstance(result, TrialDataset):
            td = result
        elif isinstance(result, (list, tuple)):
            for it in result:
                if isinstance(it, TrialDataset):
                    td = it
                elif isinstance(it, dict):
                    meta.update(it)
        elif isinstance(result, dict):
            meta.update(result)
            trials = meta.get("trials"); time_rel = meta.get("time_rel")
            if trials is not None and time_rel is not None:
                td = SimpleNamespace(
                    trials=np.asarray(trials),
                    time_rel=np.asarray(time_rel),
                    channel_name=meta.get("channel_name", "Unknown"),
                    metadata=meta,
                )
        if td is None:
            raise RuntimeError("get_active_trials() returned an unsupported format.")

        trials = np.asarray(td.trials)
        time_rel = np.asarray(getattr(td, "time_rel", meta.get("time_rel", None)))
        if time_rel is None:
            raise RuntimeError("Active trials missing time_rel.")
        if trials.ndim != 2:
            raise RuntimeError(f"Active trials must be 2D. Got {trials.shape}.")

        n_total = int(meta.get("total_trials", getattr(td, "total_trials", trials.shape[1])))
        orig_idx = meta.get("orig_indices", getattr(td, "orig_indices", None))
        if orig_idx is None:
            orig_idx = list(range(trials.shape[1]))
        else:
            orig_idx = list(map(int, orig_idx))
            
        # NUEVO: usar channel_name resuelto si el resultado no lo trae
        chan = getattr(td, "channel_name", meta.get("channel_name", channel_name))

        return SimpleNamespace(
            time_rel=time_rel,
            trials=trials,
            orig_indices=orig_idx,
            channel_name=chan,
            total_trials=n_total,
        )

    # --- Carga de Datos y Lógica de Ploteo ---
    def _load_and_display_trials(self):
        """Carga trials activos vía get_active_trials y muestra promedio o individual."""
        print(f"{LOGP} _load_and_display_trials(). Index: {self.current_display_index}")
        if not self.kernel:
            return self._clear_render("Kernel missing.")
        try:
            active = self._fetch_active_trials()
        except Exception as e:
            msg = str(e)
            print(f"{LOGP} fetch active trials error: {msg}")
            self._reset_state()
            # 3. Mensaje claro cuando aún no hay trials
            if "No channel selected" in msg or "Generate Trials" in msg or "not available" in msg:
                return self._clear_render("No trial data. Please generate Trials first (Preprocessing → Trials).")
            return self._clear_render(msg)


        t = np.asarray(active.time_rel)
        trials = np.asarray(active.trials)          # (Ns, Tact)
        orig_indices = list(active.orig_indices)    # mapeo a índices originales
        total_trials = int(active.total_trials)
        channel_name = active.channel_name

        Tact = trials.shape[1]
        if Tact == 0:
            self._reset_state()
            return self._clear_render("No active trials for this signal.")
        if not (-1 <= self.current_display_index < Tact):
            self.current_display_index = -1

        # 4. Poblar valid_indices para navegación
        self.valid_indices = list(range(Tact))
        self.total_original_trials = int(total_trials) 

        if self.ui:
            self.ui.artifact_panel.apply_button.setEnabled(self.current_display_index == -1 and Tact > 0)

        if self.current_display_index == -1:
            y = np.nanmean(trials, axis=1)
            title = f"Average ({Tact} Valid) - {channel_name}"
            status = f"Viewing Average / {Tact} Valid ({total_trials} Total)"
        else:
            idx = self.current_display_index
            y = trials[:, idx]
            orig_idx = orig_indices[idx] if idx < len(orig_indices) else idx
            title = f"Trial {orig_idx + 1} - {channel_name}"
            status = f"Viewing Valid {idx + 1}/{Tact} (Orig. {orig_idx + 1}) / {total_trials} Total"

        if self.ui:
            self.ui.artifact_panel.trial_status_label.setText(status)

        if t.ndim != 1 or y.ndim != 1:
            return self._clear_render(f"Invalid shapes: time={t.shape}, data={y.shape}")
        if t.shape[0] != y.shape[0]:
            return self._clear_render(f"Length mismatch: time={t.shape[0]}, data={y.shape[0]}")

        self._plot_curve(t, y, title)

    # --- Lógica de Visualización VTK ---
    def _ensure_vtk(self):
        """ 
        Asegura que el interactor y la vista VTK existan y estén en el layout.
        """
        
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
            self.vtk_interactor = QVTKRenderWindowInteractor(self.ui.plotArea)
            self.ui.plotArea.setLayout(QtWidgets.QVBoxLayout())
            self.ui.plotArea.layout().setContentsMargins(0, 0, 0, 0)
            self.ui.plotArea.layout().addWidget(self.vtk_interactor)
            print(f"{LOGP} VTK Interactor embedded.")

            self.vtk_view = vtk.vtkContextView()
            
            print(f"{LOGP} DEBUG: Setting RenderWindow on vtkContextView.")
            self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
            print(f"{LOGP} DEBUG: RenderWindow set. Setting background.")
            
            self.vtk_view.GetRenderer().SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))

            print(f"{LOGP} Using QVTKRenderWindowInteractor directly.")
            
            print(f"{LOGP} DEBUG: Attempting to get VTK Interactor.")
            interactor = self.vtk_interactor.GetRenderWindow().GetInteractor()
            print(f"{LOGP} DEBUG: VTK Interactor object retrieved: {interactor is not None}")
            
            if interactor and not interactor.GetInteractorStyle():
                print(f"{LOGP} DEBUG: Setting vtkContextInteractorStyle.")
                interactor.SetInteractorStyle(vtk.vtkContextInteractorStyle())
                print(f"{LOGP} Explicitly set vtkContextInteractorStyle to fix zoom deformation and crash.")
            
            print(f"{LOGP} MouseMove observer is DISABLED to prevent interaction crash.")
            
            print(f"{LOGP} DEBUG: Calling Initialize.")
            self.vtk_interactor.Initialize()
            print(f"{LOGP} DEBUG: Initialize finished.")
            
            print(f"{LOGP} VTK Initialized.")
            
        except Exception as e:
            print(f"{LOGP} CRITICAL VTK Setup Error: {e}")
            self._cleanup_vtk_references()
            if self.ui and self.ui.plotArea:
                lbl = QLabel(f"VTK Error:\n{e}", self.ui.plotArea)
                lbl.setAlignment(QtCore.Qt.AlignCenter)
                if self.ui.plotArea.layout():
                    self.ui.plotArea.layout().addWidget(lbl)

    def _cleanup_vtk_references(self):
       """ Limpia referencias VTK para evitar memory leaks. """
       self.vtk_interactor = None
       self.vtk_view = None
       self.chart = None
       self.vtk_menu = None
       print(f"{LOGP} VTK references cleaned.")


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
            
            renderer.GetActors2D().RemoveAllItems() 
            
            # Corrección del mensaje persistente: forzar render después de limpiar actores 2D
            self.vtk_view.GetRenderWindow().Render() 
            
            renderer.SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))

            # --- limpiar datos y convertir a VTK de forma segura (nps.numpy_to_vtk) ---
            finite_mask = np.isfinite(t) & np.isfinite(y)
            valid_mask = finite_mask.copy()
            
            t_valid = t[valid_mask]
            y_valid = y[valid_mask]
            
            n_points = t_valid.shape[0]

            if n_points == 0:
                raise RuntimeError("No hay puntos válidos para graficar (NaN/Inf).")
            
            vtk_t = nps.numpy_to_vtk(t_valid.astype(np.float64), deep=True)
            vtk_t.SetName("Time (s)")
            vtk_y = nps.numpy_to_vtk(y_valid.astype(np.float64), deep=True)
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

            max_abs = float(np.nanmax(np.abs(y_valid)))
            if not np.isfinite(max_abs) or max_abs > 1e12:
                print(f"{LOGP} WARNING: amplitud muy grande (|y| max ≈ {max_abs:.3e}). Revisa unidades/escala de la señal.")

            self.chart.RecalculateBounds()
            print(f"{LOGP} _plot_curve: Plot '{title}' con {n_points} puntos válidos (carga segura).")

        except RuntimeError as re:
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

                    if hasattr(self, "_refresh_timer"):
                        self._refresh_timer.start()
                    else:
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

# Ubicación: plugins/preprocessing/prepare/artifact_remove/artifact_remove_plugin.py
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
# --- MODIFICADO: Importar la nueva función de lógica ---
from plugins.preprocessing.prepare.artifact_remove.artifact_logic import apply_modification_to_all_valid

# --- Intento de importación de clases personalizadas ---
try:
    # Estas clases mejoran la experiencia de usuario si están disponibles
    from core.plugins.vtk_context_menu import VTKInteractorStyleZoomAxis, VTXContextMenu
except ImportError:
    # Si no se encuentran, usamos las clases por defecto de VTK.
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
            # Asegurarse que VTK esté listo antes de cargar datos
            self.plugin._ensure_vtk()
            # Cargar datos después de asegurar VTK
            self.plugin._load_and_display_trials()
            # Habilitar interactor si existe
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
        self.current_display_index: int = -1 # -1 significa promedio
        self.valid_indices: List[int] = [] # Lista de índices ORIGINALES que son válidos (no descartados)
        self.total_original_trials: int = 0 # Total de columnas en la matriz de trials actual
        self.discarded_indices: Set[int] = set() # Set de índices ORIGINALES descartados
        self.modified_indices: Set[int] = set() # Set de índices ORIGINALES modificados

    def initialize(self, kernel): pass
    # process no se usa activamente en este plugin
    def process(self, data): pass

    def start(self, kernel):
        print(f"{LOGP} start()")
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        try:
            # Conectar a eventos relevantes para actualizar la vista
            self.kernel.event.connect(self._on_data_updated)
            print(f"{LOGP} Conectado a eventos del kernel.")
        except Exception as e:
            print(f"{LOGP} Error al conectar a eventos: {e}")

    def stop(self):
        print(f"{LOGP} stop() - Limpiando VTK si existe, conservando UI.")
        # Remover observadores para evitar llamadas a self._on_mouse_move después de limpiar
        if self.vtk_view and self.vtk_view.GetInteractor():
            try:
                # Usar GetInteractorStyle() puede ser más robusto si el estilo cambia
                interactor_style = self.vtk_view.GetInteractor() # O GetInteractorStyle()? Chequear API VTK
                if interactor_style:
                     interactor_style.RemoveObservers(vtk.vtkCommand.MouseMoveEvent)
                     print(f"{LOGP} Observador MouseMoveEvent removido.")
            except Exception as e:
                 print(f"{LOGP} Error removiendo observador MouseMove: {e}")

        # Limpiar la escena VTK
        if self.vtk_view:
            try:
                self.vtk_view.GetScene().ClearItems()
                print(f"{LOGP} Escena VTK limpiada.")
            except Exception as e:
                print(f"{LOGP} Error limpiando escena VTK: {e}")

        # Deshabilitar y programar borrado del interactor Qt/VTK
        if self.vtk_interactor:
            try:
                self.vtk_interactor.Disable()
                self.vtk_interactor.Finalize() # Ayuda a liberar recursos
                self.vtk_interactor.deleteLater() # Borrado seguro en Qt
                print(f"{LOGP} Interactor VTK deshabilitado y programado para borrado.")
            except Exception as e:
                print(f"{LOGP} Error deshabilitando/borrando interactor VTK: {e}")

        # Limpiar referencias para forzar la recreación completa en la próxima muestra
        self.vtk_interactor = None
        self.vtk_view = None
        self.chart = None
        self.vtk_menu = None
        print(f"{LOGP} Referencias VTK limpiadas.")


    def get_widget(self, parent=None):
        if self.widget is None:
            print(f"{LOGP} get_widget(): Creando UI y VTK por primera vez...")
            # Usar el widget personalizado que maneja showEvent
            self.widget = ArtifactRemoveWidget(self, parent)
            self.ui = Ui_ArtifactRemove()
            self.ui.setupUi(self.widget)

            # Configurar VTK (solo si no existe)
            self._ensure_vtk()
            # Conectar controles de la UI
            self._wire_controls()
            # Carga inicial de datos
            print(f"{LOGP} get_widget(): Cargando datos iniciales...")
            self._load_and_display_trials()
            # Asegurar estado inicial de Point B
            self._on_mode_changed(self.ui.artifact_panel.mode_combo.currentText())

        # Siempre reasignar padre por si cambia el contenedor
        self.widget.setParent(parent)

        # Habilitar interactor si existe (puede haber sido deshabilitado en stop)
        if self.vtk_interactor:
            try:
                 if not self.vtk_interactor.isEnabled():
                      self.vtk_interactor.Enable()
                      print(f"{LOGP} Interactor VTK re-habilitado.")
            except Exception as e:
                 print(f"{LOGP} Error re-habilitando interactor: {e}")

        return self.widget

    # --- Lógica de la Interfaz de Usuario ---

    def _wire_controls(self):
        """Conecta señales y slots de los controles del panel."""
        panel = self.ui.artifact_panel
        panel.apply_button.clicked.connect(self._on_apply_changes)
        panel.prev_button.clicked.connect(self._go_to_previous_trial)
        panel.next_button.clicked.connect(self._go_to_next_trial)
        # Conectar cambio de modo para mostrar/ocultar Point B
        panel.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        print(f"{LOGP} Controles UI conectados.")

    # --- AÑADIDO: Mostrar/ocultar Point B según el modo ---
    def _on_mode_changed(self, mode_text: str):
         """Actualiza la visibilidad del Point B basado en el modo seleccionado."""
         show_point_b = (mode_text == "Interpolate")
         self.ui.artifact_panel.point_b_label.setVisible(show_point_b)
         self.ui.artifact_panel.point_b.setVisible(show_point_b)
         # print(f"{LOGP} Modo cambiado a '{mode_text}'. Point B visible: {show_point_b}")

    # --- MODIFICADO: Llamar a la nueva lógica ---
    def _on_apply_changes(self):
        """Se ejecuta al presionar 'Apply'. Llama a la lógica para modificar todos los trials."""
        panel = self.ui.artifact_panel
        mode_text = panel.mode_combo.currentText()
        mode = 'cut' if mode_text == "Cut From Start" else 'interpolate'

        # --- VALIDACIÓN: Solo aplicar desde la vista promedio ---
        if self.current_display_index != -1:
            QMessageBox.warning(self.widget, "Acción no Válida",
                                "La modificación de artefactos ahora se aplica a todos los trials válidos simultáneamente.\n\n"
                                "Por favor, navegue a la vista 'Promedio' (Average)\n"
                                "(usando 'Next'/'Previous' hasta que el estado lo indique)\n"
                                "para definir los puntos y aplicar el cambio globalmente.")
            return
        # --- FIN VALIDACIÓN ---

        try:
            # Obtener puntos A y B del panel
            point_a_str = panel.point_a.text().strip()
            point_b_str = panel.point_b.text().strip() if mode == 'interpolate' else "0.0"

            if not point_a_str: raise ValueError("Punto A no puede estar vacío.")
            point_a = float(point_a_str)

            if mode == 'interpolate':
                 if not point_b_str: raise ValueError("Punto B no puede estar vacío para interpolar.")
                 point_b = float(point_b_str)
                 if point_a == point_b: raise ValueError("Punto A y Punto B deben ser diferentes para interpolar.")
            else:
                 point_b = 0.0 # No se usa para 'cut'

            print(f"{LOGP} Solicitando aplicar '{mode}' globalmente con A={point_a}, B={point_b}")

            # --- LLAMAR A LA NUEVA FUNCIÓN DE LÓGICA ---
            modified_td = apply_modification_to_all_valid(
                kernel=self.kernel,
                mode=mode,
                point_a=point_a,
                point_b=point_b
            )
            # --- FIN LLAMADA ---

            if modified_td:
                message = f"Modo '{mode}' aplicado exitosamente a todos los trials válidos aplicables."
                # El evento 'trials_generated' emitido por la lógica
                # activará _on_data_updated, que llamará a _load_and_display_trials.
                QMessageBox.information(self.widget, "Éxito", message)
            else:
                 # La lógica devuelve None si no hubo cambios efectivos
                 QMessageBox.information(self.widget, "Sin Cambios",
                                         "No se realizaron modificaciones (quizás los puntos estaban fuera de rango o no afectaron trials válidos).")

        except ValueError as ve: # Capturar errores de conversión o validación
             QMessageBox.critical(self.widget, "Error de Parámetros", f"Valor inválido: {ve}")
        except RuntimeError as re: # Capturar errores de DataStore, señal no encontrada, etc.
             QMessageBox.critical(self.widget, "Error de Datos", f"No se pudo procesar: {re}")
        except Exception as e: # Capturar otros errores inesperados
             QMessageBox.critical(self.widget, "Error Inesperado", f"Ocurrió un error inesperado: {e}")
             print(f"{LOGP} Error inesperado en _on_apply_changes: {e}") # Log para debug


    # --- Lógica de Navegación y Carga de Datos ---

    def _go_to_previous_trial(self):
        """Navega al trial anterior o al promedio."""
        num_valid = len(self.valid_indices)
        if num_valid == 0: return # No hay nada que mostrar

        current_original_index = -1
        if self.current_display_index != -1: # Si estábamos viendo un trial individual
             current_original_index = self.valid_indices[self.current_display_index]

        if self.current_display_index == 0: # Si estábamos en el primer válido, ir al promedio
             self.current_display_index = -1
        elif self.current_display_index == -1: # Si estábamos en el promedio, ir al último válido
             self.current_display_index = num_valid - 1
        else: # Ir al anterior válido
             self.current_display_index -= 1

        print(f"{LOGP} Navegando a display_index: {self.current_display_index}")
        self._load_and_display_trials()

    def _go_to_next_trial(self):
        """Navega al siguiente trial o al promedio."""
        num_valid = len(self.valid_indices)
        if num_valid == 0: return

        current_original_index = -1
        if self.current_display_index != -1:
             current_original_index = self.valid_indices[self.current_display_index]

        if self.current_display_index == num_valid - 1: # Si estábamos en el último válido, ir al promedio
             self.current_display_index = -1
        elif self.current_display_index == -1: # Si estábamos en el promedio, ir al primer válido
             self.current_display_index = 0
        else: # Ir al siguiente válido
             self.current_display_index += 1

        print(f"{LOGP} Navegando a display_index: {self.current_display_index}")
        self._load_and_display_trials()


    # --- MODIFICADO: Lógica de carga y visualización ---
    def _load_and_display_trials(self):
        """Carga el TrialDataset actual, determina qué mostrar (promedio o individual) y lo plotea."""
        print(f"{LOGP} _load_and_display_trials() llamado.")
        if not self.kernel: return self._clear_render("Kernel no disponible.")
        store = self.kernel.get_service("DataStore")
        if not store: return self._clear_render("Error: DataStore no disponible.")

        active_signal = store.get_active_signal()
        if not isinstance(active_signal, SignalDataset):
            return self._clear_render("No hay señal activa cargada.")

        # Obtener el ÚLTIMO (más reciente) TrialDataset de la lista
        current_td: Optional[TrialDataset] = None
        if active_signal.trials_dataset:
            current_td = active_signal.trials_dataset[-1]
            # Obtener info de descarte y modificación actualizada
            file_name = Path(current_td.source).name if current_td.source else "unknown"
            discard_key = (file_name, current_td.channel_name)
            self.discarded_indices = active_signal.discarded_trials.get(discard_key, set())

            # Leer metadatos de modificación (asegurando que sea un set)
            mods_from_meta = current_td.metadata.get("modified_trials", set())
            if isinstance(mods_from_meta, set):
                 self.modified_indices = mods_from_meta
            else: # Intentar convertir si no es set
                 try: self.modified_indices = set(mods_from_meta)
                 except TypeError: self.modified_indices = set() # Fallback a set vacío

            self.total_original_trials = current_td.trials.shape[1]
            self.valid_indices = [i for i in range(self.total_original_trials) if i not in self.discarded_indices]
            print(f"{LOGP} Trials cargados: Total={self.total_original_trials}, Descartados={len(self.discarded_indices)}, Válidos={len(self.valid_indices)}, Modificados={len(self.modified_indices)}")
        else:
            self._reset_state() # Limpiar estado si no hay trials
            return self._clear_render("Fallo: No se encontraron datos de trials en la señal.")

        num_valid_indices = len(self.valid_indices)

        # Ajustar índice de display actual si está fuera de rango [ -1, num_valid_indices - 1 ]
        if not (-1 <= self.current_display_index < num_valid_indices):
            print(f"{LOGP} Índice {self.current_display_index} fuera de rango. Reseteando a promedio (-1).")
            self.current_display_index = -1 # Ir al promedio por defecto

        status_text, display_data, title = "", None, ""
        # Seleccionar solo las columnas válidas para el promedio
        # Usar iloc/fancy indexing es más seguro que boolean mask si hay NaNs inesperados
        valid_trial_columns = current_td.trials[:, self.valid_indices]

        # Determinar si el botón Apply debe estar activo
        # (Solo activo si estamos en modo promedio Y hay trials válidos)
        apply_enabled = (self.current_display_index == -1 and num_valid_indices > 0)
        if self.ui: self.ui.artifact_panel.apply_button.setEnabled(apply_enabled)


        if self.current_display_index == -1: # --- Mostrar Promedio ---
            if num_valid_indices == 0:
                 self._reset_state() # Limpiar estado si no hay válidos
                 return self._clear_render("Todos los trials están descartados. No se puede mostrar promedio.")

            # Calcular promedio ignorando NaNs (importante si hay cortes 'cut')
            # nanmean devuelve NaN si una columna entera es NaN, lo cual es correcto
            display_data = np.nanmean(valid_trial_columns, axis=1)
            title = f"Promedio de {num_valid_indices} Válidos - {current_td.channel_name}"
            status_text = f"Viendo Promedio / {num_valid_indices} Válidos ({self.total_original_trials} Totales)"

        else: # --- Mostrar Trial Individual ---
            try:
                # Obtener el índice ORIGINAL correspondiente al índice de display actual
                original_index = self.valid_indices[self.current_display_index]
                # Mostrar datos del trial actual (desde la matriz original/actual)
                display_data = current_td.trials[:, original_index]
                status_suffix = " (modificado)" if original_index in self.modified_indices else ""
                title = f"Trial Original {original_index + 1} - {current_td.channel_name}"
                # Mostrar índice relativo a los válidos + índice original
                status_text = (f"Viendo Válido {self.current_display_index + 1}/{num_valid_indices} "
                               f"(Orig. {original_index + 1}{status_suffix}) / {self.total_original_trials} Totales")
            except IndexError:
                 print(f"{LOGP} ERROR: IndexError al acceder a valid_indices[{self.current_display_index}]. Reseteando a promedio.")
                 self.current_display_index = -1
                 # Volver a llamar para mostrar el promedio
                 self._load_and_display_trials()
                 return
            except Exception as e:
                 print(f"{LOGP} ERROR inesperado al acceder a trial individual: {e}. Reseteando a promedio.")
                 self.current_display_index = -1
                 self._load_and_display_trials()
                 return


        # Actualizar etiqueta de estado en la UI
        if self.ui: self.ui.artifact_panel.trial_status_label.setText(status_text)

        # Plotear la curva (promedio o individual)
        # Asegurarse que VTK esté listo ANTES de plotear
        self._ensure_vtk()
        self._plot_curve(current_td.time_rel, display_data, title)


    # --- Lógica de Visualización VTK ---

    def _ensure_vtk(self):
        """Prepara el entorno de VTK si aún no está inicializado."""
        # Si ya existe, no hacer nada para evitar recreaciones innecesarias
        if self.vtk_view is not None and self.vtk_interactor is not None:
            # print(f"{LOGP} _ensure_vtk(): VTK ya existe.")
            # Asegurarse que el interactor esté en el layout correcto (por si acaso)
            layout = self.ui.plotArea.layout()
            if layout and layout.indexOf(self.vtk_interactor) == -1:
                 print(f"{LOGP} _ensure_vtk(): Re-añadiendo interactor al layout.")
                 layout.addWidget(self.vtk_interactor)
            return

        print(f"{LOGP} _ensure_vtk(): Configurando VTK por primera vez...")
        container = self.ui.plotArea

        # Asegurar que el contenedor tenga un layout
        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            container.setLayout(layout) # Establecer el layout en el contenedor

        # Crear e añadir el interactor Qt/VTK
        self.vtk_interactor = QVTKRenderWindowInteractor(container)
        layout.addWidget(self.vtk_interactor)

        # Crear la vista de contexto VTK
        self.vtk_view = vtk.vtkContextView()
        self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
        self.vtk_view.GetRenderer().SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))

        # Configurar interactor para coordenadas y zoom/pan
        # Dejar que vtkContextView use su estilo por defecto y añadir observador
        try:
             interactor = self.vtk_view.GetInteractor()
             if interactor:
                  # Remover observadores previos si existen (seguridad)
                  interactor.RemoveObservers(vtk.vtkCommand.MouseMoveEvent)
                  # Añadir observador para mostrar coordenadas
                  interactor.AddObserver(vtk.vtkCommand.MouseMoveEvent, self._on_mouse_move)
                  print(f"{LOGP} Observador 'MouseMoveEvent' añadido al interactor por defecto.")
             else:
                  print(f"{LOGP} Advertencia: No se pudo obtener interactor de vtk_view.")
        except Exception as e:
             print(f"{LOGP} Error configurando observador MouseMove: {e}")

        # Inicializar el widget Qt/VTK
        try:
             # Necesario para que el render funcione correctamente
             self.vtk_interactor.Initialize()
             # Render inicial opcional
             self.vtk_interactor.Start()
             print(f"{LOGP} Interactor VTK inicializado y arrancado.")
        except Exception as e:
             print(f"{LOGP} Error inicializando/arrancando interactor VTK: {e}")


    def _on_mouse_move(self, interactor, event):
        """Muestra las coordenadas del ratón en la barra de estado."""
        # Añadir chequeos de seguridad
        if not self.chart or not self.mainwin or not self.vtk_view or not interactor: return
        pos = interactor.GetEventPosition()
        coords = vtk.vtkVector2f()
        try:
            # Intentar obtener transformación del plot actual
            # Puede fallar si no hay plots o durante transiciones
            plot_item = self.chart.GetPlot(0) # Asumir que usamos el plot 0
            transform = plot_item.GetTransform() if plot_item else None

            # Usar la transformación de los ejes como fallback si la del plot falla
            if not transform:
                 transform = self.chart.GetPlotTransform() # Transformación general de ejes

            if transform:
                 # Invertir transformación para obtener coordenadas de datos
                 inverse_transform = transform.GetInverse()
                 if inverse_transform:
                      inverse_transform.TransformPoint(pos, coords)
                      message = f"Tiempo: {coords[0]:.4f} s, Amplitud: {coords[1]:.6f}"
                      # Usar statusBar() directamente si mainwin es QMainWindow
                      if hasattr(self.mainwin, 'statusBar'):
                           self.mainwin.statusBar().showMessage(message)
                      else: # Fallback si mainwin no es QMainWindow (raro)
                           print(message)
                 #else: print(f"{LOGP} No se pudo obtener inversa de la transformación.")
            #else: print(f"{LOGP} No se pudo obtener transformación del chart.")
        except Exception as e:
             # Silenciar errores comunes durante redraws o si no hay datos
             # print(f"{LOGP} Error en _on_mouse_move: {e}")
             pass

    def _plot_curve(self, t: np.ndarray, y: np.ndarray, title: str = ""):
        """Dibuja una única curva (promedio o trial) en el chart VTK."""
        # Asegurar que VTK esté listo
        self._ensure_vtk()
        if not self.vtk_view or not self.vtk_interactor:
             print(f"{LOGP} Error: VTK no está listo para plotear.")
             return self._clear_render("Error interno de VTK.")

        # Limpiar la escena anterior
        scene = self.vtk_view.GetScene()
        scene.ClearItems()
        # Restaurar fondo por si _clear_render lo cambió
        self.vtk_view.GetRenderer().SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))

        # Crear tabla VTK para los datos
        table = vtk.vtkTable()
        arr_t = vtk.vtkFloatArray(); arr_t.SetName("Time (s)")
        arr_y = vtk.vtkFloatArray(); arr_y.SetName("Amplitude")
        table.AddColumn(arr_t); table.AddColumn(arr_y)

        # Filtrar NaNs para evitar problemas en VTK
        # (Aunque nanmean ya los maneja, el plot individual puede tenerlos)
        valid_mask = ~np.isnan(y) if y is not None else np.array([False])
        if np.any(valid_mask):
             t_valid, y_valid = t[valid_mask], y[valid_mask]
             n_points = len(t_valid)
             table.SetNumberOfRows(n_points)
             # Llenar tabla (más eficiente con SetVoidArray si es posible, pero esto es más simple)
             for i in range(n_points):
                  table.SetValue(i, 0, t_valid[i])
                  table.SetValue(i, 1, y_valid[i])
        else: # Si todos son NaN o y es None
             print(f"{LOGP} No hay datos válidos para plotear.")
             table.SetNumberOfRows(0)
             # Podríamos mostrar un mensaje aquí usando _clear_render
             # return self._clear_render("No hay datos válidos en este trial/promedio.")


        # Crear el chart y añadirlo a la escena
        self.chart = vtk.vtkChartXY()
        scene.AddItem(self.chart)

        # Añadir el plot de línea
        plot = self.chart.AddPlot(vtk.vtkChart.LINE)
        plot.SetInputData(table, "Time (s)", "Amplitude") # Usar nombres de columna
        plot.SetWidth(1.5)
        # Cambiar color según si es promedio o individual
        color_name = "Crimson" if self.current_display_index == -1 else "SteelBlue"
        plot.GetPen().SetColor(vtk.vtkNamedColors().GetColor4ub(color_name))

        # Configurar título y ejes
        self.chart.SetTitle(title)
        axis_bottom = self.chart.GetAxis(vtk.vtkAxis.BOTTOM); axis_bottom.SetTitle("Tiempo (s)")
        axis_left = self.chart.GetAxis(vtk.vtkAxis.LEFT); axis_left.SetTitle("Amplitud")
        # Habilitar rejilla
        axis_bottom.SetGridVisible(True); axis_left.SetGridVisible(True)

        # Añadir menú contextual si está disponible
        if VTXContextMenu and self.vtk_interactor and self.chart:
             try:
                 # Remover menú anterior si existe
                 if hasattr(self, 'vtk_menu') and self.vtk_menu:
                      # self.vtk_menu.destroy() # ¿Necesario? Chequear API
                      pass
                 self.vtk_menu = VTXContextMenu(self.chart, self.vtk_interactor, parent=self.widget)
                 # Acción básica para resetear vista
                 self.vtk_menu.add_action("Reset Zoom", self.chart.RecalculateBounds)
                 # Podrías añadir más acciones aquí
             except Exception as e:
                  print(f"{LOGP} Error creando menú contextual VTK: {e}")

        # Forzar el renderizado de la ventana VTK
        try:
             # Recalcular límites antes de renderizar
             self.chart.RecalculateBounds()
             self.vtk_view.GetRenderWindow().Render()
             # print(f"{LOGP} Renderizado completado.")
        except Exception as e:
             print(f"{LOGP} Error durante el renderizado VTK: {e}")

    # --- Funciones de utilidad ---
    def _reset_state(self):
        """Resetea el estado interno del plugin."""
        print(f"{LOGP} Reseteando estado...")
        self.current_display_index = -1
        self.valid_indices = []
        self.total_original_trials = 0
        self.discarded_indices = set()
        self.modified_indices = set()
        # Opcional: Limpiar campos de texto A y B en la UI
        # if self.ui:
        #      self.ui.artifact_panel.point_a.setText("0.0")
        #      self.ui.artifact_panel.point_b.setText("0.0")

    def _find_active_trials_dataset(self) -> Optional[TrialDataset]:
        """Encuentra el TrialDataset más reciente para la señal y canal activos."""
        # Esta función parece redundante si _load_and_display_trials ya obtiene el último
        # Podría simplificarse o eliminarse si no se usa en otro lugar.
        if not self.kernel: return None
        store = self.kernel.get_service("DataStore")
        if not store: return None
        active_signal = store.get_active_signal()
        # Asegurarse que trials_dataset no esté vacío
        if isinstance(active_signal, SignalDataset) and active_signal.trials_dataset:
            # Devolver el último (más reciente)
            return active_signal.trials_dataset[-1]
        return None

    def _clear_render(self, message=""):
        """Limpia la ventana VTK y opcionalmente muestra un mensaje."""
        print(f"{LOGP} Limpiando render. Mensaje: '{message}'")
        # Asegurar que VTK esté listo
        self._ensure_vtk()
        if not self.vtk_view or not self.vtk_interactor:
             print(f"{LOGP} Error: No se puede limpiar render, VTK no está listo.")
             return

        scene = self.vtk_view.GetScene()
        scene.ClearItems() # Limpiar plots, etc.
        # Limpiar actores 2D (como mensajes previos)
        renderer = self.vtk_view.GetRenderer()
        renderer.RemoveAllViewProps() # Esto quita actores 2D y 3D

        # Poner fondo oscuro para indicar estado vacío/error
        renderer.SetBackground(0.1, 0.1, 0.15)

        if message: # Añadir nuevo mensaje si se proporcionó
            text_actor = vtk.vtkTextActor()
            text_actor.SetInput(message)
            prop = text_actor.GetTextProperty()
            prop.SetColor(0.9, 0.9, 0.9) # Color claro
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToCentered()
            prop.SetFontSize(16)
            # Centrar el actor en la ventana
            text_actor.SetPosition(renderer.GetSize()[0]/2, renderer.GetSize()[1]/2)
            renderer.AddActor2D(text_actor)

        # Renderizar el estado limpio
        try:
             self.vtk_view.GetRenderWindow().Render()
        except Exception as e:
             print(f"{LOGP} Error renderizando estado limpio: {e}")


    def _on_data_updated(self, topic: str, payload: object):
        """Se ejecuta cuando el DataStore emite un evento."""
        # Eventos que indican un cambio en los trials o la señal activa
        if topic in ["signal_added", "active_signal_changed", "trials_generated", "trial_discard_updated"]:
            # Solo actualizar si el widget de este plugin es visible
            if self.widget and self.widget.isVisible():
                print(f"{LOGP} Evento '{topic}' recibido mientras visible. Reseteando y actualizando vista...")
                # Resetear el índice y estado interno
                self._reset_state()
                # Habilitar interactor por si acaso
                if self.vtk_interactor: self.vtk_interactor.Enable()
                # Recargar y mostrar (probablemente el promedio ahora)
                self._load_and_display_trials()
            #else:
            #    print(f"{LOGP} Evento '{topic}' recibido mientras NO visible. Ignorando.")

# --- FIN DEL ARCHIVO ---
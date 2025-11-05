from collections import defaultdict
import os
from PyQt5.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QWidget, QToolButton, QGroupBox, QLabel, QSizePolicy, QApplication
from app.view.main_window_ui import Ui_MainWindow 
from PyQt5.QtGui import QIcon, QFontMetrics, QFont
from PyQt5.QtCore import QSize, Qt, QPropertyAnimation, QEasingCurve

from core.plugins.interfaces import IPlugin
from core.plugins.plugin_alerts import PluginAlerts

class MainWindow(QMainWindow):
    def __init__(self, kernel):
        super().__init__()
        self.kernel = kernel

        #Registrar la ventana principal como un servicio en el kernel para que los plugins puedan acceder a ella.
        self.kernel.register_service("MainWindow", self)

        self.setWindowIcon(QIcon("assets/logos/app-logo.png"))
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.showMaximized()
        
        self.alerts = PluginAlerts()
        self.alerts.parent = self

        self.kernel.event.connect(self.on_kernel_event)

        self.current_section = "Home"
        self.active_plugin = None #Plugin activo actualmente
        self.active_plugin_widget = None #Widget del plugin activo
        self.plugin_widgets = {} #Almacenamiento de los widgets de los plugins para no perder trabajo

        #area de trabajo
        self.plugin_area = self.ui.workspace

        # Inicializar funcionalidades de la barra lateral
        self.setup_sidebar_functionality()

        if not self.plugin_area.layout():
            self.plugin_layout = QVBoxLayout(self.plugin_area)
            self.plugin_layout.setContentsMargins(0,0,0,0)
        else:
            self.plugin_layout = self.plugin_area.layout()

        # Diccionario de secciones
        self.section_buttons = {
            "Home": self.ui.bnt_home,
            "Preprocessing": self.ui.btn_preprocessing,
            "Analysis": self.ui.btn_analysis,
            "Measure": self.ui.btn_measure,
            "FAQ": self.ui.btn_faq,
        }

        for section, btn in self.section_buttons.items():
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, s=section: self.switch_section(s))

        # Mostrar por defecto plugins de Home
        self.switch_section(self.current_section)
        
        self._app_quitting = False
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._on_app_about_to_quit)


    '''buttons section'''
    # Actualizar plugins al registrar uno nuevo
    def on_plugin_registered(self, name):
        plugin = self.kernel.get_plugin(name)
        if plugin and plugin.category() == self.current_section:
            
            self.add_plugin_button(name)

    # Cambiar de sección
    def switch_section(self, section):
        self.current_section = section
        self.setWindowTitle(f"Gamma Lab - {self.current_section}")

        # Toggle del botón de sección
        for btn in self.section_buttons.values():
            btn.setChecked(False)
        if section in self.section_buttons:
            self.section_buttons[section].setChecked(True)

        # Layout del contenedor azul
        contenedor = self.ui.buttonContainer.layout()
        while contenedor.count():
            item = contenedor.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Alinear a la izquierda y sin espacios externos
        contenedor.setContentsMargins(0, 0, 0, 0)
        contenedor.setSpacing(8)
        contenedor.setAlignment(Qt.AlignLeft)

        # Agrupar plugins por subcategoría
        subcategories = defaultdict(list)
        for name in self.kernel.get_plugins_by_category(section):
            plugin = self.kernel.get_plugin(name)
            subcategories[plugin.subcategory()].append(name)

        # Construir cada subcategoría y poner divider entre ellas
        subcats = list(subcategories.items())
        for idx, (subcat, plugins) in enumerate(subcats):
            group_box = QGroupBox(subcat, self.ui.buttonContainer)
            group_box.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            row = QHBoxLayout(group_box)
            row.setContentsMargins(0, 6, 0, 22)
            row.setSpacing(34)

            for name in plugins:
                row.addWidget(self.add_plugin_button(name))

            contenedor.addWidget(group_box, 0, Qt.AlignVCenter)

        # Empujar todo a la izquierda
        contenedor.addStretch(1)
        
    def add_plugin_button(self, name):
        plugin = self.kernel.get_plugin(name)
        btn = QToolButton(self.ui.buttonContainer)
        btn.setObjectName(f"btn_{name}")
        btn.setCheckable(False)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        # Slot fijo (coherente con QSS)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setMinimumWidth(96); btn.setMaximumWidth(96)
        btn.setMinimumHeight(76)

        # Icono
        try:
            icon_path = plugin.icon()
            if icon_path:
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(26, 26))
        except Exception as e:
            print("Icono no disponible para plugin", name, "->", e)

        label = plugin.name()
        fm_width = 96 - 8
        btn.setText(self._wrap_button_text(label, btn.font(), fm_width))

        btn.clicked.connect(lambda _, n=name: self.on_button_click(n))
        return btn

    def _wrap_button_text(self, text: str, font: QFont, max_width: int) -> str:
        """
        Inserta un salto de línea óptimo para que el texto quepa en 1–2 líneas
        dentro de 'max_width'. Si ya cabe en una línea, lo deja igual.
        """
        fm = QFontMetrics(font)
        if fm.horizontalAdvance(text) <= max_width:
            return text

        # Intentar partir en el último espacio que deje primera línea <= max_width
        words = text.split()
        if len(words) == 1:
            # Sin espacios; corta “a mano” en ~caracteres que quepan
            for i in range(len(text)-1, 0, -1):
                if fm.horizontalAdvance(text[:i]) <= max_width:
                    return text[:i] + "\n" + text[i:]
            return text  # fallback
        else:
            # Construir línea 1 con el mayor número de palabras que quepan
            line1 = words[0]
            for w in words[1:]:
                candidate = f"{line1} {w}"
                if fm.horizontalAdvance(candidate) <= max_width:
                    line1 = candidate
                else:
                    # resto pasa a segunda línea
                    line2 = " ".join(words[len(line1.split()):])
                    # si la segunda aún es muy larga, no pasa nada: el alto del botón lo soporta
                    return line1 + "\n" + line2
            # si entraron todas, ya no hace falta segunda línea
            return line1

    # Clean workspace
    def clear_plugin_area(self):
        if self.active_plugin_widget and self.active_plugin:
            try:
                self.active_plugin.stop()
            except Exception as e:
                self.alerts.warning(f"An error occurred while stopping the VTK render plugin.\n\nDetails:\n{str(e)}", "Error stopping plugin")
            self.active_plugin_widget.setVisible(False)

        self.active_plugin_widget = None
        self.active_plugin = None


    # Intertar el widget de un plugin activo en el espacio de trabajo
    def show_plugin_widget(self, plugin: IPlugin):
        try:
            plugin.process(None)
        except Exception as e:
            print("Error al reanudar plugin:", e)
        
        if plugin is None:
            return

        # Iniciar plugin si aún no fue iniciado
        if not getattr(plugin, "started", False):
            try:
                plugin.start(self.kernel)
                plugin.started = True
            except Exception as e:
                print("Error iniciando plugin:", e)

        # Reutilizar si ya existe
        if plugin.name() in self.plugin_widgets:
            widget = self.plugin_widgets[plugin.name()]
        else:
            # Obtener widget desde plugin
            try:
                widget = plugin.get_widget(parent=self.plugin_area)
            except Exception as e:
                self.alerts.error(f"An error occurred while rendering the plugin widget '{plugin.name()}'.\n\nDetails:\n{str(e)}", "Error rendering plugin")
                print("[Main Window] Error en get_widget del plugin:", e)
                widget = None

            # Si no retorna widget, crear placeholder
            if widget is None:
                self.alerts.error(f"No hay interfaz para el plugin '{plugin.name()}'.", "Error rendering plugin")


                placeholder = QWidget(parent=self.plugin_area)
                layout = QVBoxLayout(placeholder)
                layout.addWidget(QLabel(f"No hay interfaz para {plugin.name()}"))
                widget = placeholder

            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.plugin_layout.addWidget(widget)
            self.plugin_widgets[plugin.name()] = widget

        # Ocultar anterior y mostrar el nuevo
        self.clear_plugin_area()
        widget.setVisible(True)
        self.active_plugin_widget = widget
        self.active_plugin = plugin

        # Notificar que se muestra
        if hasattr(plugin, "on_show"):
            try:
                plugin.on_show()
            except Exception as e:
                print("Error en on_show del plugin:", e)

               
    # Evento al presionar un botón de plugin: mostrar su interfaz y opcionalmente procesar
    def on_button_click(self, name):
        plugin = self.kernel.get_plugin(name)
        if plugin:
            print(f"Se hizo clic en plugin {name}")
            self.show_plugin_widget(plugin)
            if hasattr(plugin, "process"):
                try:
                    plugin.process("Ventana abierta")
                except Exception as e:
                    print("Error en process del plugin:", e)
        else:
            print("Plugin no encontrado:", name)



    '''Barra lateral'''

    def on_kernel_event(self, topic: str, payload: object):
        """
        Escucha eventos emitidos por el Kernel.
        """
        if topic == "signal_added":
            print(f"Nueva señal añadida: {payload}")
            self.update_signal_list()

    def setup_sidebar_functionality(self):
        sidebar = self.ui.widget_3
        sidebar.setMaximumWidth(250)
        """Inicializa y conecta todas las funciones de la barra lateral."""
        # Collapse de la barra lateral
        self.ui.collapse_explorer_btn.clicked.connect(lambda: self.toggle_sidebar_collapse(sidebar))
        self.ui.collapse_explorer_btn.setIcon(QIcon("assets/icons/home/icn_collapse.png"))

        self.update_signal_list()
        # Selección de señal
        self.ui.selected_signal_comboBox.currentIndexChanged.connect(self.on_signal_selected)

        # Secciones futuras
        self.setup_explorer_section()
        self.setup_calculus_section()
        self.setup_results_section()

    # Comprimir y expandir la barra lateral
    def toggle_sidebar_collapse(self, sidebar):
        
        current_width = sidebar.width()

        if current_width > 0:
            self._last_sidebar_width = current_width

            # Permitir colapso total
            sidebar.setMinimumWidth(0)

            # Animación de colapso
            self._sidebar_animation = QPropertyAnimation(sidebar, b"maximumWidth")
            self._sidebar_animation.setDuration(250)
            self._sidebar_animation.setStartValue(current_width)
            self._sidebar_animation.setEndValue(0)
            self._sidebar_animation.setEasingCurve(QEasingCurve.InOutCubic)
            self._sidebar_animation.start()

            self.ui.collapse_explorer_btn.setIcon(QIcon("assets/icons/home/icn_expand.png"))

        else:
            width = getattr(self, "_last_sidebar_width", 250)

            # Restaurar ancho y límite mínimo
            sidebar.setMinimumWidth(100)

            # Animación de expansión
            self._sidebar_animation = QPropertyAnimation(sidebar, b"maximumWidth")
            self._sidebar_animation.setDuration(250)
            self._sidebar_animation.setStartValue(0)
            self._sidebar_animation.setEndValue(width)
            self._sidebar_animation.setEasingCurve(QEasingCurve.InOutCubic)
            self._sidebar_animation.start()

            self.ui.collapse_explorer_btn.setIcon(QIcon("assets/icons/home/icn_collapse.png"))


    def on_signal_selected(self):
        """
        Se ejecuta cuando el usuario cambia la señal seleccionada en el comboBox.
        Actualiza la señal activa en el DataStore.
        """
        datastore = self.kernel.get_service("DataStore")
        if not datastore:
            print("⚠️ No se encontró el servicio DataStore.")
            return

        selected_key = self.ui.selected_signal_comboBox.currentText()
        if not selected_key:
            print("No hay señal seleccionada.")
            return

        try:
            datastore.set_active_signal(selected_key)
            self.kernel.emit_event("signal_active_changed", {"key": selected_key})

            print(f"[Main Window] Señal activa cambiada a: {selected_key}")
        except ValueError as e:
            print(f"[Main Window] Error al cambiar señal activa: {e}")


    def update_signal_list(self):
        """Maneja la selección de una señal del comboBox."""

        datastore = self.kernel.get_service("DataStore")
        if not datastore:
            print("No se encontró el servicio DataStore.")
            return
        
        signals = datastore.get_signals()
        active_signal_key = datastore.get_active_signal_key()

        #limpiar combo
        self.ui.selected_signal_comboBox.blockSignals(True)
        self.ui.selected_signal_comboBox.clear()

        for key in signals.keys():
            self.ui.selected_signal_comboBox.addItem(key)

        # Seleccionar la señal activa si hay
        if active_signal_key and active_signal_key in signals:
            index = self.ui.selected_signal_comboBox.findText(active_signal_key)
            if index >= 0:
                self.ui.selected_signal_comboBox.setCurrentIndex(index)

        self.ui.selected_signal_comboBox.blockSignals(False)



        # selected_signal = self.ui.selected_signal_comboBox.currentText()
        # if selected_signal:
        #     print(f"Señal seleccionada: {selected_signal}")
        #     # Aquí podrías notificar al kernel o cargar la señal seleccionada
        # else:
        #     print("No hay señal seleccionada.")
        pass


    # === FUNCIONES FUTURAS (placeholder con pass) ===
    def setup_explorer_section(self):
        """Inicializa la sección de explorador (por ahora vacía)."""
        pass

    def setup_calculus_section(self):
        """Inicializa la sección de cálculos (por ahora vacía)."""
        pass

    def setup_results_section(self):
        """Inicializa la sección de resultados (por ahora vacía)."""
        pass
    
    def _on_app_about_to_quit(self):
        """Apaga plugins y su UI de forma segura. Idempotente."""
        if self._app_quitting:
            return
        self._app_quitting = True

        # 1) Detén el plugin activo, si lo hay
        try:
            if self.active_plugin and hasattr(self.active_plugin, "stop"):
                self.active_plugin.stop()
        except Exception as e:
            print("stop(active_plugin) error:", e)

        # 2) Detén el resto (si tu kernel expone una forma de listarlos)
        try:
            # Opción A: si tienes un método para listarlos todos
            if hasattr(self.kernel, "get_all_plugins"):
                for name in self.kernel.get_all_plugins():
                    p = self.kernel.get_plugin(name)
                    if p is not None and hasattr(p, "stop"):
                        try: p.stop()
                        except Exception as e: print(f"stop({name}) error:", e)
            else:
                # Opción B: usa los que están instanciados en la UI
                for name in list(self.plugin_widgets.keys()):
                    p = self.kernel.get_plugin(name)
                    if p is not None and hasattr(p, "stop"):
                        try: p.stop()
                        except Exception as e: print(f"stop({name}) error:", e)
        except Exception as e:
            print("stop(all) error:", e)

        # 3) Oculta widgets y limpia referencias (evita renders tardíos)
        try:
            for name, w in list(self.plugin_widgets.items()):
                if w is not None:
                    w.setVisible(False)
            self.plugin_widgets.clear()
            self.active_plugin_widget = None
            self.active_plugin = None
        except Exception as e:
            print("cleanup widgets error:", e)

    def closeEvent(self, event):
        self._on_app_about_to_quit()
        super().closeEvent(event)
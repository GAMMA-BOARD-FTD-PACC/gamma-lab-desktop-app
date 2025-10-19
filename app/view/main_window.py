from collections import defaultdict
import os
from PyQt5.QtWidgets import QMainWindow, QMessageBox, QHBoxLayout, QVBoxLayout, QWidget, QToolButton, QGroupBox, QLabel, QSizePolicy
from app.view.ventana_principal_ui import Ui_MainWindow 
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import QSize, Qt, QPropertyAnimation, QEasingCurve

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
            "Visualization": self.ui.btn_visualization,
            "Utilities": self.ui.btn_utilities,
            "FAQ": self.ui.btn_faq,
        }

        for section, btn in self.section_buttons.items():
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, s=section: self.switch_section(s))

        # Mostrar por defecto plugins de Home
        self.switch_section(self.current_section)


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

        
        # Desmarcar los botones y marcar el de la sección actual
        for btn in self.section_buttons.values():
            btn.setChecked(False)
        if section in self.section_buttons:
            self.section_buttons[section].setChecked(True)


        contenedor_botones = self.ui.buttonContainer.layout()
        subcategories = defaultdict(list)

        # Limpiar botones existentes
        while contenedor_botones.count():
            item = contenedor_botones.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        


        # Agregar solo los plugins de la sección actual
        for name in self.kernel.get_plugins_by_category(section):
            plugin = self.kernel.get_plugin(name)
            subcategory = plugin.subcategory()
            subcategories[subcategory].append(name)

            self.add_plugin_button(name)
        
        # Crear secciones visuales por subcategoría
        for subcat, plugins in subcategories.items():
            group_box = QGroupBox(subcat)
            group_box.setAlignment(Qt.AlignHCenter | Qt.AlignTop)  # nombre centrado arriba
            group_layout = QHBoxLayout(group_box)
            group_layout.setContentsMargins(0, 0, 0, 0)  # sin márgenes internos

            for name in plugins:
                btn = self.add_plugin_button(name)
                group_layout.addWidget(btn)

            contenedor_botones.addWidget(group_box)


    #Agregar un botón de plugin cuando hay el evento de agregar uno nuevo.
    def add_plugin_button(self, name):
        plugin = self.kernel.get_plugin(name)
        btn = QToolButton()
        btn.setText(plugin.name())
        btn.setObjectName(f"btn_{name}")

        try:
            icon_path = plugin.icon()
            if icon_path:
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(48, 48))
                btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        except Exception as e:
            print("Icono no disponible para plugin", name, "->", e)

        btn.clicked.connect(lambda _, n=name: self.on_button_click(n))
        return btn
    '''workspace area'''

    # Clean workspace
    def clear_plugin_area(self):
        if self.active_plugin_widget and self.active_plugin:
            try:
                self.active_plugin.stop()
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error al detener el plugin",
                    f"Ocurrió un error al detener el VTK render del plugin .\n\nDetalles:\n{str(e)}"
                )
            self.active_plugin_widget.setVisible(False)

        self.active_plugin_widget = None
        self.active_plugin = None


    # Intertar el widget de un plugin activo en el espacio de trabajo
    def show_plugin_widget(self, plugin):
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
                QMessageBox.critical(
                    self,
                    "Error al renderizar el plugin",
                    f"Ocurrió un error al renderizar el widget del plugin '{plugin.name()}'.\n\nDetalles:\n{str(e)}"
                )
                print("[Main Window] Error en get_widget del plugin:", e)
                widget = None

            # Si no retorna widget, crear placeholder
            if widget is None:
                QMessageBox.critical(
                    self,
                    "Error al renderizar el plugin",
                    f"No hay interfaz para el plugin '{plugin.name()}'."
                )


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

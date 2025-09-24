from PyQt5.QtWidgets import QMainWindow, QHBoxLayout, QVBoxLayout, QWidget, QToolButton, QPushButton, QLabel, QSizePolicy
from view.ventana_principal_ui import Ui_MainWindow 
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSize, Qt



class MainWindow(QMainWindow):
    def __init__(self, kernel):
        super().__init__()
        self.kernel = kernel

        #Registrar la ventana principal como un servicio en el kernel para que los plugins puedan acceder a ella.
        self.kernel.register_service("MainWindow", self)


        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.showMaximized()

        self.current_section = "Home"
        self.active_plugin = None #Plugin activo actualmente
        self.active_plugin_widget = None #Widget del plugin activo
        self.plugin_widgets = {} #Almacenamiento de los widgets de los plugins para no perder trabajo

        #area de trabajo
        self.plugin_area = self.ui.workspace

        if not self.plugin_area.layout():
            self.plugin_layout = QVBoxLayout(self.plugin_area)
            self.plugin_layout.setContentsMargins(6, 6, 6, 6)
        else:
            self.plugin_layout = self.plugin_area.layout()

        # Conectar botones de sección
        self.ui.bnt_home.clicked.connect(lambda: self.switch_section("Home"))
        self.ui.btn_preprocessing.clicked.connect(lambda: self.switch_section("Preprocessing"))
        self.ui.btn_analysis.clicked.connect(lambda: self.switch_section("Analysis"))
        self.ui.btn_measure.clicked.connect(lambda: self.switch_section("Measure"))
        self.ui.btn_visualization.clicked.connect(lambda: self.switch_section("Visualization"))
        self.ui.btn_utilities.clicked.connect(lambda: self.switch_section("Utilities"))
        self.ui.btn_faq.clicked.connect(lambda: self.switch_section("FAQ"))

        # Mostrar por defecto plugins de Home
        self.switch_section(self.current_section)


    # Actualizar plugins al registrar uno nuevo
    def on_plugin_registered(self, name):
        plugin = self.kernel.get_plugin(name)
        if plugin and plugin.category() == self.current_section:
            self.add_plugin_button(name)

    # Cambiar de sección
    def switch_section(self, section):
        self.current_section = section
        contenedor_botones = self.ui.buttonContainer.layout()

        # Limpiar botones existentes
        while contenedor_botones.count():
            item = contenedor_botones.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Agregar solo los plugins de la sección actual
        for name in self.kernel.get_plugins_by_category(section):
            self.add_plugin_button(name)


    #Agregar un botón de plugin cuando hay el evento de agregar uno nuevo.
    def add_plugin_button(self, name):
        contenedor_botones = self.ui.buttonContainer.layout()
        plugin = self.kernel.get_plugin(name)
        btn = QToolButton()
        btn.setText(plugin.name())
        btn.setObjectName(f"btn_{name}")

        #Si tiene ícono agregarlo
        if plugin and hasattr(plugin, "icon"):
            icon_path = plugin.icon()
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(48, 48))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        btn.clicked.connect(lambda _, n=name: self.on_button_click(n))
        contenedor_botones.addWidget(btn)


    # Limpia el área de plugin y notifica al plugin anterior
    def clear_plugin_area(self):
        # notificar hide del plugin anterior
        if self.active_plugin and hasattr(self.active_plugin, "on_hide"):
            try:
                self.active_plugin.on_hide()
            except Exception as e:
                print("Error en on_hide del plugin:", e)

        if self.active_plugin_widget:
            self.active_plugin_widget.setVisible(False)

        self.active_plugin_widget = None
        self.active_plugin = None


    # Insertar la interfaz del plugin en el area de trabajo
    def show_plugin_widget(self, plugin):
        if plugin is None:
            return

        # llamar start si existe y si no fue iniciado (opcional: plugin puede manejar repetidas llamadas)
        try:
            if hasattr(plugin, "start") and not getattr(plugin, "started", False):
                plugin.start(self.kernel)
                plugin.started = True
        except Exception as e:
            print("Error iniciando plugin:", e)

        
        # si ya existe el widget, reutilizarlo
        if plugin.name() in self.plugin_widgets:
            widget = self.plugin_widgets[plugin.name()]
        else:
            # crear widget solo una vez
            widget = plugin.get_widget(parent=self.plugin_area) if hasattr(plugin, "get_widget") else None

            if widget is None:
                placeholder = QWidget(parent=self.plugin_area)
                placeholder_layout = QVBoxLayout(placeholder)
                lbl = QLabel(f"No hay interfaz para {plugin.name()}")
                placeholder_layout.addWidget(lbl)
                widget = placeholder

            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.plugin_layout.addWidget(widget)
            self.plugin_widgets[plugin.name()] = widget

        # ocultar plugin anterior y mostrar el nuevo
        self.clear_plugin_area()
        widget.setVisible(True)
        self.active_plugin_widget = widget
        self.active_plugin = plugin

        # notificar plugin que se muestra
        if hasattr(plugin, "on_show"):
            try:
                plugin.on_show()
            except Exception as e:
                print("Error en on_show del plugin:", e)


            # obtener widget desde plugin (contrato get_widget)
            widget = None
            if hasattr(plugin, "get_widget"):
                try:
                    widget = plugin.get_widget(parent=self.plugin_area)
                except Exception as e:
                    print("Error obteniendo widget del plugin:", e)
                    widget = None

        # si no hay widget, crear placeholder
        if widget is None:
            placeholder = QWidget(parent=self.plugin_area)
            placeholder_layout = QVBoxLayout(placeholder)
            lbl = QLabel(f"No hay interfaz para {plugin.name()}")
            placeholder_layout.addWidget(lbl)
            widget = placeholder

               
    # Evento al presionar un botón de plugin: mostrar su interfaz y opcionalmente procesar
    def on_button_click(self, name):
        plugin = self.kernel.get_plugin(name)
        if plugin:
            print(f"Se hizo clic en plugin {name}")
            self.show_plugin_widget(plugin)
            if hasattr(plugin, "process"):
                try:
                    plugin.process("Hola desde MainWindow")
                except Exception as e:
                    print("Error en process del plugin:", e)
        else:
            print("Plugin no encontrado:", name)

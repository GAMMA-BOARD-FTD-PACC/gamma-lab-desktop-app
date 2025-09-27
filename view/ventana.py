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

    '''buttons section'''
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

    '''workspace area'''

    # Clean workspace
    def clear_plugin_area(self):
        if self.active_plugin_widget:
            self.active_plugin_widget.setVisible(False)

        self.active_plugin_widget = None
        self.active_plugin = None


    # Intertar el widget de un plugin activo en el espacio de trabajo
    def show_plugin_widget(self, plugin):
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
                print("Error en get_widget del plugin:", e)
                widget = None

            # Si no retorna widget, crear placeholder
            if widget is None:
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
                    plugin.process("Hola desde MainWindow")
                except Exception as e:
                    print("Error en process del plugin:", e)
        else:
            print("Plugin no encontrado:", name)

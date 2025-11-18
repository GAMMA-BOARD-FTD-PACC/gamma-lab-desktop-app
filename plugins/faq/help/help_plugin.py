from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from PyQt5.QtWidgets import QWidget, QVBoxLayout
import webbrowser

from plugins.faq.help.help_ui import Ui_FAQ



class HelpPlugin(IPlugin):

    def __init__(self, meta:PluginMeta):
        super().__init__(meta)
        self.ui = None

    def stop(self):
        """Invoked when the kernel stops plugins."""
        pass

    def get_widget(self, parent=None):
        """Return the widget associated with the plugin."""
        pass

    def process(self, data: any):
        """Process data sent by the kernel or other plugins."""
        pass



    def get_widget(self, parent=None):
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_FAQ()
            self.ui.setupUi(self.widget)

            self.init_buttons()
        else:
            self.widget.setParent(parent)

        return self.widget
    
    
    def init_buttons(self):
        # Official repo
        self.ui.repoButton.clicked.connect(
            lambda: webbrowser.open("https://github.com/GAMMA-BOARD-FTD-PACC/gamma-lab-desktop-app")
        )

        # Documentation
        self.ui.docsButton.clicked.connect(
            lambda: webbrowser.open("https://github.com/GAMMA-BOARD-FTD-PACC/gamma-lab-desktop-app")
        )

        # Tutorial videos
        self.ui.videosButton.clicked.connect(
            lambda: webbrowser.open("https://github.com/GAMMA-BOARD-FTD-PACC/gamma-lab-desktop-app")
        )

        # Releases / Downloads
        self.ui.downloadButton.clicked.connect(
            lambda: webbrowser.open("https://github.com/GAMMA-BOARD-FTD-PACC/gamma-lab-desktop-app")
        )
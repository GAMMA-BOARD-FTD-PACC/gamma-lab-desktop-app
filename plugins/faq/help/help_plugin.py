from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from PyQt5.QtWidgets import QWidget, QVBoxLayout
import webbrowser
import os
from PyQt5.QtCore import QUrl


from plugins.faq.help.help_ui import Ui_FAQ



class HelpPlugin(IPlugin):

    def __init__(self, meta:PluginMeta):
        super().__init__(meta)
        self.ui = None
        self.widget = None 

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

            # Ruta absoluta del PDF
            pdf_path = os.path.join(os.path.dirname(__file__), "MU_GAMMA_LAB.pdf")
            self.load_pdf(pdf_path)
        else:
            self.widget.setParent(parent)
        return self.widget

    def load_pdf(self, pdf_path=None):
        """Carga un PDF o muestra una página web de prueba."""
        # Por ahora, mostramos Google para probar que QWebEngineView funciona
        test_url = QUrl("https://github.com/GAMMA-BOARD-FTD-PACC/gamma-lab-desktop-app/blob/develop/requirements.txt")
        self.ui.pdfView.setUrl(test_url)


    
    
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
            lambda: webbrowser.open("https://youtube.com/playlist?list=PLTiLHF2jqOJZLib1CLtq1JnGZeNTktVmm&si=6JOE_WovbWcczJy2")
        )

        # Releases / Downloads
        self.ui.downloadButton.clicked.connect(
            lambda: webbrowser.open("https://github.com/GAMMA-BOARD-FTD-PACC/gamma-lab-desktop-app")
        )

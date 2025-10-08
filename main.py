# main.py
from pathlib import Path
import sys
from PyQt5.QtWidgets import QApplication

from core.kernel import Kernel
from app.view.main_window import MainWindow
from core.plugins.manager import PluginManager
from core.services.data_store import DataStore
from core.services.fileio import FileIOService
from plugins.home.home_plugin import Plugin_home
from plugins.analysis.time.average.average_plugin import Average_plugin


#Frecuencia
from plugins.analysis.frequency.fft.fft_plugin import Fft_plugin
from plugins.analysis.frequency.fft_average.fft_average_plugin import Fft_average_plugin
from plugins.analysis.frequency.psd.psd_plugin import Psd_plugin
from plugins.analysis.frequency.relative_psd.relative_psd_plugin import Relative_psd_plugin
from plugins.analysis.frequency.psd_average.psd_average_plugin import Psd_average_plugin
from plugins.io.open_signal.open_signal_plugin import OpenSignalPlugin
from plugins.preprocessing.trials.trials_plugin import TrialsPlugin



def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(loadStyleSheet())

    kernel = Kernel()

    # 1) Servicios core
    kernel.register_service("DataStore", DataStore())
    kernel.register_service("FileIO", FileIOService())

    # 2) Descubrir e instanciar plugins
    plugins_dir = Path(__file__).resolve().parent / "plugins"
    pm = PluginManager(plugins_dir)
    pm.load_all()

    # 3) Registrar plugins en el kernel POR NOMBRE (desde properties.yml)
    for meta, plugin in pm.all():
        try:
            kernel.register_plugin(meta.name, plugin)
        except Exception as e:
            print(f"No se pudo registrar '{meta.name}':", e)

    # 4) Ventana principal (después de registrar plugins)
    main_win = MainWindow(kernel)
    kernel.register_service("MainWindow", main_win)

    main_win.show()
    sys.exit(app.exec_())


def loadStyleSheet():
    with open("assets/styles/styles.qss", "r") as f:
        return f.read()

if __name__ == "__main__":
    main()

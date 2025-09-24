# main.py
import sys
from PyQt5.QtWidgets import QApplication

from core.kernel import Kernel
from view.ventana import MainWindow
from plugins.ui_plugin import UIPlugin
from plugins.home_plugin.home_plugin import Plugin_home
from plugins.analysis.time.average.average_plugin import Average_plugin
from plugins.analysis.time.erp.erp_plugin import Erp_plugin


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("src/styles.qss")

    kernel = Kernel()


    # plugin para home 
    home_plugin = Plugin_home()
    kernel.register_plugin("home", home_plugin)

    # plugin para tiempo avergae
    time_average_plugin = Average_plugin()
    kernel.register_plugin("time_average", time_average_plugin)

    # plugin para ERP
    time_erp_plugin = Erp_plugin()
    kernel.register_plugin("time_erp", time_erp_plugin)

    #plugin para leer señal 
    ui_plugin = UIPlugin()
    kernel.register_plugin("ui", ui_plugin)


    # Ventana principal 
    main_win = MainWindow(kernel)
    kernel.register_service("MainWindow", main_win)

    main_win.show()
    sys.exit(app.exec_())



if __name__ == "__main__":
    main()

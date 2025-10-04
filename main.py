# main.py
import sys
from PyQt5.QtWidgets import QApplication

from core.kernel import Kernel
from core.services.assets import AssetManager
from app.view.ventana import MainWindow
from plugins.ui_plugin import UIPlugin
from plugins.home.home_plugin import Plugin_home
from plugins.analysis.time.average.average_plugin import Average_plugin
from plugins.analysis.time.erp.erp_plugin import Erp_plugin
#from plugins.io.open_signal_plugin import OpenSignalPlugin

#Frecuencia
from plugins.analysis.frequency.fft.fft_plugin import Fft_plugin
from plugins.analysis.frequency.fft_average.fft_average_plugin import Fft_average_plugin
from plugins.analysis.frequency.psd.psd_plugin import Psd_plugin
from plugins.analysis.frequency.relative_psd.relative_psd_plugin import Relative_psd_plugin
from plugins.analysis.frequency.psd_average.psd_average_plugin import Psd_average_plugin



def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(loadStyleSheet())

    kernel = Kernel()

    '''Core plugins'''
    kernel.register_service("Assets", AssetManager(root="assets/icons"))
    
    '''IO plugins'''
    ui_plugin = UIPlugin()
    kernel.register_plugin("ui", ui_plugin)
    #open_signal_plugin = OpenSignalPlugin()
    #kernel.register_plugin("io.open_signal", open_signal_plugin)
    
    '''Home plugins'''
    home_plugin = Plugin_home()
    ui_plugin = UIPlugin()
    
    kernel.register_plugin("home", home_plugin)
    kernel.register_plugin("ui", ui_plugin)     #plugin para leer señal


    '''Time plugins'''
    time_average_plugin = Average_plugin() # plugin para tiempo avergae 
    time_erp_plugin = Erp_plugin() # plugin para ERP

    kernel.register_plugin("time_erp", time_erp_plugin)
    kernel.register_plugin("time_average", time_average_plugin)



    '''Frequency plugins'''
    frequency_fft_plugin = Fft_plugin()
    frequency_fft_average_plugin = Fft_average_plugin()
    frequency_psd_plugin = Psd_plugin()
    frequency_relative_psd_plugin = Relative_psd_plugin()
    frequency_psd_average_plugin = Psd_average_plugin()

    kernel.register_plugin("frequency_fft", frequency_fft_plugin)
    kernel.register_plugin("frequency_fft_average", frequency_fft_average_plugin)
    kernel.register_plugin("frequency_psd", frequency_psd_plugin)
    kernel.register_plugin("frequency_relative_psd", frequency_relative_psd_plugin)
    kernel.register_plugin("frequency_psd_average", frequency_psd_average_plugin)


    # Ventana principal 
    main_win = MainWindow(kernel)
    kernel.register_service("MainWindow", main_win)

    main_win.show()
    sys.exit(app.exec_())


def loadStyleSheet():
    with open("assets/styles/styles.qss", "r") as f:
        return f.read()

if __name__ == "__main__":
    main()

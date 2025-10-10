from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from plugins.analysis.time.average.average_plugin_ui import Ui_Average
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
import numpy as np

class Average_plugin(IPlugin):
    def __init__(self, meta:PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.kernel = None
        self.ui = None


    def initialize(self, kernel):
        print("Inicializando Average")

    def process(self, data: any):
        print(f"Average recibió datos: {data}")
        if self.mainwin:
            # ejemplo: mostrar mensaje en statusBar (si existe)
            try:
                self.mainwin.statusBar().showMessage(f"Average procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando Average")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("Average tiene acceso a MainWindow")        

    def stop(self):
        print("Deteniendo Average")
        self.mainwin = None

    def get_widget(self, parent=None):
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Average()
            self.ui.setupUi(self.widget)

            # Crear el VTK interactor dentro del contenedor del .ui
            vtk_layout = QVBoxLayout(self.ui.VTK_render_Qwidget)
            vtk_layout.setContentsMargins(0, 0, 0, 0)

            self.vtk_widget = QVTKRenderWindowInteractor(self.ui.VTK_render_Qwidget)
            vtk_layout.addWidget(self.vtk_widget)

            self.renwin = self.vtk_widget.GetRenderWindow()
            try:
                self.vtk_widget.Initialize()
            except Exception:
                pass

            # Conectar botón “Calculate Average”
            self.ui.pushButton.clicked.connect(self._on_calculate_average)

        else:
            self.widget.setParent(parent)

        return self.widget

    def _on_calculate_average(self):
        """Carga el SignalDataset activo desde el DataStore y muestra sus TrialDataset asociados."""
        if not self.mainwin:
            return

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            print("[Average] No hay servicio de DataStore.")
            return

        # Obtener la señal activa
        active_signal = store.get_active_signal()
        if not active_signal:
            print("[Average] No hay señal activa registrada en el DataStore.")
            return
        
        if not active_signal.trials_dataset:
            print("[Average] Esta señal no tiene TrialDataset asociado.")
            return
    
        #Tomar el trial # 0 para prácticidad
        td = active_signal.trials_dataset[0]

        #calcular el promedio por muestras
        av_data = np.mean(td.trials, axis=1)
        t = td.time_rel

        print(f"[Average] Promedio calculado → shape: {av_data.shape}")

        # Render en VTK
        self.render_average(t, av_data, td.channel_name, td.unit)

    def render_average(self, t, av_data, channel_name, unit):
        self.renwin.GetRenderers().RemoveAllItems()

        # Crear tabla VTK
        table = vtk.vtkTable()
        arr_time = vtk.vtkFloatArray()
        arr_time.SetName("Time (s)")
        arr_signal = vtk.vtkFloatArray()
        arr_signal.SetName(f"{channel_name} [{unit}]")

        for ti, si in zip(t, av_data):
            arr_time.InsertNextValue(float(ti))
            arr_signal.InsertNextValue(float(si))

        table.AddColumn(arr_time)
        table.AddColumn(arr_signal)

        # Crear gráfico
        renderer = vtk.vtkRenderer()
        renderer.SetBackground(1, 1, 1)
        self.renwin.AddRenderer(renderer)

        chart = vtk.vtkChartXY()
        scene = vtk.vtkContextScene()
        actor = vtk.vtkContextActor()
        scene.AddItem(chart)
        actor.SetScene(scene)
        renderer.AddActor(actor)
        scene.SetRenderer(renderer)

        chart.SetTitle(f"Average - {channel_name}")
        plot = chart.AddPlot(vtk.vtkChart.LINE)
        plot.SetInputData(table, 0, 1)
        plot.SetColor(0, 0, 0, 255)
        plot.SetWidth(1.5)

        self.renwin.Render()
# ui_plugin.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QPushButton
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk, pyabf
from core.interfaces import IPlugin


class UIPlugin(IPlugin):
    def __init__(self):
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None

    def name(self) -> str:
        return "UIPlugin"
    
    def category(self):
        return "Home"

    def initialize(self, kernel):
        print("Inicializando UIPlugin")

    def process(self, data: any):
        print(f"UIPlugin recibió datos: {data}")

    def start(self, kernel):
        print("Iniciando UIPlugin")
        self.mainwin = kernel.get_service("MainWindow")
        

    def stop(self):
        print("Deteniendo UIPlugin")

    def build_widget(self):
        if self.widget is None:
            self.widget = QWidget()
            layout = QVBoxLayout(self.widget)

            # Botón abrir señal
            btn = QPushButton("Seleccionar archivo ABF", self.widget)
            btn.clicked.connect(self.on_open_signal)
            layout.addWidget(btn)

            # VTK Widget
            self.vtk_widget = QVTKRenderWindowInteractor(self.widget)
            layout.addWidget(self.vtk_widget)

            self.renwin = self.vtk_widget.GetRenderWindow()

        return self.widget

    # 👉 Mostrar en el workspace de la ventana principal
    def show_ui(self):
        if self.mainwin:
            w = self.build_widget()
            self.mainwin.show_plugin_widget(w)

    def on_open_signal(self):
        fname, _ = QFileDialog.getOpenFileName(
            self.widget,
            "Abrir archivo ABF",
            "",
            "Archivos ABF (*.abf);;Todos los archivos (*)"
        )
        if fname:
            self.load_abf(fname)

    def load_abf(self, fname):
        abf = pyabf.ABF(fname)
        colors = vtk.vtkNamedColors()

        self.renwin.GetRenderers().RemoveAllItems()
        num_channels = abf.channelCount
        channel_names = abf.adcNames
        print(f"ABF con {num_channels} canales: {channel_names}")

        viewports = []
        for row in range(num_channels):
            viewports.append([
                0.0,
                float(num_channels - (row + 1)) / num_channels,
                1.0,
                float(num_channels - row) / num_channels
            ])

        table = vtk.vtkTable()
        array_x = vtk.vtkFloatArray()
        array_x.SetName('X Axis')
        table.AddColumn(array_x)

        for ch in range(num_channels):
            arr = vtk.vtkFloatArray()
            arr.SetName(channel_names[ch])
            table.AddColumn(arr)

        signalX = abf.sweepX[:2000]
        num_points = len(signalX)
        table.SetNumberOfRows(num_points)

        for i in range(num_points):
            table.SetValue(i, 0, float(signalX[i]))

        for ch in range(num_channels):
            abf.setSweep(0, channel=ch)
            signalY = abf.sweepY[:num_points]
            for i in range(num_points):
                table.SetValue(i, ch + 1, float(signalY[i]))

        for ch in range(num_channels):
            renderer = vtk.vtkRenderer()
            renderer.SetBackground(colors.GetColor3d("WhiteSmoke"))
            renderer.SetViewport(viewports[ch])
            self.renwin.AddRenderer(renderer)

            chart = vtk.vtkChartXY()
            scene = vtk.vtkContextScene()
            actor = vtk.vtkContextActor()
            scene.AddItem(chart)
            actor.SetScene(scene)
            renderer.AddActor(actor)
            scene.SetRenderer(renderer)

            chart.SetTitle(channel_names[ch])
            plot = chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, ch + 1)
            plot.SetColor(*colors.GetColor4ub("Black"))
            plot.SetWidth(0.5)

        self.renwin.Render()
        self.vtk_widget.Initialize()

# ui_plugin.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QPushButton
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk, pyabf
from core.interfaces import IPlugin
from core.services.data_store import DataStore
from core.services.fileio import FileIOService
from core.services.signal_dataset import SignalDataset
from core.vtk_adapters.adapters import dataset_to_vtk_table


class OpenSignalPlugin(IPlugin):
    def __init__(self):
        self.kernel = None
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.ds_key = "raw"

    def name(self) -> str: return "OpenSignalPlugin"
    def category(self):     return "Home"
    def subcategory(self):  return "io"

    def initialize(self, kernel):
        print("Inicializando UIPlugin")

    def process(self, data: any):
        print(f"UIPlugin recibió datos: {data}")

    def start(self, kernel):
        self.kernel = kernel
        print("Iniciando OpenSignalPlugin")
        self.mainwin = kernel.get_service("MainWindow")
        

    def stop(self):
        print("Deteniendo UIPlugin")

    def get_widget(self, parent=None):
        return self.build_widget(parent)

    def build_widget(self, parent=None):
        if self.widget is None:
            self.widget = QWidget(parent)
            layout = QVBoxLayout(self.widget)

            # Botón abrir señal
            btn = QPushButton("Seleccionar archivo ABF", self.widget)
            btn.clicked.connect(self.on_open_clicked)   # <-- usa el método que existe
            layout.addWidget(btn)

            # VTK Widget
            self.vtk_widget = QVTKRenderWindowInteractor(self.widget)
            layout.addWidget(self.vtk_widget)

            self.renwin = self.vtk_widget.GetRenderWindow()
            try:
                # Inicializa ANTES de primer Render
                self.vtk_widget.Initialize()
            except Exception:
                pass

        else:
            self.widget.setParent(parent)
        return self.widget


    def on_open_clicked(self):
        fname, _ = QFileDialog.getOpenFileName(
            self.widget, "Seleccionar archivo ABF", "", "ABF (*.abf);;Todos (*)"
        )
        if fname:
            self.load_and_render(fname)
            
    def load_and_render(self, path: str):
        fileio: FileIOService = self.kernel.get_service("FileIO")
        ds: SignalDataset = fileio.load_abf(path)

        # guarda dataset para otros plugins
        store: DataStore = self.kernel.get_service("DataStore")
        store.set(self.ds_key, ds)

        self.render_dataset(ds)

        if self.mainwin:
            self.mainwin.statusBar().showMessage(f"ABF cargado: {path}", 4000)


    # render
    def render_dataset(self, ds: SignalDataset):
        self.renwin.GetRenderers().RemoveAllItems()

        table = dataset_to_vtk_table(ds)
        colors = vtk.vtkNamedColors()
        C = ds.signals.shape[0]
        
        for ch in range(C):
            vmin = float(C - (ch + 1)) / C
            vmax = float(C - ch) / C

            renderer = vtk.vtkRenderer()
            renderer.SetBackground(colors.GetColor3d("WhiteSmoke"))
            renderer.SetViewport(0.0, vmin, 1.0, vmax)
            self.renwin.AddRenderer(renderer)

            chart = vtk.vtkChartXY()
            scene = vtk.vtkContextScene()
            actor = vtk.vtkContextActor()
            scene.AddItem(chart)
            actor.SetScene(scene)
            renderer.AddActor(actor)
            scene.SetRenderer(renderer)

            title = ds.channel_names[ch] if ch < len(ds.channel_names) else f"ch{ch}"
            chart.SetTitle(title)

            plot = chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, ch + 1)  # 0=time, ch+1=col del canal
            plot.SetColor(*colors.GetColor4ub("Black"))
            plot.SetWidth(0.5)

        self.renwin.Render()

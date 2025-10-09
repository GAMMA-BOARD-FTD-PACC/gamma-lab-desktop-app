# ui_plugin.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QPushButton
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
from pathlib import Path
from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.data_store import DataStore
from core.services.fileio import FileIOService
from core.services.signal_dataset import SignalDataset
from core.vtk_adapters.adapters import dataset_to_vtk_table


class OpenSignalPlugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.ds_key = "raw"

    def initialize(self, kernel):
        print(f"Inicializando {self.name()}") 

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
            btn.clicked.connect(self.on_open_clicked)
            layout.addWidget(btn)

            # VTK Widget
            self.vtk_widget = QVTKRenderWindowInteractor(self.widget)
            layout.addWidget(self.vtk_widget)

            self.renwin = self.vtk_widget.GetRenderWindow()
            try:
                self.vtk_widget.Initialize()
            except Exception:
                pass

        else:
            self.widget.setParent(parent)
        return self.widget


    def on_open_clicked(self):
        fname, _ = QFileDialog.getOpenFileName(
            self.widget,
            "Seleccionar archivo de señal",
            "",
            "Señales (*.abf *.edf *.ebf *.mat);;Archivos ABF (*.abf);;Archivos EDF (*.edf);;Archivos EBF (*.ebf);;Archivos MAT (*.mat)"
        )
        if fname:
            self.load_and_render(fname)
            
    def load_and_render(self, path: str):
        fileio: FileIOService = self.kernel.get_service("FileIO")
        if fileio is None:
            fileio = FileIOService()
            self.kernel.register_service("FileIO", fileio)

        ext = Path(path).suffix.lower()
        if ext == ".abf":
            ds = fileio.load_abf(path)
        elif ext == ".edf":
            ds = fileio.load_edf(path)
        else:
            # Puedes mostrar un mensaje de error si lo deseas
            if self.mainwin:
                self.mainwin.statusBar().showMessage(f"Formato no soportado: {ext}", 4000)
            return

        # Guarda y pinta como antes
        store: DataStore = self.kernel.get_service("DataStore")
        #Registrar el servicio de DataStore
        if store is None:
            store = DataStore()
            self.kernel.register_service("DataStore", store)
        
        #usar el método de datastore para almacenar una señal cruda
        file_name = Path(path).name
        key = store.add_signal(ds, file_name)
        print(f"[OpenSignal] Guardado en DataStore: {key}")

        self.render_dataset(ds)
        if self.mainwin:
            self.mainwin.statusBar().showMessage(f"Cargado: {path}", 4000)


    # render
    def render_dataset(self, ds: SignalDataset):
        self.renwin.GetRenderers().RemoveAllItems()

        MIN_PLOT_HEIGHT_PX = 250  
        h = max(1, self.vtk_widget.height())
        avail_h = max(1, h - 8)
        max_visible = max(1, avail_h // MIN_PLOT_HEIGHT_PX)
        C_total = ds.signals.shape[0]
        C = min(C_total, int(max_visible))
        
        table = dataset_to_vtk_table(ds)
        colors = vtk.vtkNamedColors()
        
        for idx, ch in enumerate(range(C)):
            vmin = float(C - (idx + 1)) / C
            vmax = float(C - idx) / C

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
            plot.SetInputData(table, 0, ch + 1) 
            plot.SetColor(*colors.GetColor4ub("Black"))
            plot.SetWidth(0.5)

        if C_total > C and self.mainwin:
                self.mainwin.statusBar().showMessage(
                    f"Mostrando {C} de {C_total} canales (alto mínimo {MIN_PLOT_HEIGHT_PX}px).",
                    5000
                )
        
        self.renwin.Render()

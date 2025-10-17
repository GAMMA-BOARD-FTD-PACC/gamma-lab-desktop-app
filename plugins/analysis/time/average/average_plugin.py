from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset
from plugins.analysis.time.average.average_plugin_ui import Ui_Average
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QMessageBox
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
            self.ensure_vtk()

            # Crear el VTK interactor dentro del contenedor del .ui
            vtk_layout = QVBoxLayout(self.ui.VTK_render_Qwidget)
            vtk_layout.setContentsMargins(0, 0, 0, 0)

            self.vtk_widget = QVTKRenderWindowInteractor(self.ui.VTK_render_Qwidget)
            vtk_layout.addWidget(self.vtk_widget)

            # Conectar botón “Calculate Average”
            self.ui.mainActionButton.clicked.connect(self._on_calculate_average)

        else:
            self.widget.setParent(parent)

        return self.widget
    
    def _log(self, *args):
        print("[Average]", *args)

    def _get_active_signal(self) -> SignalDataset | None:
        """Devuelve la señal activa"""
        try:
            store: DataStore | None = self.mainwin.kernel.get_service("DataStore")
            if store is None:
                QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
                return
            ds = store.get_active_signal() if store else None
            if not ds:
                print("[Average] No hay señal activa registrada en el DataStore.")
                return

            self._log("_get_active_signal:", "ok" if ds else "None")
            return ds
        except Exception as e:
            self._log("_get_active_signal error:", e)
            return None

    def _on_calculate_average(self):
        """Carga el SignalDataset activo desde el DataStore y muestra sus TrialDataset asociados."""

        active_signal = self._get_active_signal()        
        # if not active_signal.trials_dataset:
        #     print("[Average] Esta señal no tiene TrialDataset asociado.")
        #     return
    
        #Tomar el trial # 0 para prácticidad
        td = active_signal.get_active_trials()[0]

        #calcular el promedio por muestras
        av_data = np.mean(td.trials, axis=1)
        t = td.time_rel

        print(f"[Average] Promedio calculado → shape: {av_data.shape}")

        # Render en VTK
        self.render_average(t, av_data, td.channel_name, td.unit)

    def render_average(self, t, av_data, channel_name=None, unit=None):
        """
        Renderiza el promedio usando vtkContextView + vtkChartXY (similar a ERP).
        t: array 1D de tiempos
        av_data: array 1D de valores promedio
        """
        if self.view is None:
            self.ensure_vtk()

        # Validaciones mínimas
        t = np.asarray(t, dtype=float)
        av = np.asarray(av_data, dtype=float)
        if t.ndim != 1 or av.ndim != 1 or t.size != av.size:
            QMessageBox.warning(self.widget, "Render error", "Vectores de tiempo y señal deben tener la misma longitud 1D.")
            return

        # Downsample si hay muchísimos puntos (para mantener interacción fluida)
        MAX_SAMPLES = 2000
        N = t.size
        if N > MAX_SAMPLES:
            factor = int(np.ceil(N / MAX_SAMPLES))
            t_plot = t[::factor]
            av_plot = av[::factor]
        else:
            t_plot = t
            av_plot = av

        # Limpiar escena y crear tabla VTK
        scene = self.view.GetScene()
        scene.ClearItems()

        table = vtk.vtkTable()
        arr_time = vtk.vtkFloatArray(); arr_time.SetName("Time (s)")
        arr_sig  = vtk.vtkFloatArray();  arr_sig.SetName(f"{channel_name or 'Signal'} [{unit or ''}]")

        for ti, si in zip(t_plot, av_plot):
            arr_time.InsertNextValue(float(ti))
            arr_sig.InsertNextValue(float(si))

        table.AddColumn(arr_time)
        table.AddColumn(arr_sig)

        # Chart + actor (igual patrón que ERP)
        chart = vtk.vtkChartXY()
        scene.AddItem(chart)

        # Dibujar línea
        plot = chart.AddPlot(vtk.vtkChart.LINE)
        plot.SetInputData(table, 0, 1)
        # Opcionales: ancho y color
        try:
            plot.SetWidth(1.5)
            # SetColor espera RGBA (0..255) en algunas versiones
            plot.SetColor(0, 0, 0, 255)
        except Exception:
            pass

        chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle("Time (s)")
        chart.GetAxis(vtk.vtkAxis.LEFT).SetTitle(unit or "Amplitude")
        chart.SetTitle(f"Average - {channel_name or ''}")

        # Forzar render
        try:
            self.view.GetRenderWindow().Render()
        except Exception:
            # Fallback: si view no tiene RenderWindow usar vtk_widget
            try:
                self.vtk_widget.GetRenderWindow().Render()
            except Exception:
                pass


    def ensure_vtk(self):
        """Crea e inicializa los widgets VTK y las vistas (context view)."""
        # Crear QVTK dentro del contenedor ya definido en el .ui
        if not self.vtk_widget:
            self.vtk_widget = QVTKRenderWindowInteractor(self.ui.VTK_render_Qwidget)
            layout = self.ui.VTK_render_Qwidget.layout()
            if layout is None:
                layout = QVBoxLayout(self.ui.VTK_render_Qwidget)
                layout.setContentsMargins(0, 0, 0, 0)
                self.ui.VTK_render_Qwidget.setLayout(layout)
            layout.addWidget(self.vtk_widget)

        # ContextView (facilita charting similar a Erp_plugin)
        self.view = vtk.vtkContextView()
        self.view.SetRenderWindow(self.vtk_widget.GetRenderWindow())
        # Fondo similar a ERP
        try:
            self.view.GetRenderer().SetBackground(0.98, 0.98, 0.98)
        except Exception:
            pass

        # Inicializar interactores (evita errores en algunos SO)
        try:
            self.vtk_widget.Initialize()
        except Exception:
            pass
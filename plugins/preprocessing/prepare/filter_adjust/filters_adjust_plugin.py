from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset
from plugins.preprocessing.prepare.filter_adjust.filters_adjust_ui import Ui_Filters_Adjust
from PyQt5.QtWidgets import QWidget, QMessageBox,QVBoxLayout
from PyQt5 import QtCore
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkImagingFourier import vtkImageButterworthHighPass
from vtkmodules.vtkCommonDataModel import vtkImageData

class FiltersAdjustPlugin(IPlugin):

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)

        self.kernel = None
        self.mainwin = None
        self.ui = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.params = {
            "filter_type": "Butterworth",
            "high_range": 4.0,
            "low_range": 0.5,
            "order": 2,
            "sample_density": 1000
        }
 
    # end def

# ====== Getting the widget ================
    def initialize(self, kernel):
        self.kernel = kernel
    # end def

    def process(self, data):
        return super().process(data)
    # end def

    def start(self, kernel):
        if self.mainwin:
            self.started = True
            print("Filters tiene acceso a MainWindow")
        else:
            self.renwin = self.vtk_widget.GetRenderWindow()
        # end if
    # end def

    def stop(self):
        self.mainwin = None
        print("[FiltersAdjust] stop")
    # end def
    
    def get_widget(self, parent=None):
        """Devuelve el widget principal del plugin (interfaz de usuario)."""
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Filters_Adjust()
            self.ui.setupUi(self.widget)

            # --- Configurar interacciones ---
            self.ui.doubleSpinBox_low.setValue(self.params["low_range"])
            self.ui.doubleSpinBox_high.setValue(self.params["high_range"])
            self.ui.type_select.setCurrentText(self.params["filter_type"])

            # Conexión de botones
            self.ui.pushButton_filter.clicked.connect(self.on_click_filter_btn)
            self.ui.pushButton_adjust.clicked.connect(self.on_click_adjust_btn)

            # Vincular el área VTK
            self._setup_vtk()
        else:
            self.widget.setParent(parent)

        return self.widget

    def _setup_vtk(self):
        """Inicializa el QVTKRenderWindowInteractor dentro de la UI."""
        frame = self.ui.graphicsView_1  # usa uno de los GraphicsView definidos
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        # Crear e inicializar el widget VTK
        self.vtk_widget = QVTKRenderWindowInteractor(parent=frame)
        layout.addWidget(self.vtk_widget)

        if self.vtk_widget is None:
            print("[ERROR] vtk_widget no está inicializado correctamente.")
            return

        render_window = self.vtk_widget.GetRenderWindow()
        if render_window is None:
            print("[ERROR] No se pudo obtener el RenderWindow de vtk_widget.")
            return
        else:
            print("[DEBUG] RenderWindow inicializado correctamente:", render_window)

        render_window.SetMultiSamples(0)
        self.renwin = render_window

        self.vtk_widget.Initialize()
        self.vtk_widget.Start()

        # Si necesitas iniciar un temporizador (como en tu código original)
        QtCore.QTimer.singleShot(0, self._init_interactor)


    def _init_interactor(self):
        """Inicializa el interactor del VTK."""
        if self.vtk_widget:
            interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
            interactor.Initialize()

# ============= Adjusting controls ==================

    def _init_controls(self):
        print("Controles")
    # end def

# =========== Interaction with UI =====================

    def on_click_filter_btn(self):
        self.run_filter()
    # end def

    def run_filter(self):
        """Aplica un filtro Butterworth a la señal activa del DataStore."""
        try:
            low = float(self.ui.doubleSpinBox_low.value())
            high = float(self.ui.doubleSpinBox_high.value())
            order = int(self.ui.spinBox_order.value())
        except Exception:
            QMessageBox.warning(self.widget, "Error", "Parámetros inválidos")
            return

        # Obtener la señal activa del DataStore
        store = self.kernel.get_service("DataStore")
        if not store:
            QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
            return

        signals = store.get_signals()
        if not signals:
            QMessageBox.warning(self.widget, "Error", "No hay señales cargadas.")
            return

        key = next(iter(signals))
        ds = signals[key]
        print(f"[FiltersAdjustPlugin] Señal seleccionada: {key}")

        # Obtener el primer canal de la señal
        channel_idx = 0
        signal = ds.signals[channel_idx, :].astype(float)
        fs = ds.sampling_rate or 1000.0

        # === Convertir señal a vtkImageData (2 componentes) ===
        img = vtk.vtkImageData()
        N = len(signal)
        img.SetDimensions(N, 1, 1)
        img.AllocateScalars(vtk.VTK_DOUBLE, 2)

        # Llenar los valores
        for i, value in enumerate(signal):
            img.SetScalarComponentFromFloat(i, 0, 0, 0, float(value))
            img.SetScalarComponentFromFloat(i, 0, 0, 1, 0.0)

        # === Aplicar filtro Butterworth ===
        butter_high = vtkImageButterworthHighPass()
        butter_high.SetInputData(img)
        butter_high.SetCutOff(high)
        butter_high.SetOrder(order)
        butter_high.Update()

        output_vtk = butter_high.GetOutput()
        self._render_filtered_signal(output_vtk, fs=fs)
        print("[FiltersAdjustPlugin] Filtro Butterworth aplicado correctamente.")

    def _render_filtered_signal(self, filtered_output, fs: float, unit: str = "Amplitude"):
        """
        Renderiza la señal filtrada dentro del QVTKRenderWindowInteractor existente.
        """
        if not hasattr(self, "vtk_widget") or self.vtk_widget is None:
            print("[FiltersAdjustPlugin] No hay QVTKRenderWindowInteractor disponible.")
            return

        renwin = self.vtk_widget.GetRenderWindow()
        if not renwin:
            print("[FiltersAdjustPlugin] No se pudo obtener el RenderWindow.")
            return

        # Limpiar renderers previos
        renwin.GetRenderers().RemoveAllItems()

        colors = vtk.vtkNamedColors()
        renderer = vtk.vtkRenderer()
        renderer.SetBackground(colors.GetColor3d("WhiteSmoke"))
        renwin.AddRenderer(renderer)

        # Crear tabla con datos
        scalars = filtered_output.GetPointData().GetScalars()
        if not scalars:
            print("[FiltersAdjustPlugin] El filtro no produjo salida.")
            return

        n_points = filtered_output.GetNumberOfPoints()
        arr_time = vtk.vtkFloatArray()
        arr_time.SetName("Time (s)")
        arr_signal = vtk.vtkFloatArray()
        arr_signal.SetName("Filtered Signal")

        # Rellenar arrays sin NumPy
        n_components = scalars.GetNumberOfComponents()

        for i in range(n_points):
            t = i / fs
            tuple_val = scalars.GetTuple(i)  # devuelve una tupla con todos los componentes
            if n_components == 1:
                value = tuple_val[0]
            else:
                # Promediar los componentes si hay más de uno
                value = sum(tuple_val) / n_components
            arr_time.InsertNextValue(t)
            arr_signal.InsertNextValue(value)


        table = vtk.vtkTable()
        table.AddColumn(arr_time)
        table.AddColumn(arr_signal)

        # --- Configurar escena y gráfico ---
        scene = vtk.vtkContextScene()
        chart = vtk.vtkChartXY()
        scene.AddItem(chart)

        plot = chart.AddPlot(vtk.vtkChart.LINE)
        plot.SetInputData(table, 0, 1)
        plot.SetWidth(1.4)
        plot.SetLabel("Señal Filtrada")

        chart.GetAxis(0).SetTitle("Time (s)")
        chart.GetAxis(1).SetTitle(unit)

        # Crear actor para el gráfico y añadirlo al renderer
        chart_actor = vtk.vtkContextActor()
        chart_actor.SetScene(scene)
        scene.SetRenderer(renderer)
        renderer.AddActor(chart_actor)

        # Render final
        try:
            renwin.Render()
            self.vtk_widget.update()
            print("[FiltersAdjustPlugin] Gráfico renderizado correctamente.")
        except Exception as e:
            print("[FiltersAdjustPlugin] Error al renderizar:", e)


    # end def

    def on_click_adjust_btn(self):
        self.run_adjust()
    # end def

    def run_adjust(self):
        print("yesx2")
    # end def

# end class
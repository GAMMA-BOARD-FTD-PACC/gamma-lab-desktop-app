from core import kernel
from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu


from plugins.analysis.time.average.average_plugin_ui import Ui_Average
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QMessageBox, QMenu
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
import numpy as np



class Average_plugin(IPlugin):
    def __init__(self, meta:PluginMeta):
        super().__init__(meta)
        self.vtk_widget = None
        self.renwin = None
        self.ui = None
        self.vtk_menu: VTKContextMenu | None = None


    def process(self, data: any):
        if self.vtk_widget:
            self.vtk_widget.Enable()

    def stop(self):
        print("Deteniendo Average")

        if self.vtk_widget:
            self.vtk_widget.Disable()


    def start(self, kernel: kernel):
        print("Iniciando Average")
        self.mainwin = kernel.get_service("MainWindow")
        #Escuchar los eventos del kernel
        self.kernel.event.connect(self.on_kernel_event)


        if self.mainwin:
            self.started = True
            print("Average tiene acceso a MainWindow")        


    def get_widget(self, parent=None):
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_Average()
            self.ui.setupUi(self.widget)
            #Asignar el widget a los alerts
            self.alerts.parent = self.widget

            self.ensure_vtk()

            # Conectar botón “Calculate Average”
            self.ui.mainActionButton.clicked.connect(self._on_calculate_average)

        else:
            self.widget.setParent(parent)

        return self.widget


    def _on_calculate_average(self):
        """Carga el SignalDataset activo desde el DataStore y muestra sus TrialDataset asociados."""

        if self.get_active_signal() is None:
            return
        
        
        trials = self.get_active_trials()
        if trials is None:
            return

        # Calcular promedio por muestra (a lo largo de los trials)
        av_data = np.mean(trials.trials, axis=1)
        t = trials.time_rel

        self._notify(f"Promedio calculado → shape: {av_data.shape} con {trials.trials.shape[1]} trials usados")

        
        # Render en VTK
        self.render_average(t, av_data, trials.channel_name, trials.unit)

    def render_average(self, t, av_data, channel_name=None, unit=None):
        """
        Renderiza el promedio usando vtkContextView + vtkChartXY
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

        # Chart + actor 
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

        # --- Menú contextual---

        signal_name = self.active_signal.name
        ch_name = channel_name or "channel"
        graph_uid = f"average"
        
        if self.vtk_menu is not None:
            self.vtk_menu.on_view_rebuilt(
                chart,
                view_id="average",
                trial_id=None,
                channel_name=f"{signal_name}:{ch_name}",
                plugin=self.meta.id,
                domain=self.meta.subcategory,
                graph_id=graph_uid
            )
        # --- Fin menú contextual---

        # Forzar render
        try:
            self.view.GetRenderWindow().Render()
        except Exception:
            # Fallback: si view no tiene RenderWindow usar vtk_widget
            try:
                self.vtk_widget.GetRenderWindow().Render()
            except Exception:
                pass

    
    def on_show_stats(self):
        # Acción personalizada del plugin Average
        QMessageBox.information(self.widget, "Estadísticas", "Promedio calculado correctamente.")

    def ensure_vtk(self):
        """Crea e inicializa los widgets VTK y las vistas (context view)."""
        # Crear QVTK dentro del contenedor ya definido en el .ui
        if not self.vtk_widget:
            self.vtk_widget = QVTKRenderWindowInteractor(self.ui.VTK_render_Qwidget)
            
            layout = QVBoxLayout(self.ui.VTK_render_Qwidget)
            layout.setContentsMargins(0, 0, 0, 0)
            self.ui.VTK_render_Qwidget.setLayout(layout)
            layout.addWidget(self.vtk_widget)

        # ContextView (facilita charting)
        self.view = vtk.vtkContextView()
        self.view.SetRenderWindow(self.vtk_widget.GetRenderWindow())
        self.view.GetRenderer().SetBackground(0.98, 0.98, 0.98)
        self.vtk_widget.Initialize()
        
        # Menú
        if self.vtk_menu is None:
            base_scope = {
                "view_id": "average",
                "graph_id": "average:blank",
                "trial_id": None,           
                "channel_name": None,       
                "plugin": "average",
                "domain": "time",
            }
            try:
                self.vtk_menu = VTKContextMenu(
                    chart=None,
                    vtk_widget=self.vtk_widget,
                    plugin_name="average",
                    measurements_enabled=True,
                    measure_scope=base_scope,
                    parent=self.widget
                )
                self.vtk_menu.set_datastore(self.kernel.get_service("DataStore"))
                self.vtk_menu.add_action("Mostrar estadísticas", self.on_show_stats)
            except Exception as e:
                QMessageBox.information(self.widget, "Context menu",
                                        "Error creating context menu.\n" + str(e))


   
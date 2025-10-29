from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QWidget, QMessageBox

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset

from plugins.preprocessing.prepare.filter.filter_plugin_ui import Ui_Filter

import vtk
from vtkmodules.vtkCommonCore import vtkDoubleArray
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from vtkmodules.vtkImagingFourier import vtkImageButterworthHighPass
from vtkmodules.vtkCommonDataModel import vtkImageData

import numpy as np

class Filter_plugin(IPlugin):
    """Filter plugin for signal processing"""

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.kernel = None
        self.ui = None
        self.vtk_menu = None
        self._context_view = None

        # VTK widgets
        self.vtk_top: QVTKRenderWindowInteractor | None = None
        self.vtk_bot: QVTKRenderWindowInteractor | None = None
        self.view_top: vtk.vtkContextView | None = None
        self.view_bot: vtk.vtkContextView | None = None
 
    # end def

    # =====================================================
    # === Plugin lifecycle
    # =====================================================
    def initialize(self, kernel):
        print("Initializing Filter")
    # end def

    def process(self, data: any):
        if self.vtk_widget:
            self.vtk_widget.Enable()

        if self.vtk_top and self.vtk_top.GetRenderWindow().GetInteractor():
            self.vtk_top.GetRenderWindow().GetInteractor().Enable()

        if self.vtk_bot and self.vtk_bot.GetRenderWindow().GetInteractor():
                self.vtk_bot.GetRenderWindow().GetInteractor().Enable()
    # end def

    def start(self, kernel):
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
    # end def

    def stop(self):
        if self.vtk_top and self.vtk_top.GetRenderWindow().GetInteractor():
            self.vtk_top.GetRenderWindow().GetInteractor().Disable()

        if self.vtk_bot and self.vtk_bot.GetRenderWindow().GetInteractor():
            self.vtk_bot.GetRenderWindow().GetInteractor().Disable()
    # end def

    def _log(self, *args):
        print("[Filter]", *args)
    # end def
    
    # =====================================================
    # === Create widget UI + VTK
    # =====================================================
    def get_widget(self, parent=None):
        if self.widget is not None:
            self.widget.setParent(parent)
            return self.widget

        self.widget = QWidget(parent)
        self.ui = Ui_Filter()
        self.ui.setupUi(self.widget)

        self.init_controls()
        self.ensure_vtk()

        return self.widget
    # end def
    
    # =====================================================
    # === Utilities
    # =====================================================
    def init_controls(self):
        self.ui.splitter.setStretchFactor(0, 0)
        self.ui.splitter.setStretchFactor(1, 1)
        self.ui.splitter.widget(1).setMaximumWidth(300)

        self.ui.doubleSpinBox_high.setRange(0, 1000)
        self.ui.doubleSpinBox_high.setValue(4.0)
        self.ui.doubleSpinBox_low.setRange(0, 1000)
        self.ui.doubleSpinBox_low.setValue(0.5)
        self.ui.spinBox_order.setRange(0, 100)
        self.ui.spinBox_order.setValue(2)
        self.ui.type_select.addItems(["Butterworth", "Chebyshev", "Elliptic"])

        self.ui.pushButton_filter.clicked.connect(self.on_apply_filter)
    # end def

    def ensure_vtk(self):
        """Initialize VTK components for rendering."""

        # Filtered signal
        self.vtk_top = QVTKRenderWindowInteractor(self.ui.filteredSignal)
        self.ui.filteredSignal.setLayout(QtWidgets.QVBoxLayout())
        self.ui.filteredSignal.layout().setContentsMargins(0, 0, 0, 0)
        self.ui.filteredSignal.layout().addWidget(self.vtk_top)

        self.view_top = vtk.vtkContextView()
        self.view_top.SetRenderWindow(self.vtk_top.GetRenderWindow())
        self.view_top.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        # Filtered trial
        self.vtk_bot = QVTKRenderWindowInteractor(self.ui.filteredTrial)
        self.ui.filteredTrial.setLayout(QtWidgets.QVBoxLayout())
        self.ui.filteredTrial.layout().setContentsMargins(0, 0, 0, 0)
        self.ui.filteredTrial.layout().addWidget(self.vtk_bot)

        self.view_bot = vtk.vtkContextView()
        self.view_bot.SetRenderWindow(self.vtk_bot.GetRenderWindow())
        self.view_bot.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        try:
            self.vtk_top.Initialize()
            self.vtk_bot.Initialize()
        except Exception:
            pass

        except Exception as e:
            self._log("Error ensure_vtk:", e)
    # end def

    def _get_active_signal(self) -> SignalDataset | None:
        """ Returns active signal from DataStore """
        try:
            store: DataStore | None = self.mainwin.kernel.get_service("DataStore")
            if store is None:
                QMessageBox.warning(self.widget, "Error", "DataStore Not Found.")
                return
            ds = store.get_active_signal() if store else None
            return ds
        except Exception as e:
            print("[Filter] Error getting signal", e)
            return None
    # end def

    # =====================================================
    # === Main Logic: Filter + Render
    # =====================================================
    def on_apply_filter(self):
        try:
            active_signal = self._get_active_signal()
            if not active_signal:
                raise ValueError("No active signal found")

            channel_name = active_signal.channel_names[0]
            trials = active_signal.get_active_trials(active_signal.name, channel_name)
            if trials.trials is None:
                raise ValueError("No active trials found")

            signal_data = active_signal.signals[:, 0]
            trial_data = trials.trials[:, 0]

            low = float(self.ui.doubleSpinBox_low.value())
            high = float(self.ui.doubleSpinBox_high.value())
            order = int(self.ui.spinBox_order.value())

            filtered_signal = self.run_filter(signal_data, low, high, order)
            filtered_trial = self.run_filter(trial_data, low, high, order)

            if filtered_signal and filtered_trial:
                self._render_filtered(filtered_signal, active_signal.sampling_rate, unit="Amplitude", type = "signal")
                self._render_filtered(filtered_trial, active_signal.sampling_rate, unit="Amplitude", type = "trial")

        except ValueError as ve:
            QMessageBox.warning(self.widget, "Error", str(ve))
        except Exception as e:
            self._log("Unexpected error in on_apply_filter:", e)
            QMessageBox.critical(self.widget, "Error", f"Unexpected error: {e}")
    # end def

    def run_filter(self, signal, low, high, order, type = "butterworth"):
        try:
            signal = np.asarray(signal, dtype=np.float64)
            N = len(signal)
            img = vtk.vtkImageData()
            img.SetDimensions(N, 1, 1)
            img.AllocateScalars(vtk.VTK_DOUBLE, 2)

            arr = vtkDoubleArray()
            arr.SetNumberOfComponents(2)
            arr.SetNumberOfTuples(N)

            for i in range(N):
                arr.SetComponent(i, 0, float(signal[i]))
                arr.SetComponent(i, 1, 0.0)

            img.GetPointData().SetScalars(arr)

            result = None

            if type == "butterworth":
                butter_high = vtkImageButterworthHighPass()
                butter_high.SetInputData(img)
                butter_high.SetCutOff(high)
                butter_high.SetOrder(order)
                butter_high.Update()

                result = butter_high.GetOutput()
            # end if

            return result
        
        except Exception as e:
            self._log("Error running filter:", e)
            return None
    # end def

    def _render_filtered(self, filtered_output, fs: float, unit: str = "Amplitude", type: str = ""):
        """
        Render filtered signal or trial using the correct vtkContextView.
        """
        try:
            # --- Select proper rendering context ---
            if type == "signal":
                vtk_widget = self.vtk_top
                view = self.view_top
            elif type == "trial":
                vtk_widget = self.vtk_bot
                view = self.view_bot
            else:
                print("[Filter] Unknown render type. Expected 'signal' or 'trial'.")
                return

            if not vtk_widget or not view:
                print(f"[Filter] VTK context for '{type}' not initialized.")
                return

            # --- Get render window & scene ---
            renwin = view.GetRenderWindow()
            if not renwin:
                print(f"[Filter] Could not get RenderWindow for '{type}'.")
                return

            scene = view.GetScene()
            if not scene:
                print(f"[Filter] Could not get Scene for '{type}'.")
                return

            # --- Clear any previous charts ---
            scene.ClearItems()

            # --- Validate filtered output ---
            scalars = filtered_output.GetPointData().GetScalars()
            if not scalars:
                print(f"[Filter] No scalar data in filtered output ({type}).")
                return

            n_points = filtered_output.GetNumberOfPoints()
            n_components = scalars.GetNumberOfComponents()

            # --- Build VTK table ---
            arr_time = vtk.vtkFloatArray()
            arr_time.SetName("Time (s)")
            arr_signal = vtk.vtkFloatArray()
            arr_signal.SetName("Filtered Signal")

            for i in range(n_points):
                t = i / fs
                tuple_val = scalars.GetTuple(i)
                value = tuple_val[0] if n_components == 1 else sum(tuple_val) / n_components
                arr_time.InsertNextValue(t)
                arr_signal.InsertNextValue(value)

            table = vtk.vtkTable()
            table.AddColumn(arr_time)
            table.AddColumn(arr_signal)

            # --- Create and configure chart ---
            chart = vtk.vtkChartXY()
            plot = chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, 1)
            plot.SetWidth(1.2)
            plot.SetColor(0, 0, 255, 255)
            plot.SetLabel(f"Filtered {type.capitalize()}")

            # Axes configuration
            ax_b = chart.GetAxis(vtk.vtkAxis.BOTTOM)
            ax_l = chart.GetAxis(vtk.vtkAxis.LEFT)
            ax_b.SetGridVisible(True)
            ax_l.SetGridVisible(True)
            ax_b.SetTitle("Time (s)")
            ax_l.SetTitle(unit)

            chart.SetTitle(f"Filtered {type.capitalize()}")

            # --- Add chart to scene ---
            scene.AddItem(chart)

            # --- Render final ---
            try:
                renwin.Render()
                vtk_widget.update()
                print(f"[Filter] {type.capitalize()} chart rendered successfully.")
            except Exception as e:
                print(f"[Filter] Render error in {type}:", e)

        except Exception as e:
            print(f"[Filter] Error rendering {type}:", e)

    # end def

# end class
# plugins/preprocessing/prepare/artifact_remove/artifact_remove_plugin.py
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QWidget, QMessageBox, QVBoxLayout
import numpy as np
import vtk
from typing import Optional
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset

from plugins.preprocessing.prepare.artifact_remove.artifact_remove_ui import Ui_ArtifactRemove
from plugins.preprocessing.prepare.artifact_remove.artifact_logic import apply_artifact_modification

LOGP = "[ArtifactRemovePlugin]"

class ArtifactRemovePlugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel, self.mainwin, self.widget, self.ui = None, None, None, None
        self.vtk_interactor, self.vtk_view, self.chart = None, None, None

    def initialize(self, kernel): pass
    def process(self, data): pass

    def start(self, kernel):
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        try: self.kernel.event.connect(self._on_data_updated)
        except Exception: pass
        
    def stop(self):
        try:
            if self.kernel: self.kernel.event.disconnect(self._on_data_updated)
        except Exception: pass

    def get_widget(self, parent=None):
        if self.widget is None:
            self.widget = QWidget(parent)
            self.ui = Ui_ArtifactRemove()
            self.ui.setupUi(self.widget)
            self._setup_vtk()
            self._wire_controls()
        self.widget.setParent(parent)
        self._load_and_display_trials()
        return self.widget

    def _setup_vtk(self):
        if self.vtk_view: return
        container = self.ui.signal_container
        layout = QVBoxLayout(container); layout.setContentsMargins(0, 0, 0, 0)
        self.vtk_interactor = QVTKRenderWindowInteractor(container)
        layout.addWidget(self.vtk_interactor)
        self.vtk_view = vtk.vtkContextView()
        self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
        self.vtk_view.GetInteractor().AddObserver(vtk.vtkCommand.MouseMoveEvent, self._on_mouse_move)
        self.vtk_interactor.Initialize(); self.vtk_interactor.Start()

    def _wire_controls(self):
        self.ui.artifact_panel.apply_button.clicked.connect(self._on_apply_changes)

    def _on_data_updated(self, topic: str, payload: object):
        if topic in ["signal_added", "trials_generated"] and self.widget and self.widget.isVisible():
            self._load_and_display_trials()

    def _find_active_trials_dataset(self) -> Optional[TrialDataset]:
        if not self.kernel: return None
        store = self.kernel.get_service("DataStore")
        if not store: return None
        active_signal = store.get_active_signal()
        if not isinstance(active_signal, SignalDataset) or not active_signal.trials_dataset:
            return None
        return active_signal.trials_dataset[-1]

    def _load_and_display_trials(self):
        td = self._find_active_trials_dataset()
        if td is None:
            self._clear_render("No hay trials generados."); return
        average_trial = np.mean(td.trials, axis=1)
        title = f"Promedio de {td.trials.shape[1]} Trials - {td.channel_name}"
        self._render_curve(td.time_rel, average_trial, title)

    def _on_apply_changes(self):
        panel = self.ui.artifact_panel
        mode_text = panel.mode_combo.currentText()
        try:
            point_a = float(panel.point_a.text())
            point_b = float(panel.point_b.text()) if panel.point_b.isVisible() else 0.0
            mode = 'cut' if mode_text == "Cut From Start" else 'interpolate'
            
            apply_artifact_modification(kernel=self.kernel, mode=mode, point_a=point_a, point_b=point_b)
            
            self._load_and_display_trials()
            QMessageBox.information(self.widget, "Éxito", "Cambios aplicados correctamente.")
        except Exception as e:
            QMessageBox.critical(self.widget, "Error de Procesamiento", str(e))

    def _on_mouse_move(self, interactor, event):
        if not self.chart or not self.mainwin or not self.vtk_view: return
        pos = interactor.GetEventPosition()
        coords = self.vtk_view.GetScene().GetSceneToViewTransform().GetInverse().TransformFloatPoint(pos[0], pos[1], 0)
        message = f"Tiempo: {coords[0]:.4f} s, Amplitud: {coords[1]:.6f}"
        self.mainwin.statusBar().showMessage(message)

    def _clear_render(self, message=""):
        self._setup_vtk()
        self.vtk_view.GetScene().ClearItems()
        self.vtk_view.GetRenderer().SetBackground(0.1, 0.1, 0.2)
        if message:
            text_actor = vtk.vtkTextActor(); text_actor.SetInput(message)
            prop = text_actor.GetTextProperty()
            prop.SetColor(1.0, 1.0, 1.0); prop.SetJustificationToCentered(); prop.SetVerticalJustificationToCentered(); prop.SetFontSize(16)
            self.vtk_view.GetRenderer().AddActor2D(text_actor)
        self.vtk_view.GetRenderWindow().Render()

    def _render_curve(self, t, y, title=""):
        self._setup_vtk()
        scene = self.vtk_view.GetScene()
        scene.ClearItems()
        self.vtk_view.GetRenderer().SetBackground(vtk.vtkNamedColors().GetColor3d("WhiteSmoke"))
        table = vtk.vtkTable(); arr_t = vtk.vtkFloatArray(); arr_t.SetName("Time (s)"); arr_y = vtk.vtkFloatArray(); arr_y.SetName("Amplitude")
        table.AddColumn(arr_t); table.AddColumn(arr_y)
        n_points = min(len(t), len(y)); table.SetNumberOfRows(n_points)
        for i in range(n_points): table.SetValue(i, 0, t[i]); table.SetValue(i, 1, y[i])
        self.chart = vtk.vtkChartXY(); scene.AddItem(self.chart)
        plot = self.chart.AddPlot(vtk.vtkChart.LINE)
        plot.SetInputData(table, 0, 1)
        plot.SetWidth(1.5); plot.GetPen().SetColor(vtk.vtkNamedColors().GetColor4ub("SteelBlue")); self.chart.SetTitle(title)
        self.chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle("Tiempo (s)"); self.chart.GetAxis(vtk.vtkAxis.LEFT).SetTitle("Amplitud")
        self.vtk_view.GetRenderWindow().Render()
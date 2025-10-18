import sys
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QWidget, QComboBox, QVBoxLayout, QFormLayout, QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QFrame, QMessageBox
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.data_store import DataStore
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset
from core.filters.trials import cut_trials_single_channel
from core.vtk_adapters.adapters import trials_matrix_to_vtk_table
from plugins.preprocessing.trials.trial_plugin_ui import Ui_Trials

class TrialsPlugin(IPlugin):

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None
        self.ui = None

        self.params = {
            "channel": 0,
            "threshold": 0.7,
            "t0": -0.05,
            "t1": 4.0,
            "stim_count": 1,
            "inter_stim_time": 0.0
        }

        self.widget: QWidget | None = None
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None
        self.chart: vtk.vtkChartXY | None = None

        self.visible_trials = []
        self.last_td: TrialDataset | None = None
        self._active_ds: SignalDataset | None = None

    # ---------------- Logs ----------------
    def _log(self, *args):
        print("[TRIALS]", *args)
        sys.stdout.flush()

    # -------------- Ciclo de vida ----------
    def initialize(self, kernel):
        self.kernel = kernel
        self._log("initialize")

    def start(self, kernel):
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        self._log("start: mainwin?", bool(self.mainwin))

    def stop(self):
        self._log("stop")

    def process(self):
        self._log("process")
    # -------------- UI ---------------------
    def get_widget(self, parent=None):
        if self.widget is None:
            self._log("get_widget: creando UI")
            self.ui = Ui_Trials(parent)
            self.widget = self.ui

            self._ensure_vtk()
            self.ui.Btn_generate_trials.clicked.connect(self._on_generate_clicked)
            self._init_controls()

            self._populate_channels_once()

        else:
            self.widget.setParent(parent)

        return self.widget

    def _ensure_vtk(self):
        self._log("ensure_vtk(): enter")
        
        self.vtk_interactor = QVTKRenderWindowInteractor(self.ui.plotArea)
        self.ui.plotArea.setLayout(QtWidgets.QVBoxLayout())
        self.ui.plotArea.layout().setContentsMargins(0, 0, 0, 0)
        self.ui.plotArea.layout().addWidget(self.vtk_interactor)
        self._log("ensure_vtk(): interactor embebido")

        self.vtk_view = vtk.vtkContextView()
        self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
        self.vtk_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        try:
            self.vtk_interactor.Initialize()
        except Exception:
            pass
        self._log("ensure_vtk(): scheduled init")

    def _init_controls(self):
        self._log("_init_controls: set defaults")
        self.ui.thresholdDoubleSpinBox.setRange(0.0, 1e12)
        self.ui.thresholdDoubleSpinBox.setValue(self.params["threshold"])

        self.ui.initialTimeDoubleSpinBox.setRange(-3600.0, 0.0)
        self.ui.initialTimeDoubleSpinBox.setValue(self.params["t0"])

        self.ui.finalTimeDoubleSpinBox.setRange(0.001, 3600.0)
        self.ui.finalTimeDoubleSpinBox.setValue(self.params["t1"])

        self.ui.stimNumberSpinBox.setRange(0, 1_000_000)
        self.ui.stimNumberSpinBox.setValue(self.params["stim_count"] or 0)

        self.ui.interStimTimeDoubleSpinBox.setRange(0.0, 3600.0)
        self.ui.interStimTimeDoubleSpinBox.setValue(self.params["inter_stim_time"] or 0.0)

    def _get_active_signal(self) -> SignalDataset | None:
        """Devuelve la señal activa"""
        try:
            store: DataStore | None = self.kernel.get_service("DataStore")
            ds = store.get_active_signal() if store else None
            self._log("_get_active_signal:", "ok" if ds else "None")
            return ds
        except Exception as e:
            self._log("_get_active_signal error:", e)
            return None


    def _populate_channel_combo(self, ds: SignalDataset):
        """Llena channelComboBox con nombres; userData = índice del canal."""
        cb = getattr(self.ui, "channelComboBox", None)
        cb.blockSignals(True)
        cb.clear()
        names = []
        try:
            if getattr(ds, "channel_names", None):
                names = [str(n) for n in ds.channel_names]
        except Exception as e:
            self._log("channel_names error:", e)

        if not names:
            # Fallback: ch-1..ch-C usando shape de signals
            C = 0
            try:
                sig = getattr(ds, "signals", None)
                C = int(sig.shape[0]) if sig is not None else 0
            except Exception:
                C = 0
            names = [f"ch-{i+1}" for i in range(C)]
            self._log("fallback nombres por shape:", C)

        for i, name in enumerate(names):
            cb.addItem(name, i)  # texto=nombre, userData=índice

        cb.setCurrentIndex(0 if names else -1)
        cb.blockSignals(False)

        self._log("channelComboBox poblado:", cb.count(), "items",
                "ejemplo:", names[:5])


    def _populate_channels_once(self):
        """Intenta cargar la señal activa y poblar el combo (silencioso si no hay)."""
        ds = self._get_active_signal()
        if ds:
            self._populate_channel_combo(ds)
        else:
            self._log("_populate_channels_once: no hay señal activa (aún)")
    
    # -------------- Acciones UI -----------------
    def _on_generate_clicked(self):
        self._log("_on_generate_clicked")

        ds = self._get_active_signal()
        if ds is None:
            QMessageBox.warning(self.widget, "Selección", "No hay señal activa en el DataStore.")
            return
        
        if self.ui.channelComboBox.count() == 0:
            self._populate_channel_combo(ds)
            if self.ui.channelComboBox.count() == 0:
                QMessageBox.warning(self.widget, "Canales", "La señal activa no tiene canales disponibles.")
                return

        ch = self.ui.channelComboBox.currentData()
        if ch is None:
            ch = self.ui.channelComboBox.currentIndex()
        if ch is None or ch < 0:
            QMessageBox.warning(self.widget, "Parámetros",
                                "Seleccione un canal válido.")
            return

        th   = float(self.ui.thresholdDoubleSpinBox.value())
        t0   = float(self.ui.initialTimeDoubleSpinBox.value())
        t1   = float(self.ui.finalTimeDoubleSpinBox.value())
        mode = self.ui.endModeCombo.currentData() or "fixed"
        stim = int(self.ui.stimNumberSpinBox.value())
        stim = None if stim <= 0 else stim
        inter_stim_time  = float(self.ui.interStimTimeDoubleSpinBox.value())
        inter_stim_time  = None if inter_stim_time <= 0 else inter_stim_time

        if mode == "fixed" and not (t1 > t0):
            QMessageBox.warning(self.widget, "Parámetros", "t1 debe ser mayor que t0.")
            return

        self._log("params →", dict(channel=int(ch), threshold=th, t0=t0, t1=t1,
                                end_mode=mode, stim_expected=stim, inter_stim_time=inter_stim_time))

        # Ejecutar corte
        try:
            td: TrialDataset = cut_trials_single_channel(
                ds=ds, channel=int(ch), threshold=th, t0=t0, t1=t1,
                end_mode=mode, stim_expected=stim, inter_stim_time=inter_stim_time
            )
        except Exception as e:
            self._log("cut_trials_single_channel error:", e)
            QMessageBox.critical(self.widget, "Error",
                                f"Falló la generación de trials:\n{e}")
            return

        self._log("TD listo:", td.trials.shape, td.time_rel.shape, "onsets:", len(td.onsets_s))

        try:
            ds.add_trial_dataset(td)
        except Exception as e:
            self._log("add_trial_dataset warning:", e)

        self.last_td = td
        T = td.trials.shape[1]
        self.visible_trials = [1] if T > 0 else []
        self._render_trials(td)

        if self.mainwin:
            self.mainwin.statusBar().showMessage(
                f"Trials: T={td.trials.shape[1]}, Ns={td.trials.shape[0]}, canal='{td.channel_name}'",
                4000
            )

    # -------------- Render ----------------------
    def _render_trials(self, td: TrialDataset):
        self._log("_render_trials: enter")
        
        if self.vtk_view is None:
            self._log("  vtk_view no inicializado → ensure_vtk()")
            self._ensure_vtk()
        if self.vtk_view is None:
            self._log("  sin VTK view, abort")
            return

        table = trials_matrix_to_vtk_table(td.time_rel, td.trials)
        
        scene = self.vtk_view.GetScene()
        scene.ClearItems()
        self.chart = vtk.vtkChartXY()
        scene.AddItem(self.chart)

        Ns, T = td.trials.shape
        sel = sorted({i for i in self.visible_trials if 0 <= i < T})
        if not sel:
            sel = [1] if T > 1 else ([0] if T == 1 else [])

        for idx in sel:
            plot = self.chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, idx + 1)
            plot.SetWidth(1.0)
            plot.SetLabel(f"Trial {idx+1}")

        ax_b = self.chart.GetAxis(vtk.vtkAxis.BOTTOM)
        ax_l = self.chart.GetAxis(vtk.vtkAxis.LEFT)
        ax_b.SetGridVisible(True); ax_l.SetGridVisible(True)
        ax_b.SetTitle("Time (s)")
        ax_l.SetTitle(td.unit or "Amplitude")
        
        ch_name = getattr(td, "channel_name", "") or "channel"
        trials_txt = ", ".join(str(i+1) for i in sel)
        self.chart.SetTitle(f"Trial {trials_txt} — {ch_name}")
        
        try:
            self.vtk_view.GetRenderWindow().Render()
            self._log("  render OK (ContextView interactivo)")
        except Exception as e:
            self._log("Render error:", e)
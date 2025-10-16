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
            "isi": None
        }

        self.widget: QWidget | None = None
        self.VtkViewer: QFrame | None = None
        self.vtk_widget: QVTKRenderWindowInteractor | None = None
        self.renwin = None

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

    def process(self, data: any):
        self._log(f"process{data}")
        self._populate_channels_once()

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

            #Botones para navegar entre trials
            self.ui.Btn_prev_trial.clicked.connect(lambda: self.navigate_trial(-1))
            self.ui.Btn_next_trial.clicked.connect(lambda: self.navigate_trial(1))
        else:
            self.widget.setParent(parent)

        return self.widget

    def _ensure_vtk(self):
        self._log("_ensure_vtk")
        frame = self.ui.VtkViewer
        if frame.layout() is None:
            frame.setLayout(QVBoxLayout(frame))
            frame.layout().setContentsMargins(0, 0, 0, 0)

        self.vtk_widget = QVTKRenderWindowInteractor(frame)
        frame.layout().addWidget(self.vtk_widget)

        self.renwin = self.vtk_widget.GetRenderWindow()
        self.renwin.SetMultiSamples(0)
        QtCore.QTimer.singleShot(0, self._init_interactor)

    def _init_interactor(self):
        self._log("_init_interactor")
        try:
            iren = self.renwin.GetInteractor()
            if iren and not iren.GetInitialized():
                iren.Initialize()
        except Exception as e:
            self._log("_init_interactor error:", e)

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
        self.ui.interStimTimeDoubleSpinBox.setValue(self.params["isi"] or 0.0)

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
        isi  = float(self.ui.interStimTimeDoubleSpinBox.value())
        isi  = None if isi <= 0 else isi

        if mode == "fixed" and not (t1 > t0):
            QMessageBox.warning(self.widget, "Parámetros", "t1 debe ser mayor que t0.")
            return

        self._log("params →", dict(channel=int(ch), threshold=th, t0=t0, t1=t1,
                                end_mode=mode, stim_expected=stim, isi=isi))

        # Ejecutar corte
        try:
            td: TrialDataset = cut_trials_single_channel(
                ds=ds, channel=int(ch), threshold=th, t0=t0, t1=t1,
                end_mode=mode, stim_expected=stim, isi=isi
            )
        except Exception as e:
            self._log("cut_trials_single_channel error:", e)
            QMessageBox.critical(self.widget, "Error",
                                f"Falló la generación de trials:\n{e}")
            return

        self._log("TD listo:", td.trials.shape, td.time_rel.shape, "onsets:", len(td.onsets_s))

        try:
            ds.add_trial_dataset(td)
            ds.discarded_trials.clear()
        except Exception as e:
            self._log("add_trial_dataset warning:", e)

        #Se muestra solo el primer trial
        self.last_td = td
        self.navigate_trial(0)

        if self.mainwin:
            self.mainwin.statusBar().showMessage(
                f"Trials: T={td.trials.shape[1]}, Ns={td.trials.shape[0]}, canal='{td.channel_name}'",
                4000
            )

    # -------------- Navegación entre trials ----------------------
    def navigate_trial(self, direction: int):
        """
        Muestra el siguiente o anterior trial según 'direction'.
        direction = +1 → siguiente
        direction = -1 → anterior
        """
        if not self.last_td:
            QMessageBox.information(self.widget, "Navegación", "No hay trials cargados.")
            return

        td = self.last_td
        sd = self._get_active_signal()
        
        _, T = td.trials.shape
        if T == 0:
            QMessageBox.information(self.widget, "Navegación", "No hay trials disponibles.")
            return

        if not self.visible_trials:
            self.visible_trials = [0]

        current = self.visible_trials[0]
        new_idx = (current + direction) % T  # navegación circular
        self.visible_trials = [new_idx]

        self._log(f"Navegando trial {new_idx + 1}/{T}")
        self._render_trials(td)

        # Actualizar el label del trial actual
        if new_idx in sd.discarded_trials:
            self.ui.currentTrialLabel.setText(f"Trial actual: {new_idx + 1} (descartado)/{T}")
            self.ui.currentTrialLabel.setStyleSheet("color: red; font-weight: bold;")
            self.ui.Btn_discard_trial.setText("Include")
        else:
            self.ui.currentTrialLabel.setText(f"Trial actual: {new_idx + 1}/{T}")
            self.ui.currentTrialLabel.setStyleSheet("color: black; font-weight: bold;")
            self.ui.Btn_discard_trial.setText("Discard")

            # Conectar solo una vez
            try:
                self.ui.Btn_discard_trial.clicked.disconnect()
            except Exception:
                pass
            self.ui.Btn_discard_trial.clicked.connect(lambda _, idx=new_idx: self._on_discard_trial(idx))


        # Feedback en barra de estado
        if self.mainwin:
            self.mainwin.statusBar().showMessage(
                f"Trial {new_idx + 1} de {T}", 2000
            )


    def _on_discard_trial(self, index: int):

        ds = self._get_active_signal()

        """Alterna el estado de descarte del trial actual (añadir o remover de la lista del SignalDataset)."""
        if not self.last_td:
            QMessageBox.information(self.widget, "Descartar Trial", "No hay trials cargados.")
            return
        
        if not ds:
            QMessageBox.warning(self.widget, "Descartar Trial", "No se encontró la señal activa.")
            return
      
        if not self.visible_trials:
            QMessageBox.information(self.widget, "Descartar Trial", "No hay trial seleccionado.")
            return

        # current = self.visible_trials[0]


        # Alternar descarte / inclusión
        if index in ds.discarded_trials:
            # ➕ Incluir nuevamente
            ds.discarded_trials.discard(index)
            self._log(f"Trial {index + 1} incluido nuevamente.")
            self.ui.currentTrialLabel.setText(f"Trial actual: {index + 1}")
            self.ui.currentTrialLabel.setStyleSheet("color: black; font-weight: bold;")
            self.ui.Btn_discard_trial.setText("🗑️ Discard Trial")
            QMessageBox.information(
                self.widget,
                "Trial incluido",
                f"El trial {index + 1} ha sido incluido nuevamente."
            )
        else:
            # 🚫 Marcar como descartado
            ds.discarded_trials.add(index)
            self._log(f"Trial {index + 1} marcado como descartado.")
            self.ui.currentTrialLabel.setText(f"Trial actual: {index + 1} (descartado)")
            self.ui.currentTrialLabel.setStyleSheet("color: red; font-weight: bold;")
            self.ui.Btn_discard_trial.setText("Include")
            QMessageBox.information(
                self.widget,
                "Trial descartado",
                f"El trial {index + 1} ha sido descartado y no se tendrá en cuenta."
            )

    # -------------- Render ----------------------
    def _render_trials(self, td: TrialDataset):
        self._log("_render_trials: enter")
        if not self.renwin:
            self._log("  sin render window")
            return

        if not self.renwin.GetMapped():
            self._log("  RW no mapeada aún → retry")
            QtCore.QTimer.singleShot(0, lambda: self._render_trials(td))
            return

        self.renwin.GetRenderers().RemoveAllItems()

        table = trials_matrix_to_vtk_table(td.time_rel, td.trials)
        colors = vtk.vtkNamedColors()

        renderer = vtk.vtkRenderer()
        renderer.SetBackground(colors.GetColor3d("WhiteSmoke"))
        self.renwin.AddRenderer(renderer)

        chart = vtk.vtkChartXY()
        scene = vtk.vtkContextScene()
        actor = vtk.vtkContextActor()
        scene.AddItem(chart)
        actor.SetScene(scene)
        renderer.AddActor(actor)
        scene.SetRenderer(renderer)

        Ns, T = td.trials.shape
        sel = sorted({i for i in self.visible_trials if 0 <= i < T})
        if not sel:
            sel = [1] if T > 1 else ([0] if T == 1 else [])

        for idx in sel:
            plot = chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, idx + 1)  # 0=time, (idx+1)=trial idx
            plot.SetWidth(0.5)

        chart.GetAxis(0).SetTitle("Time (s)")
        chart.GetAxis(1).SetTitle(td.unit or "Amplitude")

        try:
            self.renwin.Render()
            self._log("  render OK")
        except Exception as e:
            self._log("Render error:", e)
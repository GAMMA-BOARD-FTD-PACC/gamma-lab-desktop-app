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
            "threshold": 0.8,
            "t0": -0.05,
            "t1": 4.0,
            "stim_count": 1,  
            "isi": None          
        }

        self.widget: QWidget | None = None
        self.VtkViewer: QFrame | None = None
        self.vtk_widget: QVTKRenderWindowInteractor | None = None
        self.renwin = None

        self.signalComboBox: QComboBox | None = None
        self.channelSpinBox: QSpinBox | None = None
        self.stimNumberSpinBox: QSpinBox | None = None
        self.thresholdDoubleSpinBox: QDoubleSpinBox | None = None
        self.initialTimeDoubleSpinBox: QDoubleSpinBox | None = None
        self.finalTimeDoubleSpinBox: QDoubleSpinBox | None = None
        self.interStimTimeDoubleSpinBox: QDoubleSpinBox | None = None
        self.Btn_generate_trials: QPushButton | None = None
        
        self.visible_trials = []
        self.last_td = None

    def initialize(self, kernel): self.kernel = kernel

    def start(self, kernel):
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
    def stop(self):
        print("[TrialsPlugin] stop")

    
    def get_widget(self, parent=None):
        if self.widget is None:
            self.ui = Ui_Trials(parent)
            self.widget = self.ui  

            self._ensure_vtk()
            self.ui.Btn_generate_trials.clicked.connect(self._on_generate_clicked)

            self._init_controls()
            self._populate_from_raw()

        else:
            self.widget.setParent(parent)

        self._populate_from_raw()
        return self.widget
    

    def process(self, data: any):
        #Actualizar el combobox al cargar nuevas señales
        self._populate_from_raw()
        print(f"UIPlugin recibió datos: {data}")
        
    def _ensure_vtk(self):
        """Monta el QVTK en el frame de la UI y difiere la inicialización del interactor."""
        frame = self.ui.VtkViewer
        if frame.layout() is None:
            frame.setLayout(QVBoxLayout(frame))
            frame.layout().setContentsMargins(0,0,0,0)

        self.vtk_widget = QVTKRenderWindowInteractor(frame)
        frame.layout().addWidget(self.vtk_widget)

        self.renwin = self.vtk_widget.GetRenderWindow()
        self.renwin.SetMultiSamples(0)
        QtCore.QTimer.singleShot(0, self._init_interactor)
    
    def _populate_from_raw(self):
        
        """
        Llena el combobox con las señales crudas disponibles en el DataStore.
        Si no hay señales, se agrega un item "No hay señales cargadas".
        Luego se ajustan los rangos del canal según la primera señal cargada.
        """

        store: DataStore = self.kernel.get_service("DataStore")
        if not store:
            return
        
        #Obtener las señales crudas del DataStore
        all_signals =store.get_signals()
        self.ui.signalComboBox.clear()

        print(all_signals)

        if not all_signals:
            self.ui.signalComboBox.addItem("No hay señales cargadas", None)
            return
        
        #llenar el combo box con las señales disponibles
        for key, ds in all_signals.items():
            label = f"{key}"
            self.ui.signalComboBox.addItem(label, key)

        self.ui.signalComboBox.setCurrentIndex(0)

        ds: SignalDataset | None = store.get("raw", None)
        
         # Ajustar los rangos del canal según la primera señal
        first_key = self.ui.signalComboBox.currentData()
        if first_key:
            ds = store.get(first_key)
            if ds:
                C = ds.signals.shape[0]
                self.ui.channelSpinBox.setRange(0, max(0, C - 1))


    def _init_interactor(self):
        try:
            iren = self.renwin.GetInteractor()
            if iren and not iren.GetInitialized():
                iren.Initialize()
        except Exception as e:
            print("[TrialsPlugin] _init_interactor error:", e)

    def _post_show_check(self):
        print("[TrialsPlugin] visible:",
              bool(self._root and self._root.isVisible()),
              "vtk:", bool(self.vtk_widget))

    def _init_controls(self):
        self.ui.signalComboBox.setToolTip("Seleccionar la señal a procesar.")

        self.ui.channelSpinBox.setRange(0, 50)
        self.ui.channelSpinBox.setValue(self.params["channel"])
        self.ui.channelSpinBox.setToolTip("Seleccionar el canal de la señal a procesar.")


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

    # ====== Acción UI ======
    def _on_generate_clicked(self):
        self._run_generate()


    def _run_generate(self):
        store: DataStore = self.kernel.get_service("DataStore")
        selected_key = self.ui.signalComboBox.currentData()
        if not selected_key:
            QMessageBox.warning(self.widget, "Selección", "No hay señal seleccionada.")
            return

        ds: SignalDataset | None = store.get(selected_key, None)
        if ds is None:
            if self.mainwin:
                QMessageBox.warning(self.widget, "Error", f"No se encontró la señal '{selected_key}'.")
                self.mainwin.statusBar().showMessage("No hay señal cargada ('raw')", 4000)
            return None
        
        # Registrar la señal como la activa en el DataStore
        try:
            store.set_active_signal(selected_key)
            print(f"[TrialsPlugin] Señal activa establecida: '{selected_key}'")
        except ValueError as e:
            print(f"[TrialsPlugin] No se pudo establecer la señal activa: {e}")

        ch   = int(self.ui.channelSpinBox.value())
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
        
        td: TrialDataset = cut_trials_single_channel(
            ds=ds, channel=ch, threshold=th, t0=t0, t1=t1, end_mode=mode, stim_expected=stim, isi=isi
        )
        
        
        print(f"[DEBUG] TrialDataset generado → shape={td.trials.shape}, "
          f"time_rel={td.time_rel.shape}, "
          f"onsets={len(td.onsets_s)}")
        
        #Agregar el trial generado a la señal cruda y al DataStore
        ds.add_trial_dataset(td)

        self.last_td = td
        T = td.trials.shape[1]
        self.visible_trials = [1] if T > 0 else []
        # Render
        self._render_trials(td)

        if self.mainwin:
            self.mainwin.statusBar().showMessage(
                f"Trials: T={td.trials.shape[1]}, Ns={td.trials.shape[0]}, canal='{td.channel_name}'",
                4000
            )
        return td

    # ====== Render VTK ======
    def _render_trials(self, td: TrialDataset):
        if not self.renwin:
            return

        if not self.renwin.GetMapped():
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

        # Ejes de la gráfica
        chart.GetAxis(0).SetTitle("Time (s)")
        chart.GetAxis(1).SetTitle(td.unit or "Amplitude")

        try:
            self.renwin.Render()
        except Exception as e:
            print("[TrialsPlugin] Render error:", e)
from pathlib import Path
import sys
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QWidget, QComboBox, QVBoxLayout, QFormLayout, QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QFrame, QMessageBox
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
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
            "inter_stim_time": 0.1
        }

        self.widget: QWidget | None = None
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None
        self.chart: vtk.vtkChartXY | None = None

        self.visible_trials = []
        self.last_td: TrialDataset | None = None
        self._active_ds: SignalDataset | None = None
        
        self.vtk_menu: VTKContextMenu | None = None

    # ---------------- Logs ----------------
    def _log(self, *args):
        # print("[TRIALS]", *args)
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
        
        if self.vtk_menu is None:
            base_scope = {
                "view_id": "trials",
                "trial_id": None,
                "channel_name": None,
                "plugin": "trials",
                "domain": "time",
                "graph_id": "trials:blank"
            }
            self.vtk_menu = VTKContextMenu(
                chart=None,
                vtk_widget=self.vtk_interactor,
                plugin_name="trials",
                measurements_enabled=True,
                measure_scope=base_scope,
                parent=self.widget
            )
            self.vtk_menu.set_datastore(self.kernel.get_service("DataStore"))
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

        self.ui.interStimTimeDoubleSpinBox.setDecimals(6)
        self.ui.interStimTimeDoubleSpinBox.setSingleStep(0.01)
        self.ui.interStimTimeDoubleSpinBox.setValue(self.params["inter_stim_time"] or 0.0)
        
        self.ui.stimNumberSpinBox.valueChanged.connect(self._on_stim_count_changed)
        self._apply_interstim_ui_rules(self.ui.stimNumberSpinBox.value())

    
    def _on_stim_count_changed(self, val: int):
        """Callback cuando cambia el número de estímulos: aplica reglas al campo de ISI."""
        try:
            self._apply_interstim_ui_rules(int(val))
        except Exception as e:
            self._log("_on_stim_count_changed error:", e)
        
    def _apply_interstim_ui_rules(self, stim_count: int):
        """
        - stim_count <= 1: deshabilitar ISI y ponerlo en 0.0
        - stim_count >= 2: habilitar ISI, exigir > 0 (mínimo sugerido 1 ms)
        """
        isi = self.ui.interStimTimeDoubleSpinBox

        if stim_count is None or stim_count <= 1:
            isi.blockSignals(True)
            isi.setEnabled(False)
            isi.setMinimum(0.0)
            isi.setValue(0.0)
            isi.setToolTip("Inter-stim time no aplica cuando hay 0 ó 1 estímulo por trial.")
            isi.blockSignals(False)
            return

        # stim_count >= 2
        isi.blockSignals(True)
        isi.setEnabled(True)
        isi.setMinimum(0.001)
        if isi.value() <= 0.0:
            isi.setValue(0.1)
        isi.setToolTip("Tiempo entre estímulos (s). Debe ser > 0 cuando hay ≥2 estímulos por trial.")
        isi.blockSignals(False)
        
    def _get_active_signal(self) -> SignalDataset | None:
        """Devuelve la señal activa"""
        try:
            store: DataStore | None = self.kernel.get_service("DataStore")
            ds = store.get_active_signal() if store else None
            self._active_ds = ds
            self._log("_get_active_signal:", "ok" if ds else "None")
            return ds
        except Exception as e:
            self._log("_get_active_signal error:", e)
            return None


    def _populate_channel_combos(self, ds: SignalDataset):
        """
        Llena channelComboBox y stimChannelComboBox con los mismos nombres (userData = índice).
        - Channel → por defecto índice 0
        - Stim Channel → por defecto último canal
        """
        # Obtener referencias (tolerante si UI no tiene todavía el stim combo)
        cb_main = getattr(self.ui, "channelComboBox", None)
        cb_stim = getattr(self.ui, "stimChannelComboBox", None)

        if cb_main is None:
            return  # nada que hacer

        # Construir lista de nombres
        names = []
        try:
            if getattr(ds, "channel_names", None):
                names = [str(n) for n in ds.channel_names]
        except Exception as e:
            self._log("channel_names error:", e)

        if not names:
            # Fallback por shape
            C = 0
            try:
                sig = getattr(ds, "signals", None)
                C = int(sig.shape[0]) if sig is not None else 0
            except Exception:
                C = 0
            names = [f"ch-{i+1}" for i in range(C)]
            self._log("fallback nombres por shape:", len(names))

        # Poblar principal
        cb_main.blockSignals(True)
        cb_main.clear()
        for i, name in enumerate(names):
            cb_main.addItem(name, i)
        cb_main.setCurrentIndex(0 if names else -1)
        cb_main.blockSignals(False)

        # Poblar stim (si existe en UI)
        if cb_stim is not None:
            cb_stim.blockSignals(True)
            cb_stim.clear()
            for i, name in enumerate(names):
                cb_stim.addItem(name, i)
            # por defecto el ÚLTIMO canal
            default_idx = (len(names) - 1) if names else -1
            cb_stim.setCurrentIndex(default_idx)
            cb_stim.setToolTip("Canal usado para detectar onsets/estímulos")
            cb_stim.blockSignals(False)


    def _populate_channels_once(self):
        """Intenta cargar la señal activa y poblar el combo (silencioso si no hay)."""
        ds = self._get_active_signal()
        if ds:
            self._populate_channel_combos(ds)
        else:
            self._log("_populate_channels_once: no hay señal activa (aún)")
    
    # -------------- Acciones UI -----------------
    def _on_generate_clicked(self):
        #self._log("_on_generate_clicked")

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
        
        stim_ch = self.ui.stimChannelComboBox.currentData()
        if stim_ch is None:
            stim_ch = self.ui.stimChannelComboBox.currentIndex()
        if stim_ch is None or stim_ch < 0:
            QMessageBox.warning(self.widget, "Parámetros",
                                "Seleccione un canal de estímulos.")
            return

        th   = float(self.ui.thresholdDoubleSpinBox.value())
        t0   = float(self.ui.initialTimeDoubleSpinBox.value())
        t1   = float(self.ui.finalTimeDoubleSpinBox.value())
        mode = self.ui.endModeCombo.currentData() or "fixed"
        stim = int(self.ui.stimNumberSpinBox.value())
        stim = None if stim < 0 else stim
        inter_stim_time  = float(self.ui.interStimTimeDoubleSpinBox.value())
        inter_stim_time  = None if inter_stim_time <= 0 else inter_stim_time

        if mode == "fixed" and not (t1 > t0):
            QMessageBox.warning(self.widget, "Parámetros", "t1 debe ser mayor que t0.")
            return

        self._log("params →", dict(channel=int(ch), threshold=th, t0=t0, t1=t1,
                                end_mode=mode, stim_expected=stim, inter_stim_time=inter_stim_time))

        print("")
        try:
            td = cut_trials_single_channel(
            ds=ds,
            channel=int(ch),                  # canal objetivo a cortar
            stim_channel=None if stim_ch is None else int(stim_ch),  # canal de estímulos para detectar onsets
            threshold=th,
            t0=t0, t1=t1,
            end_mode=mode,
            stim_expected=stim,
            inter_stim_time=inter_stim_time
        )
        except Exception as e:
            self._log("cut_trials_single_channel error:", e)
            QMessageBox.critical(self.widget, "Error",
                                f"Falló la generación de trials:\n{e}")
            return

        #self._log("TD listo:", td.trials.shape, td.time_rel.shape, "onsets:", len(td.onsets_s))

        try:
            ds.add_trial_dataset(td)
            ds.clear_discarded_trials()
            
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

        #self._log(f"Navegando trial {new_idx + 1}/{T}")
        self._render_trials(td)

        self._update_trial_ui(sd, new_idx, T, None)

        # Conectar el botón
        try:
            self.ui.Btn_discard_trial.clicked.disconnect()
        except Exception:
            pass
        self.ui.Btn_discard_trial.clicked.connect(lambda _, idx=new_idx: self._on_discard_trial(idx, T))

        
        # Feedback en barra de estado
        if self.mainwin:
            self.mainwin.statusBar().showMessage(
                f"Trial {new_idx + 1} de {T}", 2000
            )


    def _on_discard_trial(self, index: int, T: int):

        ds = self._get_active_signal()
        ch = self.ui.channelComboBox.currentText()

        """Alterna el estado de descarte del trial actual (añadir o remover de la lista del SignalDataset)."""
        if not self.last_td:
            QMessageBox.warning(self.widget, "Descartar Trial", "No hay trials cargados.")
            return
        
        if not ds:
            QMessageBox.warning(self.widget, "Descartar Trial", "No se encontró la señal activa.")
            return
      
        if not self.visible_trials:
            QMessageBox.warning(self.widget, "Descartar Trial", "No hay trial seleccionado.")
            return

        estado = ds.is_trial_discarded(ds.name, ch, index)
        print(f"Trial {index + 1} descartado: {estado}")

        if estado:
            # Incluir nuevamente
            ds.include_trial(ds.name, ch, index)
            self._update_trial_ui(ds, index, T, False)
            QMessageBox.information(
                self.widget,
                "Trial incluido",
                f"El trial {index + 1} ha sido incluido nuevamente."
            )
        else:
            # Marcar como descartado
            ds.discard_trial(ds.name, ch, index)
            self._update_trial_ui(ds, index, T, True)

            QMessageBox.information(
                self.widget,
                "Trial descartado",
                f"El trial {index + 1} ha sido descartado y no se tendrá en cuenta."
            )
    

    def _update_trial_ui(self, ds: SignalDataset, index: int, total: int = None, estado_descartado: bool = None):
        """Actualiza el label y botón del trial actual según si está descartado."""
        total_text = f"/{total}" if total else ""
        ch = self.ui.channelComboBox.currentText()

        if estado_descartado is None:
            estado_descartado = ds.is_trial_discarded(ds.name, ch, index)

        if estado_descartado:
            self.ui.currentTrialLabel.setText(f"Trial actual: {index + 1} (descartado){total_text}")
            self.ui.currentTrialLabel.setStyleSheet("color: red; font-weight: bold;")
            self.ui.Btn_discard_trial.setText("Include")
        else:
            self.ui.currentTrialLabel.setText(f"Trial actual: {index + 1}{total_text}")
            self.ui.currentTrialLabel.setStyleSheet("color: black; font-weight: bold;")
            self.ui.Btn_discard_trial.setText("Discard")

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
            
        if self.vtk_menu is not None:
            self.vtk_menu.set_chart(self.chart)
            ds = self._get_active_signal()
            signal_name = getattr(ds, "name", "signal")
            trial_idx = (self.visible_trials[0] if self.visible_trials else 0)

            curr_channel_name = getattr(td, "channel_name", "") or "channel"

            graph_uid = f"trials:{signal_name}:{curr_channel_name}"

            self.vtk_menu.on_view_rebuilt(
                self.chart,
                view_id="trials",
                trial_id=trial_idx,
                channel_name=curr_channel_name,
                plugin="trials",
                domain="time",
                graph_id=graph_uid
            )
# plugins/io/open_signal/open_signal_plugin.py
from pathlib import Path
from PyQt5.QtWidgets import QMessageBox
import traceback

from PyQt5 import QtCore, QtWidgets
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
from core.services.data_store import DataStore
from core.services.fileio import FileIOService
from core.services.signal_dataset import SignalDataset
from core.vtk_adapters.adapters import dataset_to_vtk_table

from plugins.io.open_signal.open_signal_ui import Ui_OpenSignal


class OpenSignalPlugin(IPlugin):
    MAX_CHANNELS_VISIBLE = 3

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None

        self.ui: Ui_OpenSignal | None = None
        self.vtk_interactor: QVTKRenderWindowInteractor | None = None
        self.vtk_view: vtk.vtkContextView | None = None

        self.current_ds: SignalDataset | None = None
        self._block_item_changed = False

        self._charts: list[vtk.vtkChartXY] = []
        self._vtk_table = None

    # ---------------- utils/log ----------------
    def _log(self, *args):
        print("[OpenSignal]", *args)

    def initialize(self, kernel):
        self.kernel = kernel
        self._log("initialize:", self.name())

    def start(self, kernel):
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        self._log("start")

    def stop(self):
        if self.vtk_interactor:
            self.vtk_interactor.Disable()

    def process(self, data: any):
        """Restaura renderización y vuelve a activar interacción."""
        if self.vtk_interactor:
            self.vtk_interactor.Enable()

    def get_widget(self, parent=None):
        if self.ui is None:
            self.ui = Ui_OpenSignal(parent)
            self._ensure_vtk()

            self.ui.Btn_abrir_senal.clicked.connect(self._on_open_clicked)
            self.ui.listChannels.itemChanged.connect(self._on_channel_item_changed)

            if hasattr(self.ui, "splitter"):
                self.ui.splitter.splitterMoved.connect(lambda *_: self._relayout_charts())

            store: DataStore | None = self.kernel.get_service("DataStore")
            if store and store.get_active_signal() is not None:
                self._set_dataset(store.get_active_signal())
        else:
            self.ui.setParent(parent)
        return self.ui

    def _ensure_vtk(self):
        """Embeddear un QVTKRenderWindowInteractor y usar vtkContextView (charts)."""
        self._log("ensure_vtk(): enter")

        container = self.ui.vtkContainer
        if container.layout() is None:
            lay = QtWidgets.QVBoxLayout(container)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)

        self.vtk_interactor = QVTKRenderWindowInteractor(container)
        container.layout().addWidget(self.vtk_interactor)
        self._log("ensure_vtk(): interactor embebido")

        _orig_resize = self.vtk_interactor.resizeEvent
        def _resize_wrapper(ev):
            _orig_resize(ev)              
            self._relayout_charts()        
        self.vtk_interactor.resizeEvent = _resize_wrapper  

        self.vtk_view = vtk.vtkContextView()
        self.vtk_view.SetRenderWindow(self.vtk_interactor.GetRenderWindow())
        self.vtk_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        # Crear menú contextual (sin chart al inicio)
        try:
            self.vtk_menu = VTKContextMenu(None, self.vtk_interactor, plugin_name=self.meta.id, parent=self.ui)
        except Exception as e:
            self.vtk_menu = None
            QMessageBox.information(self.ui, "Menú contextual", "Error creando el menú contextual.\n" + str(e))


        try:
            self.vtk_interactor.Initialize()
        except Exception:
            pass
        self._log("ensure_vtk(): scheduled init")

    # ---------------- archivo / datos ----------------
    def _on_open_clicked(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.ui,
            "Seleccionar archivo de señal",
            "",
            "Señales (*.abf *.edf *.ebf *.mat);;Archivos ABF (*.abf);;Archivos EDF (*.edf);;Archivos EBF (*.ebf);;Archivos MAT (*.mat)"
        )
        if not fname:
            return

        fileio: FileIOService | None = self.kernel.get_service("FileIO")
        if fileio is None:
            fileio = FileIOService()
            self.kernel.register_service("FileIO", fileio)

        ext = Path(fname).suffix.lower()
        try:
            if ext == ".abf":
                ds = fileio.load_abf(fname)
            elif ext == ".edf":
                ds = fileio.load_edf(fname)
            elif ext == ".mat":
                ds = fileio.load_mat(fname)
            else:
                if self.mainwin:
                    self.mainwin.statusBar().showMessage(f"Formato no soportado: {ext}", 4000)
                return
        except Exception as e:
            QMessageBox.warning(self.ui, "Error", f"Error abriendo el archivo {fname}\n{e}.")
            self._log("_on_open_clicked error:", e)
            traceback.print_exc()
            return

        store: DataStore | None = self.kernel.get_service("DataStore")
        if store is None:
            store = DataStore()
            self.kernel.register_service("DataStore", store)

        key = store.add_signal(ds, ds.name)
        self._log("Guardado en DataStore:", key)
        self.kernel.emit_event("signal_added", {"key": key})
        store.set_active_signal(key)

        self._set_dataset(ds)

        self.vtk_menu.set_signal_name(ds.name)

        if self.mainwin:
            self.mainwin.statusBar().showMessage(f"Cargado: {fname}", 4000)

    def _set_dataset(self, ds: SignalDataset):
        self.current_ds = ds
        self._populate_channel_list(ds)
        self._vtk_table = dataset_to_vtk_table(ds)
        self._render_selected()

    def _populate_channel_list(self, ds: SignalDataset):
        lw = self.ui.listChannels
        self._block_item_changed = True
        lw.clear()

        names = list(ds.channel_names) if getattr(ds, "channel_names", None) else [
            f"ch-{i+1}" for i in range(ds.signals.shape[0])
        ]
        for i, name in enumerate(names):
            it = QtWidgets.QListWidgetItem(name)
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked if i < self.MAX_CHANNELS_VISIBLE else QtCore.Qt.Unchecked)
            it.setData(QtCore.Qt.UserRole, i)
            lw.addItem(it)

        self._block_item_changed = False

    def _checked_indices(self):
        out = []
        lw = self.ui.listChannels
        for i in range(lw.count()):
            it = lw.item(i)
            if it.checkState() == QtCore.Qt.Checked:
                out.append(int(it.data(QtCore.Qt.UserRole)))
        return out

    def _on_channel_item_changed(self, item: QtWidgets.QListWidgetItem):
        if self._block_item_changed:
            return
        checked = self._checked_indices()
        if len(checked) > self.MAX_CHANNELS_VISIBLE:
            self._block_item_changed = True
            item.setCheckState(QtCore.Qt.Unchecked)
            self._block_item_changed = False
            if self.mainwin:
                self.mainwin.statusBar().showMessage(f"Máximo {self.MAX_CHANNELS_VISIBLE} canales visibles.", 2500)
            return
        self._render_selected()

    # ---------------- layout helpers ----------------
    def _relayout_charts(self):
        """Reposiciona charts con separación suficiente para que se vean los ejes."""
        if not self.vtk_view or not self._charts:
            return

        rw = self.vtk_view.GetRenderWindow()
        w, h = rw.GetSize()
        if w <= 0 or h <= 0:
            return

        left_margin, right_margin = 8, 8
        top_margin, bottom_margin = 10, 12
        gap = 40            # espacio entre charts
        min_row_h = 150

        rows = len(self._charts)
        inner_h = max(1, h - top_margin - bottom_margin - gap * (rows - 1))
        row_h = max(min_row_h, inner_h // rows)

        y = float(h - top_margin - row_h)
        for chart in self._charts:
            chart.SetAutoSize(False)
            chart.SetSize(vtk.vtkRectf(
                float(left_margin),
                float(y),
                float(w - left_margin - right_margin),
                float(row_h)
            ))
            y -= (row_h + gap)

        for chart in self._charts:
            ax_b = chart.GetAxis(vtk.vtkAxis.BOTTOM)
            ax_b.SetLabelsVisible(True)
            ax_b.SetTitle("Time (s)")

        rw.Render()

    def _render_selected(self):
        if self.current_ds is None or self.vtk_view is None:
            return

        ds = self.current_ds
        scene = self.vtk_view.GetScene()
        scene.ClearItems()
        self._charts.clear()

        

        sel = self._checked_indices()
        if not sel:
            self.vtk_view.GetRenderWindow().Render()
            return

        table = self._vtk_table if self._vtk_table is not None else dataset_to_vtk_table(ds)

        for ch in sel:
            chart = vtk.vtkChartXY()
            scene.AddItem(chart)
            self._charts.append(chart)

            plot = chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, ch + 1)
            plot.SetWidth(0.8)

            name = ds.channel_names[ch] if ch < len(ds.channel_names) else f"ch{ch}"
            chart.SetTitle(name)

            ax_b = chart.GetAxis(vtk.vtkAxis.BOTTOM)
            ax_l = chart.GetAxis(vtk.vtkAxis.LEFT)
            ax_b.SetGridVisible(True)
            ax_l.SetGridVisible(True)

            # Mostrar labels y título de X en todos
            ax_b.SetLabelsVisible(True)
            ax_b.SetTitle("Time (s)")

            unit = "Amplitude"
            if ch < len(ds.units) and ds.units[ch]:
                unit = ds.units[ch]
            ax_l.SetTitle(unit)

        self._relayout_charts()

        if self.vtk_menu and self._charts:
            # Por ahora usamos el primer chart visible
            self.vtk_menu.set_chart(self._charts)

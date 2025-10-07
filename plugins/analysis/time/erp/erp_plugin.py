import os
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QListWidgetItem
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import numpy as np

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from plugins.analysis.time.erp.erp_plugin_ui import Ui_ErpPlot

class Erp_plugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.td = None
        self.started = False
        
        # VTK widgets
        self.vtk_top: QVTKRenderWindowInteractor | None = None
        self.vtk_bot: QVTKRenderWindowInteractor | None = None
        self.view_top: vtk.vtkContextView | None = None
        self.view_bot: vtk.vtkContextView | None = None
        
        self.time: np.ndarray | None = None            # (T,)
        self.matrix: np.ndarray | None = None          # (N_trials, T)
        self.N_trials: int = 0

    def initialize(self, kernel):
        self.kernel = kernel
        print("Inicializando ERP")

    def process(self, data: any):
        print(f"ERP recibió datos: {data}")
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(f"ERP procesó: {data}", 3000)
            except Exception:
                pass

    def start(self, kernel):
        print("Iniciando ERP")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("ERP tiene acceso a MainWindow")        

    def stop(self):
        print("[TrialsPlugin] stop")
        self.mainwin = None
    
    def get_widget(self, parent=None):
        if self.widget is None:
            self.ui = Ui_ErpPlot(parent)
            self.widget = self.ui
            self.ensure_vtk()
            self._wire_ui()
            self._populate_trials_list()
        else:
            self.widget.setParent(parent)
        return self.widget

    def ensure_vtk(self):
        # Top (butterfly)
        self.vtk_top = QVTKRenderWindowInteractor(self.ui.butterflyPlot)
        self.ui.butterflyPlot.setLayout(QtWidgets.QVBoxLayout())
        self.ui.butterflyPlot.layout().setContentsMargins(0, 0, 0, 0)
        self.ui.butterflyPlot.layout().addWidget(self.vtk_top)

        self.view_top = vtk.vtkContextView()
        self.view_top.SetRenderWindow(self.vtk_top.GetRenderWindow())
        self.view_top.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        # Bottom (heatmap)
        self.vtk_bot = QVTKRenderWindowInteractor(self.ui.heatmapPlot)
        self.ui.heatmapPlot.setLayout(QtWidgets.QVBoxLayout())
        self.ui.heatmapPlot.layout().setContentsMargins(0, 0, 0, 0)
        self.ui.heatmapPlot.layout().addWidget(self.vtk_bot)

        self.view_bot = vtk.vtkContextView()
        self.view_bot.SetRenderWindow(self.vtk_bot.GetRenderWindow())
        self.view_bot.GetRenderer().SetBackground(0.98, 0.98, 0.98)

        # Inicializa interactores (evita errores en algunos SO)
        try:
            self.vtk_top.Initialize()
            self.vtk_bot.Initialize()
        except Exception:
            pass
    
    def _wire_ui(self):
        self.ui.btnPlot.clicked.connect(self._on_plot_clicked)
        self.ui.spnFrom.valueChanged.connect(self._sync_range)
        self.ui.spnTo.valueChanged.connect(self._sync_range)
        self.ui.txtFilter.textChanged.connect(self._apply_filter)
        
    def _populate_trials_list(self):
        # Si aún no hay dataset cargado, no sabemos N: no llenamos lista
        if self.N_trials <= 0:
            return

        self.ui.spnSingleTrial.setMaximum(self.N_trials)
        self.ui.spnFrom.setMaximum(self.N_trials)
        self.ui.spnTo.setMaximum(self.N_trials)
        if self.ui.spnTo.value() == 0:
            self.ui.spnTo.setValue(self.N_trials)

        self.ui.lstTrials.clear()
        for i in range(1, self.N_trials + 1):
            it = QListWidgetItem(f"Trial-{i}")
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked)
            it.setData(QtCore.Qt.UserRole, f"trial-{i}".lower())
            self.ui.lstTrials.addItem(it)

    # ========= Dataset =========
    def _load_dataset_from_store(self):
        """Busca 'trials_dataset' en el DataStore y extrae time y matrix."""
        if not self.mainwin:
            return

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            return

        ds = store.get("trials_dataset", None)
        if ds is None:
            print("No se encontró 'trials_dataset' en DataStore")
            return

        t, X = self._extract_trials_dataset(ds)
        if t is None or X is None:
            print("No se pudieron extraer datos del TrialDataset")
            return

        print(f"ERP cargó dataset con {X.shape[0]} trials y {X.shape[1]} muestras")

        self.time = t.astype(float, copy=False)
        self.matrix = X.astype(float, copy=False)
        self.N_trials = int(X.shape[0])

    @staticmethod
    def _extract_trials_dataset(ds):
        """
        Extrae los arreglos desde un TrialDataset.
        Esperado: ds.time_rel (Ns,) y ds.trials (Ns, T)
        """
        if ds is None:
            return None, None

        # Caso 1: TrialDataset con atributos
        if hasattr(ds, "trials") and hasattr(ds, "time_rel"):
            t = getattr(ds, "time_rel")
            X = getattr(ds, "trials")
            # Asegurarse de que trials esté orientado como (N_trials, N_samples)
            if X.shape[0] == t.size:
                X = X.T  # transponer si cada columna es un trial
            return t, X

        # Caso 2: dict (fallback)
        if isinstance(ds, dict):
            t = ds.get("time_rel") or ds.get("t") or ds.get("time")
            X = ds.get("trials") or ds.get("data")
            return t, X

        return None, None

    
    # ========= Helpers UI =========
    def _sync_range(self):
        if self.ui.spnFrom.value() > self.ui.spnTo.value():
            self.ui.spnTo.setValue(self.ui.spnFrom.value())

    def _select_none(self):
        for i in range(self.ui.lstTrials.count()):
            self.ui.lstTrials.item(i).setCheckState(QtCore.Qt.Unchecked)

    def _select_visible(self):
        f = self.ui.txtFilter.text().strip().lower()
        for i in range(self.ui.lstTrials.count()):
            it = self.ui.lstTrials.item(i)
            visible = (f in it.data(QtCore.Qt.UserRole)) if f else True
            if visible:
                it.setCheckState(QtCore.Qt.Checked)

    def _invert_selection(self):
        for i in range(self.ui.lstTrials.count()):
            it = self.ui.lstTrials.item(i)
            it.setCheckState(
                QtCore.Qt.Checked if it.checkState() == QtCore.Qt.Unchecked else QtCore.Qt.Unchecked
            )

    def _apply_filter(self, text: str):
        f = (text or "").lower().strip()
        for i in range(self.ui.lstTrials.count()):
            it = self.ui.lstTrials.item(i)
            match = (f in it.data(QtCore.Qt.UserRole)) if f else True
            self.ui.lstTrials.setRowHidden(i, not match)

    # ========= Acciones =========
    def _on_plot_clicked(self):
        if self.matrix is None or self.time is None:
            self._load_dataset_from_store()
            if self.matrix is None or self.time is None:
                self._notify("No hay 'trials_dataset' en DataStore.")
                return

        idx = self._collect_selected_indices()
        if not idx:
            self._notify("No hay trials seleccionados.")
            return

        # Slicing y render
        sel = self.matrix[np.array(idx) - 1, :]  # indices 1-based → 0-based
        self._render_butterfly(self.time, sel)
        self._render_heatmap(self.time, sel)
        self._notify(f"ERP: {len(idx)} trials graficados.")

    def _collect_selected_indices(self) -> list[int]:
        """Devuelve índices (1-based) según modo de selección."""
        if self.ui.chkSelectAll.isChecked():
            return list(range(1, self.N_trials + 1))
        if self.ui.chkSingleTrial.isChecked():
            return [self.ui.spnSingleTrial.value()]
        if self.ui.chkUseRange.isChecked():
            a, b = self.ui.spnFrom.value(), self.ui.spnTo.value()
            return list(range(a, b + 1))
        # manual vía lista
        out: list[int] = []
        for i in range(self.ui.lstTrials.count()):
            it = self.ui.lstTrials.item(i)
            if it.checkState() == QtCore.Qt.Checked:
                out.append(i + 1)
        return out

    def _notify(self, msg: str):
        try:
            if self.mainwin:
                self.mainwin.statusBar().showMessage(msg, 3000)
        except Exception:
            print(msg)

    # ========= Render VTK =========
    def _render_butterfly(self, t: np.ndarray, sel: np.ndarray):
        """
        Dibuja líneas (1 por trial) con vtkChartXY.
        t: (T,), sel: (K, T)
        """
        assert self.view_top is not None
        scene = self.view_top.GetScene()
        scene.ClearItems()

        table = vtk.vtkTable()
        # Columna X
        arrX = vtk.vtkFloatArray()
        arrX.SetName("time")
        arrX.SetNumberOfValues(t.size)
        for i, v in enumerate(t):
            arrX.SetValue(i, float(v))
        table.AddColumn(arrX)

        # Columnas Yk
        for k in range(sel.shape[0]):
            arrY = vtk.vtkFloatArray()
            arrY.SetName(f"trial_{k+1}")
            arrY.SetNumberOfValues(sel.shape[1])
            # cuidado: sel[k] es (T,)
            for i, v in enumerate(sel[k]):
                arrY.SetValue(i, float(v))
            table.AddColumn(arrY)

        chart = vtk.vtkChartXY()
        scene.AddItem(chart)

        # Un plot por columna Yk
        for k in range(sel.shape[0]):
            plot = chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, k + 1)  # 0 = X, (k+1) = Yk
            plot.SetWidth(0.5)

        chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle("Time (s)")
        chart.GetAxis(vtk.vtkAxis.LEFT).SetTitle("Amplitude")

        self.view_top.GetRenderWindow().Render()

    def _render_heatmap(self, t: np.ndarray, sel: np.ndarray):
        """
        Heatmap VTK (trials x tiempo).
        t: (T,), sel: (K, T) -> imagen width=T, height=K.
        - Mantiene float (NaN válidos).
        - NaN = transparente.
        """
        assert self.view_bot is not None
        ren = self.view_bot.GetRenderer()
        ren.RemoveAllViewProps()

        # --- datos ---
        X = np.asarray(sel, dtype=np.float32)  # (K, T)
        if X.ndim != 2:
            return
        K, Tn = X.shape

        # Opcional: trial 1 arriba (VTK usa origen abajo-izquierda)
        X = X[::-1, :]

        # Rango ignorando NaN
        vmin = float(np.nanmin(X)) if np.isfinite(X).any() else 0.0
        vmax = float(np.nanmax(X)) if np.isfinite(X).any() else 1.0
        if not np.isfinite(vmax - vmin) or vmax <= vmin:
            vmax = vmin + 1.0

        # --- vtkImageData en FLOAT (1 componente) ---
        img = vtk.vtkImageData()
        img.SetDimensions(Tn, K, 1)

        # espaciamiento y origen con el tiempo (para que sea proporcional)
        dt = float(np.mean(np.diff(t))) if t.size > 1 else 1.0
        t0 = float(t[0]) if t.size > 0 else 0.0
        img.SetSpacing(dt, 1.0, 1.0)
        img.SetOrigin(t0, 0.0, 0.0)

        img.AllocateScalars(vtk.VTK_FLOAT, 1)
        scal = vtk.vtkFloatArray.SafeDownCast(img.GetPointData().GetScalars())

        # copiar fila por fila (x-fastest). Fila 0 de X será y=0 (abajo).
        # Ya hicimos X[::-1,:], así que “trial 1” quedó arriba visualmente.
        for j in range(K):
            row = X[j]
            base = j * Tn
            # escribir con posibles NaN (VTK los respeta si mapeamos colores)
            for i in range(Tn):
                scal.SetTuple1(base + i, row[i])

        # --- normalización y LUT ---
        # mapea a RGBA respetando NaN
        lut = vtk.vtkLookupTable()
        lut.SetRange(vmin, vmax)
        lut.SetNumberOfTableValues(256)
        lut.Build()
        # color para NaN: transparente
        lut.SetNanColor(0.0, 0.0, 0.0, 0.0)
        # (opcional) colores fuera de rango:
        # lut.SetBelowRangeColor(0.0, 0.0, 0.0, 1.0); lut.UseBelowRangeColorOn()
        # lut.SetAboveRangeColor(1.0, 1.0, 1.0, 1.0); lut.UseAboveRangeColorOn()

        # shift/scale NO altera NaN
        mapper_shift = vtk.vtkImageShiftScale()
        mapper_shift.SetInputData(img)
        mapper_shift.SetOutputScalarTypeToFloat()
        mapper_shift.SetShift(0.0)  # dejamos el valor físico, la LUT tiene el rango

        map2colors = vtk.vtkImageMapToColors()
        map2colors.SetLookupTable(lut)
        map2colors.PassAlphaToOutputOn()   # respeta alpha de la LUT (NaN=0)
        map2colors.SetInputConnection(mapper_shift.GetOutputPort())
        map2colors.Update()

        actor = vtk.vtkImageActor()
        actor.GetMapper().SetInputConnection(map2colors.GetOutputPort())
        actor.GetProperty().SetInterpolationTypeToNearest()

        ren.AddActor(actor)
        ren.ResetCamera()
        self.view_bot.GetRenderWindow().Render()
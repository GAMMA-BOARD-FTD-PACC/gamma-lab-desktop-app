import os
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QListWidgetItem
import vtk
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import numpy as np
from vtkmodules.util import numpy_support
from typing import Tuple

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset
from plugins.analysis.time.erp.erp_plugin_ui import Ui_ErpPlot
from core.vtk_adapters.adapters import trials_matrix_to_vtk_table

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
        """Busca la señal activa y toma el último TrialDataset que tenga."""
        if not self.mainwin:
            return

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            return

        sig: SignalDataset | None = store.get_active_signal()
        print(f"[ERP] Señal activa: {sig}")
        if sig is None:
            print("No hay señal activa en DataStore (set_active_signal faltante).")
            return

        t, X, td = self._extract_trials_dataset(sig)
        if t is None or X is None:
            print("La señal activa no tiene TrialDatasets disponibles.")
            return

        # Guarda en el plugin
        self.td = td
        self.time = t.astype(float, copy=False)            # (Ns,)
        self.matrix = X.astype(float, copy=False)          # (N_trials, Ns)
        self.N_trials = int(self.matrix.shape[0])

        # Ajusta UI ligada a cantidad de trials y refresca lista
        self._populate_trials_list()
        print(f"ERP cargó TrialDataset: channel='{td.channel_name}', "
            f"T={self.N_trials} trials, Ns={self.matrix.shape[1]}")
        

    @staticmethod
    def _extract_trials_dataset(sig: "SignalDataset") -> Tuple[np.ndarray, np.ndarray, "TrialDataset | None"]:
        """
        Extrae (time_rel, trials) desde el último TrialDataset de la señal.
        Devuelve:
        t: (Ns,)
        X: (N_trials, Ns)  <-- transpuesto para el ERP
        td: TrialDataset   <-- referencia al TD usado
        """
        # Asegurarse que la señal tenga trials
        if sig is None or not hasattr(sig, "trials_dataset"):
            return None, None, None
        if not sig.trials_dataset:
            return None, None, None

        # Política simple: usar el ÚLTIMO trial creado
        td = sig.trials_dataset[-1]

        # Estructura esperada del TD
        if not hasattr(td, "time_rel") or not hasattr(td, "trials"):
            return None, None, None

        t = td.time_rel
        M = td.trials  # (Ns, T)

        # ERP espera (N_trials, Ns)
        if M.ndim != 2 or t.ndim != 1 or M.shape[0] != t.size:
            # Intento de corrección básica
            if M.T.shape[1] == t.size:
                M = M.T
                t = t
            else:
                print("Dimensiones incompatibles entre time_rel y trials.")
                return None, None, None
        else:
            M = M.T  # (T, Ns)

        return t, M, td

    
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
        # Asegurar dataset cargado
        if self.matrix is None or self.time is None:
            self._load_dataset_from_store()
            if self.matrix is None or self.time is None:
                self._notify("No hay 'trials_dataset' en la señal activa.")
                return

        # Por si cambió la cantidad de trials y la lista está desfasada
        if self.ui.lstTrials.count() != self.N_trials:
            self._populate_trials_list()

        idx = self._collect_selected_indices()
        if not idx:
            self._notify("No hay trials seleccionados.")
            return

        # indices 1-based → 0-based
        sel = self.matrix[np.array(idx) - 1, :]
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
    
    def cleanup_vtk(self):
        """Libera correctamente los recursos de VTK antes de destruir el widget."""
        try:
            if self.vtk_widget:
                print("[TrialsPlugin] Liberando recursos VTK...")
                rw = self.vtk_widget.GetRenderWindow()
                if rw:
                    iren = rw.GetInteractor()
                    if iren:
                        iren.TerminateApp()
                    rw.Finalize()
                self.vtk_widget.SetRenderWindow(None)
                self.vtk_widget = None
                self.renwin = None
        except Exception as e:
            print("[TrialsPlugin] cleanup_vtk() error:", e)
            
    def _render_butterfly(self, t: np.ndarray, sel: np.ndarray):
        """
        Dibuja líneas (1 por trial) con vtkChartXY.
        t: (T,), sel: (K, T)
        """
        assert self.view_top is not None
        scene = self.view_top.GetScene()
        scene.ClearItems()

        table = trials_matrix_to_vtk_table(t, sel.T)

        chart = vtk.vtkChartXY()
        scene.AddItem(chart)

        # Un plot por columna Yk
        num_cols = table.GetNumberOfColumns()
        for c in range(1, num_cols):
            plot = chart.AddPlot(vtk.vtkChart.LINE)
            plot.SetInputData(table, 0, c)
            plot.SetWidth(0.5)

        chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle("Time (s)")
        chart.GetAxis(vtk.vtkAxis.LEFT).SetTitle("Amplitude")

        self.view_top.GetRenderWindow().Render()

    def _render_heatmap(self, t: np.ndarray, sel: np.ndarray):
        """Heatmap 2D con ejes correctos en tiempo"""
        assert self.view_bot is not None
        scene = self.view_bot.GetScene()
        scene.ClearItems()

        # Datos
        X = np.asarray(sel, dtype=np.float32)[::-1, :]  # (K, T)
        K, Tn = X.shape
        print(f"\n=== DEBUG HEATMAP ===")
        print(f"Dimensiones originales: K={K} trials, Tn={Tn} samples")
        
        # CRÍTICO: Downsample si hay demasiadas muestras
        MAX_SAMPLES = 2000  # Límite razonable para visualización
        if Tn > MAX_SAMPLES:
            factor = int(np.ceil(Tn / MAX_SAMPLES))
            X = X[:, ::factor]
            t = t[::factor]
            Tn = X.shape[1]
            print(f"DOWNSAMPLED por factor {factor}: nueva dimensión Tn={Tn}")
        
        print(f"Datos: min={np.nanmin(X):.3f}, max={np.nanmax(X):.3f}, mean={np.nanmean(X):.3f}")
        
        # Calcular rango para LUT (sobre datos originales)
        finite = np.isfinite(X)
        vmin = float(X[finite].min()) if finite.any() else 0.0
        vmax = float(X[finite].max()) if finite.any() else 1.0
        if vmax <= vmin:
            vmax = vmin + 1.0
        
        # Parámetros de tiempo
        t0 = float(t[0]) if t.size > 0 else 0.0
        t_end = float(t[-1]) if t.size > 0 else 1.0
        dt = (t_end - t0) / Tn if Tn > 0 else 1.0
        
        print(f"Tiempo: t0={t0:.3f}s, t_end={t_end:.3f}s, dt={dt:.6f}s")
        
        # Crear imagen con SPACING y ORIGIN correctos
        img = vtk.vtkImageData()
        img.SetDimensions(Tn, K, 1)
        img.SetSpacing(dt, 1.0, 1.0)      # dt en X para mapear a tiempo
        img.SetOrigin(t0, 0.0, 0.0)       # Comienza en t0
        img.AllocateScalars(vtk.VTK_FLOAT, 1)
        
        # Escribir datos ORIGINALES (sin normalizar)
        for j in range(K):
            for i in range(Tn):
                img.SetScalarComponentFromFloat(i, j, 0, 0, X[j, i])
        
        img.Modified()
        
        # Verificar
        vtk_range = img.GetScalarRange()
        print(f"VTK ScalarRange: {vtk_range}")
        print(f"Image Spacing: {img.GetSpacing()}")
        print(f"Image Origin: {img.GetOrigin()}")
        
        # Usar tu función de LUT
        lut = self._build_lut("blue", vmin, vmax)  # Cambia a "viridis" si prefieres
        print(f"LUT Range: {lut.GetRange()}")
        
        # Chart
        chart = vtk.vtkChartHistogram2D()
        chart.SetInputData(img, 0)
        chart.SetTransferFunction(lut)
        
        # Configurar ejes - ahora deberían mostrar tiempo correctamente
        ax_bottom = chart.GetAxis(vtk.vtkAxis.BOTTOM)
        ax_left = chart.GetAxis(vtk.vtkAxis.LEFT)
        
        ax_bottom.SetTitle("Time (s)")
        ax_left.SetTitle("Trials")
        
        # El chart debería respetar spacing/origin automáticamente
        # pero lo forzamos por si acaso
        ax_bottom.SetRange(t0, t_end)
        ax_left.SetRange(0, K)
        
        # Añadir a escena
        scene.AddItem(chart)
        
        print("Chart añadido a escena")
        print("======================\n")
        
        # Render
        self.view_bot.GetRenderWindow().Render()



# Helper mini para el LUT (puedes dejar solo uno y olvidarte del resto)
    def _build_lut(self, mode: str, vmin: float, vmax: float) -> vtk.vtkScalarsToColors:
        mode = (mode or "blue").lower()
        N = 256
        bg = self.view_bot.GetRenderer().GetBackground()

        def finalize(lut: vtk.vtkLookupTable) -> vtk.vtkLookupTable:
            lut.SetRange(vmin, vmax)
            lut.SetNumberOfTableValues(N)
            lut.Build()
            lut.SetNanColor(*bg, 1.0)
            lut.SetUseBelowRangeColor(True); lut.SetBelowRangeColor(*bg, 1.0)
            lut.SetUseAboveRangeColor(True); lut.SetAboveRangeColor(*bg, 1.0)
            return lut

        # === NUEVO: escala azul ===
        if mode in ("blue", "blue_r"):
            # claro→oscuro (o invertido si "blue_r")
            # extremos (puedes ajustarlos a gusto):
            light = (0.93, 0.97, 1.00)   # azul muy claro
            dark  = (0.00, 0.10, 0.60)   # azul profundo
            lut = vtk.vtkLookupTable()
            lut = finalize(lut)
            for i in range(N):
                s = i / (N - 1)
                if mode == "blue_r":
                    s = 1.0 - s
                r = light[0] + s * (dark[0] - light[0])
                g = light[1] + s * (dark[1] - light[1])
                b = light[2] + s * (dark[2] - light[2])
                lut.SetTableValue(i, r, g, b, 1.0)
            return lut

        if mode == "jet":
            lut = vtk.vtkLookupTable()
            lut = finalize(lut)
            for i in range(N):
                val = i / (N - 1)
                if val < 0.25:
                    r, g, b = 0, 4*val, 1
                elif val < 0.5:
                    r, g, b = 0, 1, 1 - 4*(val - 0.25)
                elif val < 0.75:
                    r, g, b = 4*(val - 0.5), 1, 0
                else:
                    r, g, b = 1, 1 - 4*(val - 0.75), 0
                lut.SetTableValue(i, r, g, b, 1.0)
            return lut

        # viridis por defecto
        ctf = vtk.vtkColorTransferFunction()
        ctf.ClampingOn()
        ctf.SetRange(vmin, vmax)
        ctf.AddRGBPoint(vmin,                 0.267, 0.005, 0.329)
        ctf.AddRGBPoint((2*vmin+vmax)/3.0,    0.229, 0.322, 0.545)
        ctf.AddRGBPoint((vmin+2*vmax)/3.0,    0.127, 0.566, 0.550)
        ctf.AddRGBPoint(vmax,                 0.993, 0.906, 0.144)

        lut = vtk.vtkLookupTable()
        lut = finalize(lut)
        for i in range(N):
            s = i / (N - 1)
            x = vmin + s * (vmax - vmin)
            r, g, b = ctf.GetColor(x)
            lut.SetTableValue(i, r, g, b, 1.0)
        return lut
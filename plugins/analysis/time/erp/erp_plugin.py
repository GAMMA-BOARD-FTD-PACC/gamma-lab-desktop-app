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
from core.plugins.vtk_context_menu import VTKContextMenu
from core.services.signal_dataset import SignalDataset
from core.services.trial_dataset import TrialDataset
from plugins.analysis.time.erp.erp_plugin_ui import Ui_ErpPlot
from core.vtk_adapters.adapters import trials_matrix_to_vtk_table

class Erp_plugin(IPlugin):
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.vtk_widget = None
        self.renwin = None
        self.td = None
        self.ch_name = None
        
        # VTK widgets
        self.vtk_top: QVTKRenderWindowInteractor | None = None
        self.vtk_bot: QVTKRenderWindowInteractor | None = None
        self.view_top: vtk.vtkContextView | None = None
        self.view_bot: vtk.vtkContextView | None = None


    def process(self, data: any):
        print(f"ERP recibió datos: {data}")

        print("[TrialsPlugin] process")
        # habilita interacción (zoom, pan, etc)
        if self.vtk_top and self.vtk_top.GetRenderWindow().GetInteractor():
            self.vtk_top.GetRenderWindow().GetInteractor().Enable()

        if self.vtk_bot and self.vtk_bot.GetRenderWindow().GetInteractor():
                self.vtk_bot.GetRenderWindow().GetInteractor().Enable()

        # if self.mainwin:
        #     try:
        #         self.mainwin.statusBar().showMessage(f"ERP procesó: {data}", 3000)
        #     except Exception:
        #         pass

    def start(self, kernel):
        print("Iniciando ERP")
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            print("ERP tiene acceso a MainWindow")        

    def stop(self):
        print("[TrialsPlugin] stop")
        # deshabilita interacción (congela plugin)
        if self.vtk_top and self.vtk_top.GetRenderWindow().GetInteractor():
            self.vtk_top.GetRenderWindow().GetInteractor().Disable()

        if self.vtk_bot and self.vtk_bot.GetRenderWindow().GetInteractor():
            self.vtk_bot.GetRenderWindow().GetInteractor().Disable()


    def get_widget(self, parent=None):
        if self.widget is None:
            self.ui = Ui_ErpPlot(parent)
            self.widget = self.ui
            self.alerts.parent = self.widget
            self.ensure_vtk()
            self._wire_ui()
        else:
            self.widget.setParent(parent)
        return self.widget

    # ===== VTK =====
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

    # ========= Dataset =========
    def _load_trials_from_store(self):
        """
        Busca la señal activa en el DataStore y retorna el último TrialDataset:
        X:  np.ndarray (Ns, T)  matriz de trials (columnas = trials)
        """
        if not self.mainwin:
            return None, None, None

        if self.get_active_signal() is None:
            return None, None, None

        td = self.get_active_trials()
        if td is None:
            return None, None, None

        #td: TrialDataset = self.active_signal.trials_dataset[-1]  # último TD
        if not hasattr(td, "time_rel") or not hasattr(td, "trials"):
            self.alerts.warning("El TrialDataset no contiene 'time_rel' o 'trials'.", "Trials incompletos")
            return None, None, None

        t = np.asarray(td.time_rel, dtype=float)           # (Ns,)
        M = np.asarray(td.trials, dtype=float)             # (Ns, T)

        if M.ndim != 2 or t.ndim != 1:
            self.alerts.warning("El TrialDataset tiene dimensiones no válidas.", "Dimensiones inválidas")

            return None, None, None

        if M.shape[0] == t.size:
            M = M.T  # (T, Ns)
        elif M.shape[1] == t.size:
            pass     # ya está como (T, Ns)
        else:
            self.alerts.warning("time_rel no coincide con trials.", "Inconsistencia")

            return None, None, None

        return t, M, td
            
    # ========= Helpers UI =========
    def _collect_selected_indices(self, n_trials: int) -> list[int]:
        """Devuelve índices (1-based) según modo de selección."""
        if self.ui.chkSelectAll.isChecked():
            return list(range(1, n_trials + 1))
        if self.ui.chkSingleTrial.isChecked():
            return [min(max(1, self.ui.spnSingleTrial.value()), n_trials)]
        if self.ui.chkUseRange.isChecked():
            a = min(max(1, self.ui.spnFrom.value()), n_trials)
            b = min(max(1, self.ui.spnTo.value()), n_trials)
            if a > b:
                a, b = b, a
            return list(range(a, b + 1))
        # Manual (lista)
        out: list[int] = []
        for i in range(self.ui.lstTrials.count()):
            it = self.ui.lstTrials.item(i)
            if it.checkState() == QtCore.Qt.Checked:
                out.append(i + 1)
        return out
    
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
        t, M, td = self._load_trials_from_store()
        if t is None or M is None:
            return

        n_trials, n_samples = M.shape
        self._ensure_trials_list(n_trials)

        # 2) recolectar selección
        idx = self._collect_selected_indices(n_trials)
        if not idx:
            self._notify("No hay trials seleccionados.")
            return

        # indices 1-based → 0-based
        sel = M[np.array(idx) - 1, :]  # (K, Ns)

        # 3) render
        self._render_butterfly(t, sel)
        self._render_heatmap(t, sel)

        self.ch_name = getattr(td, "channel_name", "")
        self._notify(f"ERP: {len(idx)} trials graficados. Canal: {self.ch_name}")

    def _ensure_trials_list(self, n_trials: int):
        """Reconstruye la lista si está vacía o desfasada."""
        if self.ui.lstTrials.count() == n_trials and n_trials > 0:
            return
        self.ui.lstTrials.clear()
        self.ui.spnSingleTrial.setMaximum(max(1, n_trials))
        self.ui.spnFrom.setMaximum(max(1, n_trials))
        self.ui.spnTo.setMaximum(max(1, n_trials))
        if self.ui.spnTo.value() == 0:
            self.ui.spnTo.setValue(n_trials)

        for i in range(1, n_trials + 1):
            it = QListWidgetItem(f"Trial-{i}")
            it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.Checked)
            it.setData(QtCore.Qt.UserRole, f"trial-{i}".lower())
            self.ui.lstTrials.addItem(it)

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

        # chart.GetAxis(vtk.vtkAxis.BOTTOM).SetTitle("Time (s)")
        # chart.GetAxis(vtk.vtkAxis.LEFT).SetTitle("Amplitude")

        try:
            self.vtk_menu = VTKContextMenu(chart, self.vtk_top, self.active_signal.name,self.ch_name,self.meta.id, parent=self.widget)
        except Exception as e:
            self.alerts.info(f"Error creating contextual menu\n {str(e)}", "Contextual menu")


        self.view_top.GetRenderWindow().Render()

    def _render_heatmap(self, t: np.ndarray, sel: np.ndarray):
        """Heatmap 2D con ejes correctos en tiempo"""
        assert self.view_bot is not None
        scene = self.view_bot.GetScene()
        scene.ClearItems()

        # Datos
        X = np.asarray(sel, dtype=np.float32)
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
        if finite.any():
            p2, p98 = np.nanpercentile(X[finite], (2, 98))
            if p98 <= p2:
                vmin = float(X[finite].min())
                vmax = float(X[finite].max()) if float(X[finite].max()) > vmin else (vmin + 1.0)
            else:
                vmin, vmax = float(p2), float(p98)
        else:
            vmin, vmax = 0.0, 1.0
        
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
        
        try:
            self.vtk_menu_bot = VTKContextMenu(chart, self.vtk_top, self.active_signal.name,self.ch_name,self.meta.id, parent=self.widget)
            self.vtk_menu_bot.add_action("Cambiar LUT", self._on_change_lut)
        except Exception as e:
            self.alerts.info(f"Error creando el menú contextual.\n{e}", "Menú contextual (Bottom)")




        # Render
        self.view_bot.GetRenderWindow().Render()

# Funciones no implementadas de los menu contextuales

    def _on_change_lut(self):
        self.alerts.info("Cambiar mapa de colores (no implementado).", "Cambiar LUT")


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

        # === Divergente: azul -> blanco -> rojo, con gamma (más agresivo)
        if mode in ("blue_red", "br"):
            gamma = 0.6  # <1 = más contraste en zonas bajas
            lut = vtk.vtkLookupTable()
            lut = finalize(lut)
            for i in range(N):
                s = (i / (N - 1)) ** gamma  # curva no lineal
                if s < 0.5:
                    # azul (0,0.1,0.6) -> blanco (1,1,1)
                    k = s / 0.5
                    r = k*1.0 + (1-k)*0.00
                    g = k*1.0 + (1-k)*0.10
                    b = k*1.0 + (1-k)*0.60
                else:
                    # blanco (1,1,1) -> rojo (0.8,0.0,0.0)
                    k = (s - 0.5) / 0.5
                    r = k*0.80 + (1-k)*1.0
                    g = k*0.00 + (1-k)*1.0
                    b = k*0.00 + (1-k)*1.0
                lut.SetTableValue(i, r, g, b, 1.0)
            return lut

        # === Azul monocroma con gamma (más agresivo que antes)
        if mode in ("blue", "blue_r"):
            light = (0.93, 0.97, 1.00)
            dark  = (0.00, 0.10, 0.60)
            gamma = 0.6  # <1 = sube contraste
            lut = vtk.vtkLookupTable()
            lut = finalize(lut)
            for i in range(N):
                s = (i / (N - 1)) ** gamma
                if mode == "blue_r":
                    s = 1.0 - s
                r = light[0] + s * (dark[0] - light[0])
                g = light[1] + s * (dark[1] - light[1])
                b = light[2] + s * (dark[2] - light[2])
                lut.SetTableValue(i, r, g, b, 1.0)
            return lut

        if mode == "jet":
            # (tu jet actual) ...
            ...
            return lut

        # viridis por defecto (puedes también aplicar gamma aquí si quieres)
        ctf = vtk.vtkColorTransferFunction()
        ctf.ClampingOn()
        ctf.SetRange(vmin, vmax)
        ctf.AddRGBPoint(vmin,                 0.267, 0.005, 0.329)
        ctf.AddRGBPoint((2*vmin+vmax)/3.0,    0.229, 0.322, 0.545)
        ctf.AddRGBPoint((vmin+2*vmax)/3.0,    0.127, 0.566, 0.550)
        ctf.AddRGBPoint(vmax,                 0.993, 0.906, 0.144)

        lut = vtk.vtkLookupTable()
        lut = finalize(lut)
        gamma = 0.8  # un poco más agresivo
        for i in range(N):
            s = (i / (N - 1)) ** gamma
            x = vmin + s * (vmax - vmin)
            r, g, b = ctf.GetColor(x)
            lut.SetTableValue(i, r, g, b, 1.0)
        return lut
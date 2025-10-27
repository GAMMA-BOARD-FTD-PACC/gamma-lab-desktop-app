from datetime import datetime
from PyQt5.QtWidgets import QMessageBox
import vtk
import bisect

from core.filters.measurements import two_point_metrics


class MeasurementService:
    """
    Medición 2 puntos con persistencia por trial y overlays reconstruibles.
    - Persistimos p1/p2 en coords de datos + contexto (view_id, trial_id, channel_name).
    - Al navegar: set_context(...) + rebuild_overlays_for_current_context().
    - Overlays: línea punteada + puntos; mostrar/ocultar sin recrear cuando es posible.
    """

    def __init__(self, parent, vtk_widget, get_active_chart, datastore_get, datastore_set,
                 pick_radius_px=10, debug=True):
        self.parent = parent
        self.vtk_widget = vtk_widget
        self.get_active_chart = get_active_chart
        self.ds_get = datastore_get
        self.ds_set = datastore_set

        self._debug = False
        self._PICK_RADIUS_PX = pick_radius_px

        # ---- estado de interacción ----
        self._state = 'idle'
        self._current = None        # {'type','p1','p2'}
        self._down_pos = None

        # ---- ejes/rangos (congelados al elegir P1) ----
        self._ref_axes = None       # {'x': axis, 'y': axis}
        self._saved_ranges = None   # {'x': (min,max), 'y': (min,max)}
        self._invert_y = False

        # ---- datos para snap ----
        self._ref_data = None       # {'xs': [...], 'ys': [...]}

        # ---- acciones del botón izq (bloqueo temporal) ----
        self._saved_actions = {}

        # ---- overlays visibles actualmente ----
        self._overlay_enabled = True
        # cada item: {'id','chart','table','line_plot','points_plot'}
        self._overlays = []

        # ---- contexto actual (para filtrar/repintar) ----
        self._context = {"view_id": None, "trial_id": None, "channel_name": None}

        # paleta para líneas
        self._palette = [
            (30, 144, 255), (220, 20, 60), (50, 205, 50), (255, 140, 0),
            (148, 0, 211), (0, 191, 255), (255, 99, 71), (0, 128, 128),
        ]
        self._palette_i = 0

    # ====================== Contexto & navegación ======================

    def set_context(self, *, view_id=None, trial_id=None, channel_name=None):
        """
        Define el contexto actual (debe llamarse al cambiar de trial/canal/vista).
        Luego invoca rebuild_overlays_for_current_context() para repintar.
        """
        if view_id is not None:
            self._context["view_id"] = view_id
        if trial_id is not None:
            self._context["trial_id"] = trial_id
        if channel_name is not None:
            self._context["channel_name"] = channel_name

    def clear_visual_overlays(self):
        """
        Limpia SOLO lo visual (overlays), sin tocar el datastore.
        Útil antes de cambiar de trial.
        """
        while self._overlays:
            ov = self._overlays.pop()
            self._detach_overlay(ov)
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass

    def rebuild_overlays_for_current_context(self):
        """
        Reconstruye overlays de TODAS las mediciones cuyos metadatos ctx
        coincidan con el contexto actual.
        """
        # limpia lo visual actual
        self.clear_visual_overlays()

        ctx = self._context.copy()
        lst = self.ds_get("measurements", None) or []
        for m in lst:
            mctx = m.get("ctx") or {}
            if self._context_matches(ctx, mctx):
                try:
                    p1 = m.get("p1"); p2 = m.get("p2"); mid = m.get("id")
                    self._add_overlay_for_points(mid, p1, p2, axes_snapshot=None)
                except Exception:
                    pass

    def _context_matches(self, curr, other) -> bool:
        """
        Regla de matching de contexto:
        - Coinciden view_id y channel_name (si están definidos en ambos)
        - Coincide trial_id (exacto).
        """
        # si alguno está None lo ignoramos para evitar falsos negativos
        for key in ("view_id", "channel_name", "trial_id"):
            a = curr.get(key, None)
            b = other.get(key, None)
            if a is None or b is None:
                # si no tienes ese dato en algún lado, no lo usamos como filtro estricto
                continue
            if a != b:
                return False
        return True

    # ====================== API pública (medición) ======================

    def _dbg(self, *a):
        if self._debug:
            try:
                print("[MEAS]", *a)
            except Exception:
                pass
        
    @property
    def state(self):
        return self._state

    def start(self, measure_type: str):
        if self._state != 'idle':
            try:
                QMessageBox.information(self.parent, "Medición", "Ya hay una medición en curso. Completa o cancélala (Esc).")
            except Exception:
                pass
            return False
        
        self._state = 'waiting_p1'
        self._current = {'type': measure_type, 'p1': None, 'p2': None}
        QMessageBox.information(self.parent, "Medición","Selecciona el PRIMER punto con clic izquierdo.")

    def cancel(self):
        self._state = 'idle'
        self._current = None
        self._ref_axes = None
        self._saved_ranges = None
        self._ref_data = None
        self._down_pos = None
        self._suspend_left_actions(False)
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass

    def on_left_press(self, sx, sy):
        if self._state != 'idle':
            self._down_pos = (sx, sy)

    def on_left_release(self, sx, sy, click_eps=8):
        if self._state == 'idle':
            return

        # click vs drag
        if self._down_pos is not None:
            dx = abs(sx - self._down_pos[0]); dy = abs(sy - self._down_pos[1])
            self._down_pos = None
            if dx > click_eps or dy > click_eps:
                return

        ch = self.get_active_chart()
        if not ch:
            QMessageBox.warning(self.parent, "Medición", "No hay un gráfico activo.")
            self.cancel(); return

        if self._state == 'waiting_p1':
            
            self._ref_axes = {'x': ch.GetAxis(vtk.vtkAxis.BOTTOM),
                            'y': ch.GetAxis(vtk.vtkAxis.LEFT)}
            self._save_axes_ranges()
            self._load_reference_data_for_pick(ch)

            # --- DEBUG ---
            rect = self._plot_rect_pixels()
            self._dbg("waiting_p1:",
                    "rect=", rect,
                    "ranges=", self._saved_ranges,
                    "xs_len=", (len(self._ref_data['xs']) if self._ref_data else 0))

            if not self._ref_data or not self._ref_data.get('xs'):
                QMessageBox.warning(self.parent, "Medición", "No hay datos de serie para seleccionar puntos.")
                self.cancel(); return

        picked = self._pick_nearest_data_point(sx, sy)
        if picked is None:
            QMessageBox.warning(self.parent, "Medición",
                                f"No hay punto cercano (≤ {self._PICK_RADIUS_PX}px). Intenta de nuevo.")
            return

        if self._state == 'waiting_p1':
            self._current['p1'] = picked
            self._state = 'waiting_p2'
            self._suspend_left_actions(True)
            QMessageBox.information(self.parent, "Medición",
                                    "Ahora selecciona el SEGUNDO punto con clic izquierdo.")
            return

        if self._state == 'waiting_p2':
            curr = self._get_current_ranges()
            if curr is not None:
                self._saved_ranges = curr
                self._dbg("waiting_p2: ranges REFRESHED ->", self._saved_ranges)

            self._current['p2'] = picked
            self._suspend_left_actions(False)
            self._finalize()
            return

    # ====================== ejes/rangos & transformaciones ======================

    def _get_current_ranges(self):
        """Lee SIEMPRE los rangos actuales del chart (tras zoom/pan)."""
        ch = self.get_active_chart()
        if not ch:
            return None
        try:
            ax_x = ch.GetAxis(vtk.vtkAxis.BOTTOM)
            ax_y = ch.GetAxis(vtk.vtkAxis.LEFT)
            return {
                'x': (ax_x.GetMinimum(), ax_x.GetMaximum()),
                'y': (ax_y.GetMinimum(), ax_y.GetMaximum()),
            }
        except Exception:
            return None


    def _vec2_to_xy(self, v):
        if isinstance(v, (tuple, list)) and len(v) == 2:
            return float(v[0]), float(v[1])
        if hasattr(v, "GetX") and hasattr(v, "GetY"):
            return float(v.GetX()), float(v.GetY())
        if hasattr(v, "x") and hasattr(v, "y"):
            return float(v.x), float(v.y)
        return None, None

    def _save_axes_ranges(self):
        ch = self.get_active_chart()
        if not ch: return
        ax_x = self._ref_axes['x'] if self._ref_axes else ch.GetAxis(0)
        ax_y = self._ref_axes['y'] if self._ref_axes else ch.GetAxis(1)
        self._saved_ranges = {
            'x': (ax_x.GetMinimum(), ax_x.GetMaximum()),
            'y': (ax_y.GetMinimum(), ax_y.GetMaximum())
        }

    def _plot_rect_pixels(self):
        ch = self.get_active_chart()
        if not ch: return None
        try:
            p1 = ch.GetPoint1(); p2 = ch.GetPoint2()
        except Exception:
            return None
        x1, y1 = self._vec2_to_xy(p1)
        x2, y2 = self._vec2_to_xy(p2)
        if x1 is None or x2 is None or y1 is None or y2 is None:
            return None
        return x1, x2, y1, y2

    def _plot_to_screen(self, x_val, y_val):
        rect = self._plot_rect_pixels()
        if rect is None:
            return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect

        # Preferimos rangos del chart en vivo; usamos saved como fallback
        rng = self._get_current_ranges() or self._saved_ranges
        if rng is None:
            return None

        x_min, x_max = rng['x']
        y_min, y_max = rng['y']

        dxp = (x_max_px - x_min_px)
        dyp = (y_max_px - y_min_px)
        if dxp <= 0 or dyp <= 0 or (x_max - x_min) == 0 or (y_max - y_min) == 0:
            return None

        sx = x_min_px + (x_val - x_min) * dxp / (x_max - x_min)
        if not self._invert_y:
            sy = y_min_px + (y_val - y_min) * dyp / (y_max - y_min)
        else:
            sy = y_min_px + (y_max - y_val) * dyp / (y_max - y_min)
        return float(sx), float(sy)


    def _screen_to_plot(self, sx, sy):
        ch = self.get_active_chart()
        if not ch:
            return None

        rect = self._plot_rect_pixels()
        if rect is None:
            return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect

        if sx < x_min_px or sx > x_max_px or sy < y_min_px or sy > y_max_px:
            return None

        # Preferimos rangos del chart en vivo; usamos saved como fallback
        rng = self._get_current_ranges() or self._saved_ranges
        if rng is None:
            return None

        x_min, x_max = rng['x']
        y_min, y_max = rng['y']

        dxp = (x_max_px - x_min_px)
        dyp = (y_max_px - y_min_px)
        if dxp <= 0 or dyp <= 0 or (x_max - x_min) == 0 or (y_max - y_min) == 0:
            return None

        x_val = x_min + (sx - x_min_px) * (x_max - x_min) / dxp
        if not self._invert_y:
            y_val = y_min + (sy - y_min_px) * (y_max - y_min) / dyp
        else:
            y_val = y_min + (y_max - sy) * (y_max - y_min) / dyp
        return float(x_val), float(y_val)

    # ====================== datos para snap ======================

    def _load_reference_data_for_pick(self, chart):
        ref_plot = None
        try:
            n = chart.GetNumberOfPlots()
        except Exception:
            self._ref_data = None; return
        for i in range(n):
            pl = chart.GetPlot(i)
            if pl is not None:
                ref_plot = pl; break
        if ref_plot is None:
            self._ref_data = None; return
        try:
            table = ref_plot.GetInput()
        except Exception:
            table = None
        if table is None:
            self._ref_data = None; return

        def _col_by_name(tbl, names):
            for nm in names:
                try:
                    arr = tbl.GetColumnByName(nm)
                    if arr is not None:
                        return arr
                except Exception:
                    pass
            return None

        x_arr = _col_by_name(table, ("Time","time","X","x"))
        y_arr = _col_by_name(table, ("Value","value","Y","y"))
        if x_arr is None or y_arr is None:
            try:
                x_arr = table.GetColumn(0); y_arr = table.GetColumn(1)
            except Exception:
                self._ref_data = None; return

        nrows = min(x_arr.GetNumberOfTuples(), y_arr.GetNumberOfTuples())
        xs, ys = [], []
        for i in range(nrows):
            xs.append(float(x_arr.GetValue(i)))
            ys.append(float(y_arr.GetValue(i)))
        pairs = sorted(zip(xs, ys), key=lambda t: t[0])
        xs2, ys2, last = [], [], None
        for x, y in pairs:
            if last is not None and x <= last:
                x = last + 1e-12
            xs2.append(x); ys2.append(y); last = x
        self._ref_data = {'xs': xs2, 'ys': ys2}

    def _pick_nearest_data_point(self, sx_click, sy_click):
        if not self._ref_data or not self._ref_data.get('xs'):
            self._dbg("pick: sin ref_data")  # DEBUG
            return None

        rect = self._plot_rect_pixels()
        if rect is None:
            self._dbg("pick: rect=None")  # DEBUG
            return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect
        if not (x_min_px <= sx_click <= x_max_px and y_min_px <= sy_click <= y_max_px):
            self._dbg(f"pick: click fuera del rect {sx_click,sy_click} vs {rect}")  # DEBUG
            return None

        guess = self._screen_to_plot(sx_click, sy_click)
        if guess is None:
            self._dbg("pick: screen_to_plot=None")  # DEBUG
            return None
        xg, yg = guess
        self._dbg(f"pick: guess plot=({xg:.6f},{yg:.6f})")  # DEBUG

        xs = self._ref_data['xs']; ys = self._ref_data['ys']
        import bisect
        i = bisect.bisect_left(xs, xg)
        cand_idx = [max(0, i-2), max(0, i-1), min(len(xs)-1, i), min(len(xs)-1, i+1)]
        seen=set(); cand_idx=[c for c in cand_idx if not (c in seen or seen.add(c))]
        self._dbg("pick: cand_idx=", cand_idx)  # DEBUG

        best = None; best_d2 = None
        for idx in cand_idx:
            sp = self._plot_to_screen(xs[idx], ys[idx])
            if sp is None:
                self._dbg(f"pick: idx={idx} sp=None")  # DEBUG
                continue
            sx, sy = sp
            d2 = (sx - sx_click)**2 + (sy - sy_click)**2
            self._dbg(f"pick: idx={idx} data=({xs[idx]:.6f},{ys[idx]:.6f}) -> screen=({sx:.1f},{sy:.1f}) d2={d2:.1f}")  # DEBUG
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2; best = (xs[idx], ys[idx])

        thr = self._PICK_RADIUS_PX * self._PICK_RADIUS_PX
        self._dbg(f"pick: best_d2={best_d2} thr={thr}")  # DEBUG
        if best is not None and best_d2 <= thr:
            return best
        return None


    # ====================== persistencia ======================

    def _save_measurement(self, result, p1, p2):
        t = result.get("type", "measure")
        lst = self.ds_get("measurements", None)
        if not isinstance(lst, list):
            lst = []

        # secuencia por tipo
        prefix, seq = f"{t}-", 0
        for it in lst:
            if isinstance(it, dict) and it.get("type") == t:
                mid = str(it.get("id", ""))
                if mid.startswith(prefix):
                    try:
                        n = int(mid[len(prefix):]); seq = max(seq, n)
                    except Exception:
                        pass
        seq += 1
        meas_id = f"{t}-{seq:03d}"

        # contexto actual
        ctx = {
            "view_id": self._context.get("view_id"),
            "trial_id": self._context.get("trial_id"),
            "channel_name": self._context.get("channel_name"),
        }

        rec = {
            "id": meas_id,
            "type": t,
            "p1": (float(p1[0]), float(p1[1])),
            "p2": (float(p2[0]), float(p2[1])),
            "dx": float(result.get("dx", float(p2[0]) - float(p1[0]))),
            "dy": float(result.get("dy", float(p2[1]) - float(p1[1]))),
            "slope": float(result.get("slope", 0.0)),
            "dist": float(result.get("dist", 0.0)),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ctx": ctx,  # <-- guardamos contexto para reconstruir luego
        }
        lst.append(rec)
        self.ds_set("measurements", lst)
        return meas_id

    # ====================== cierre de medición ======================

    def _finalize(self):
        cur = self._current or {}
        if not (cur.get('p1') and cur.get('p2')):
            self.cancel(); return

        x1, y1 = cur['p1']; x2, y2 = cur['p2']
        result = two_point_metrics((x1, y1), (x2, y2), kind=cur.get('type', 'slope'))
        meas_id = self._save_measurement(result, (x1, y1), (x2, y2))

        # overlay sólo si coincide con el contexto actual (lo normal)
        try:
            self._add_overlay_for_points(meas_id, (x1, y1), (x2, y2), axes_snapshot=None)
        except Exception:
            pass

        try:
            QMessageBox.information(
                self.parent, "Slope saved",
                f"Result '{result['type']}' saved (ID: {meas_id}).\n"
                f"Slope = {result['slope']:.6f}\n\n"
                f"For more information go to 'Measure / Slope'."
            )
        except Exception:
            pass

        self._state = 'idle'
        self._current = None
        self._ref_axes = None
        self._saved_ranges = None
        self._ref_data = None

        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass

    # ====================== bloqueo botón izquierdo ======================

    def _suspend_left_actions(self, suspend: bool):
        ch = self.get_active_chart()
        if not ch: return
        maybe = []
        for name in ("PAN", "ZOOM", "SELECT", "ZOOM_RECT", "ZOOM_BOX"):
            if hasattr(vtk.vtkChart, name):
                maybe.append(getattr(vtk.vtkChart, name))
        if suspend:
            self._saved_actions = {}
            for act in maybe:
                try:
                    btn = ch.GetActionToButton(act)
                    self._saved_actions[act] = btn
                    if btn == 1:
                        ch.SetActionToButton(act, -1)
                except Exception:
                    pass
        else:
            for act, btn in self._saved_actions.items():
                try:
                    ch.SetActionToButton(act, btn)
                except Exception:
                    pass
            self._saved_actions = {}

    # ====================== OVERLAYS ======================

    def _vtk_has_set_visible(self, plot) -> bool:
        return hasattr(plot, "SetVisible")

    def _set_plot_visible(self, chart, plot, visible: bool):
        if plot is None:
            return
        if self._vtk_has_set_visible(plot):
            try:
                plot.SetVisible(bool(visible)); return
            except Exception:
                pass
        # fallback
        if visible:
            try: chart.AddPlotInstance(plot)
            except Exception: pass
        else:
            try: chart.RemovePlotInstance(plot)
            except Exception: pass

    def set_overlay_visible(self, visible: bool):
        self._overlay_enabled = bool(visible)
        for ov in self._overlays:
            ch = ov.get("chart")
            if not ch: continue
            self._set_plot_visible(ch, ov.get("line_plot"), visible)
            self._set_plot_visible(ch, ov.get("points_plot"), visible)
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass

    def toggle_overlay(self):
        self.set_overlay_visible(not self._overlay_enabled)

    def _next_color(self):
        c = self._palette[self._palette_i % len(self._palette)]
        self._palette_i += 1
        return c

    def _make_table_2pts(self, p1, p2):
        tbl = vtk.vtkTable()
        ax = vtk.vtkFloatArray(); ax.SetName("X")
        ay = vtk.vtkFloatArray(); ay.SetName("Y")
        tbl.AddColumn(ax); tbl.AddColumn(ay)
        tbl.InsertNextBlankRow(); tbl.SetValue(0, 0, float(p1[0])); tbl.SetValue(0, 1, float(p1[1]))
        tbl.InsertNextBlankRow(); tbl.SetValue(1, 0, float(p2[0])); tbl.SetValue(1, 1, float(p2[1]))
        return tbl

    def _add_overlay_for_points(self, meas_id: str, p1, p2, axes_snapshot=None):
        ch = self.get_active_chart()
        if not ch: return
        tbl = self._make_table_2pts(p1, p2)

        # línea punteada
        line_plot = ch.AddPlot(vtk.vtkChart.LINE)
        try:
            pen = line_plot.GetPen()
            pen.SetWidth(2)
            pen.SetLineType(vtk.vtkPen.DASH_LINE)
            r, g, b = self._next_color(); pen.SetColor(r, g, b)
        except Exception:
            pass
        line_plot.SetInputData(tbl, 0, 1)
        line_plot.SetUseIndexForXSeries(False)

        # puntos
        points_plot = ch.AddPlot(vtk.vtkChart.POINTS)
        try:
            if hasattr(points_plot, "SetMarkerStyle"): points_plot.SetMarkerStyle(2)
            if hasattr(points_plot, "SetMarkerSize"): points_plot.SetMarkerSize(7.0)
            penp = points_plot.GetPen(); penp.SetWidth(2); penp.SetColor(0, 0, 0)
        except Exception:
            pass
        points_plot.SetInputData(tbl, 0, 1)
        points_plot.SetUseIndexForXSeries(False)

        self._overlays.append({
            "id": meas_id,
            "chart": ch,
            "table": tbl,
            "line_plot": line_plot,
            "points_plot": points_plot,
        })

        if not self._overlay_enabled:
            self._set_plot_visible(ch, line_plot, False)
            self._set_plot_visible(ch, points_plot, False)

        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass

    def _detach_overlay(self, ov):
        ch = ov.get("chart")
        if not ch: return
        for key in ("line_plot", "points_plot"):
            self._set_plot_visible(ch, ov.get(key), False)

    def _remove_overlay_by_id(self, meas_id: str):
        idx = next((i for i, o in enumerate(self._overlays) if o.get("id") == meas_id), None)
        if idx is None: return False
        ov = self._overlays.pop(idx)
        self._detach_overlay(ov)
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass
        return True

    # ====================== Borrados públicos ======================

    def remove_last_measurement(self):
        if not self._overlays:
            return False
        last = self._overlays[-1]
        meas_id = last.get("id")
        ok = self._remove_overlay_by_id(meas_id)
        lst = self.ds_get("measurements", None) or []
        lst = [m for m in lst if str(m.get("id")) != str(meas_id)]
        self.ds_set("measurements", lst)
        return ok

    def remove_measurement_by_id(self, meas_id: str):
        ok = self._remove_overlay_by_id(meas_id)
        lst = self.ds_get("measurements", None) or []
        lst = [m for m in lst if str(m.get("id")) != str(meas_id)]
        self.ds_set("measurements", lst)
        return ok

    def clear_all_measurements(self):
        # limpia visual
        self.clear_visual_overlays()
        # limpia datastore
        self.ds_set("measurements", [])
        return True

    def on_chart_changed(self):
        """Invocado por el menú cuando se reemplaza el chart (nuevo trial/vista)."""
        self._ref_axes = None
        self._saved_ranges = None
        self._ref_data = None
        self._down_pos = None
        
        self._dump_chart_state("on_chart_changed(before render)")
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass
        self._dump_chart_state("on_chart_changed(after render)")
        
        if self._state != 'idle':
            self.cancel() 
            
    def _dump_chart_state(self, tag=""): ## BORRAR CUANDO SE DEJN DE HACER LOGS
        ch = self.get_active_chart()
        if not ch:
            print(f"[MEAS] {tag} chart=None"); return
        try:
            nplots = ch.GetNumberOfPlots()
        except Exception:
            nplots = -1
        # ejes
        try:
            ax_x = ch.GetAxis(vtk.vtkAxis.BOTTOM)
            ax_y = ch.GetAxis(vtk.vtkAxis.LEFT)
            xr = (ax_x.GetMinimum(), ax_x.GetMaximum())
            yr = (ax_y.GetMinimum(), ax_y.GetMaximum())
        except Exception:
            xr = yr = None
        # rect en pixels del chart
        try:
            p1 = ch.GetPoint1(); p2 = ch.GetPoint2()
            rect = (p1.GetX(), p2.GetX(), p1.GetY(), p2.GetY())
        except Exception:
            rect = None

        print(f"[MEAS] {tag} plots={nplots} xr={xr} yr={yr} rect={rect}")

        # Lista rápida de labels/filas para ver qué plots hay
        try:
            for i in range(nplots):
                pl = ch.GetPlot(i)
                if pl is None: 
                    print(f"   [plot {i}] None")
                    continue
                try:
                    lbl = pl.GetLabel()
                except Exception:
                    lbl = None
                rows = None
                try:
                    tbl = pl.GetInput()
                    rows = tbl.GetNumberOfRows() if tbl else None
                except Exception:
                    pass
                # tipo (LINE/POINTS) si está disponible
                ptype = None
                try:
                    ptype = pl.GetPlotType()
                except Exception:
                    pass
                print(f"   [plot {i}] label={lbl!r} rows={rows} type={ptype}")
        except Exception:
            pass

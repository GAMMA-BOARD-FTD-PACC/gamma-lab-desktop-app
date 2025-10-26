from datetime import datetime
from PyQt5.QtWidgets import QMessageBox, QToolTip
from PyQt5.QtGui import QCursor
import vtk
import bisect
import math

from core.filters.measurements import two_point_metrics

class MeasurementService:
    """
    Servicio de medición 2 puntos (pendiente, distancia, etc.).
    - Usa SIEMPRE el chart activo (get_active_chart).
    - Mantiene persitencia vía datastore (misma estructura que usas).
    - Se integra con handlers de mouse externos: on_left_press/on_left_release.
    """
    def __init__(self, parent, vtk_widget, get_active_chart, datastore_get, datastore_set, pick_radius_px=10, debug=True):
        self.parent = parent
        self.vtk_widget = vtk_widget
        self.get_active_chart = get_active_chart
        self.ds_get = datastore_get
        self.ds_set = datastore_set

        self._debug = debug
        self._PICK_RADIUS_PX = pick_radius_px

        # estado
        self._state = 'idle'
        self._current = None         # {'type', 'p1', 'p2'}
        self._down_pos = None

        # ejes/rangos
        self._ref_axes = None        # {'x': axis, 'y': axis}
        self._saved_ranges = None    # {'x': (min,max), 'y':(min,max)}
        self._invert_y = False

        # datos de referencia para snap
        self._ref_data = None        # {'xs': [...], 'ys': [...]}

        # acciones del botón izq
        self._saved_actions = {}

    # ---------- API pública ----------
    @property
    def state(self):
        return self._state

    def start(self, measure_type: str):
        if self._state != 'idle':
            self.cancel()
        self._state = 'waiting_p1'
        self._current = {'type': measure_type, 'p1': None, 'p2': None}
        QMessageBox.information(self.parent, "Medición", "Selecciona el PRIMER punto con clic izquierdo.")

    def cancel(self):
        self._state = 'idle'
        self._current = None
        self._ref_axes = None
        self._saved_ranges = None
        self._ref_data = None
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
            self.cancel()
            return

        # En P1: fijar ejes/rangos y cargar datos para snap
        if self._state == 'waiting_p1':
            self._ref_axes = {'x': ch.GetAxis(vtk.vtkAxis.BOTTOM),
                              'y': ch.GetAxis(vtk.vtkAxis.LEFT)}
            self._save_axes_ranges()
            self._load_reference_data_for_pick(ch)
            if not self._ref_data or not self._ref_data.get('xs'):
                QMessageBox.warning(self.parent, "Medición", "No hay datos de serie para seleccionar puntos.")
                self.cancel()
                return

        picked = self._pick_nearest_data_point(sx, sy)
        if picked is None:
            QMessageBox.warning(self.parent, "Medición",
                                f"No hay punto cercano (≤ {self._PICK_RADIUS_PX}px). Intenta de nuevo.")
            return

        if self._state == 'waiting_p1':
            self._current['p1'] = picked
            self._state = 'waiting_p2'
            self._suspend_left_actions(True)
            QMessageBox.information(self.parent, "Medición", "Ahora selecciona el SEGUNDO punto con clic izquierdo.")
            return

        if self._state == 'waiting_p2':
            self._current['p2'] = picked
            self._suspend_left_actions(False)
            self._finalize()
            return

    # ---------- helpers de ejes/rangos ----------
    
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
        self._saved_ranges = {'x': (ax_x.GetMinimum(), ax_x.GetMaximum()),
                              'y': (ax_y.GetMinimum(), ax_y.GetMaximum())}

    def _plot_rect_pixels(self):
        ch = self._get_active_chart() if hasattr(self, "_get_active_chart") else self.get_active_chart()
        if not ch:
            return None
        try:
            p1 = ch.GetPoint1()
            p2 = ch.GetPoint2()
        except Exception:
            return None

        x1, y1 = self._vec2_to_xy(p1)
        x2, y2 = self._vec2_to_xy(p2)
        if x1 is None or x2 is None or y1 is None or y2 is None:
            return None

        # OJO: VTK usa origen abajo-izquierda; devolvemos rect en px como (x_min, x_max, y_min, y_max)
        return x1, x2, y1, y2

    def _plot_to_screen(self, x_val, y_val):
        rect = self._plot_rect_pixels()
        if rect is None or self._saved_ranges is None:
            return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect
        x_min, x_max = self._saved_ranges['x']
        y_min, y_max = self._saved_ranges['y']
        dxp = (x_max_px - x_min_px); dyp = (y_max_px - y_min_px)
        if dxp <= 0 or dyp <= 0: return None
        sx = x_min_px + (x_val - x_min) * dxp / (x_max - x_min)
        if not self._invert_y:
            sy = y_min_px + (y_val - y_min) * dyp / (y_max - y_min)
        else:
            sy = y_min_px + (y_max - y_val) * dyp / (y_max - y_min)
        return float(sx), float(sy)

    def _screen_to_plot(self, sx, sy):
        ch = self.get_active_chart()
        if not ch: return None
        rect = self._plot_rect_pixels()
        if rect is None: return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect
        if sx < x_min_px or sx > x_max_px or sy < y_min_px or sy > y_max_px:
            return None

        if self._saved_ranges:
            x_min, x_max = self._saved_ranges['x']
            y_min, y_max = self._saved_ranges['y']
        else:
            ax_x = ch.GetAxis(0); ax_y = ch.GetAxis(1)
            x_min, x_max = ax_x.GetMinimum(), ax_x.GetMaximum()
            y_min, y_max = ax_y.GetMinimum(), ax_y.GetMaximum()

        dxp = (x_max_px - x_min_px); dyp = (y_max_px - y_min_px)
        if dxp <= 0 or dyp <= 0:
            return None

        x_val = x_min + (sx - x_min_px) * (x_max - x_min) / dxp
        if not self._invert_y:
            y_val = y_min + (sy - y_min_px) * (y_max - y_min) / dyp
        else:
            y_val = y_min + (y_max - sy) * (y_max - y_min) / dyp
        return float(x_val), float(y_val)

    # ---------- datos para snap ----------
    def _load_reference_data_for_pick(self, chart):
        ref_plot = None
        try:
            n = chart.GetNumberOfPlots()
        except Exception:
            self._ref_data = None; return
        for i in range(n):
            pl = chart.GetPlot(i)
            if pl is not None:
                ref_plot = pl
                break
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
            return None

        rect = self._plot_rect_pixels()
        if rect is None:
            return None
        x_min_px, x_max_px, y_min_px, y_max_px = rect
        if not (x_min_px <= sx_click <= x_max_px and y_min_px <= sy_click <= y_max_px):
            return None

        guess = self._screen_to_plot(sx_click, sy_click)
        if guess is None:
            return None
        xg, yg = guess

        xs = self._ref_data['xs']; ys = self._ref_data['ys']
        i = bisect.bisect_left(xs, xg)
        cand_idx = [max(0, i-2), max(0, i-1), min(len(xs)-1, i), min(len(xs)-1, i+1)]
        seen = set(); cand_idx = [c for c in cand_idx if not (c in seen or seen.add(c))]

        best = None; best_d2 = None
        for idx in cand_idx:
            sp = self._plot_to_screen(xs[idx], ys[idx])
            if sp is None:
                continue
            sx, sy = sp
            d2 = (sx - sx_click)**2 + (sy - sy_click)**2
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best = (xs[idx], ys[idx])

        if best is not None and best_d2 <= (self._PICK_RADIUS_PX * self._PICK_RADIUS_PX):
            return best
        return None

    # ---------- persistencia ----------
    def _save_measurement(self, result, p1, p2):
        t = result.get("type", "measure")
        lst = self.ds_get("measurements", None)
        if not isinstance(lst, list):
            lst = []
        prefix, seq = f"{t}-", 0
        for it in lst:
            if isinstance(it, dict) and it.get("type") == t:
                mid = str(it.get("id", ""))
                if mid.startswith(prefix):
                    try:
                        n = int(mid[len(prefix):])
                        seq = max(seq, n)
                    except Exception:
                        pass
        seq += 1
        meas_id = f"{t}-{seq:03d}"

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
        }
        lst.append(rec)
        self.ds_set("measurements", lst)
        return meas_id

    def _finalize(self):
        cur = self._current or {}
        if not (cur.get('p1') and cur.get('p2')):
            self.cancel()
            return
        x1, y1 = cur['p1']; x2, y2 = cur['p2']
        result = two_point_metrics((x1, y1), (x2, y2), kind=cur.get('type', 'slope'))
        meas_id = self._save_measurement(result, (x1, y1), (x2, y2))

        try:
            QMessageBox.information(
                self.parent, "Slope saved",
                f"Result '{result['type']}' saved (ID: {meas_id}).\n"
                f"Slope = {result['slope']:.6f}\n\n"
                f"For more information go to 'Measure / Slope'."
            )
        except Exception:
            pass

        # limpiar estado
        self._state = 'idle'
        self._current = None
        self._ref_axes = None
        self._saved_ranges = None
        self._ref_data = None
        try:
            self.vtk_widget.GetRenderWindow().Render()
        except Exception:
            pass

    # ---------- bloqueo/restore de acciones del botón izquierdo ----------
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
                    if btn == 1:  # LEFT
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

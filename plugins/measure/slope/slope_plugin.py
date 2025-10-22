import sys
import csv
from datetime import datetime
from typing import Any, Dict, List

from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QHeaderView

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from plugins.measure.slope.slope_plugin_ui import Ui_Slope


# ----------------------------
# Modelo de tabla (solo lectura)
# ----------------------------
class SlopeTableModel(QtCore.QAbstractTableModel):
    HEADERS = [
        "ID", "Type",
        "P1.x", "P1.y", "P2.x", "P2.y",
        "dx", "dy", "slope", "dist",
        "Timestamp"
    ]

    def __init__(self, rows: List[Dict[str, Any]] | None = None, parent=None):
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = rows or []

    # --- obligatorios ---
    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        else:
            return str(section + 1)
        return None

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if not index.isValid() or role not in (QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole):
            return None

        row = self._rows[index.row()]
        col = index.column()

        def _fmt(v):
            if isinstance(v, float):
                return f"{v:.6g}"
            return "" if v is None else str(v)

        mapping = {
            0: row.get("id"),
            1: row.get("type"),
            2: row.get("p1x"),
            3: row.get("p1y"),
            4: row.get("p2x"),
            5: row.get("p2y"),
            6: row.get("dx"),
            7: row.get("dy"),
            8: row.get("slope"),
            9: row.get("dist"),
            10: row.get("timestamp"),
        }
        return _fmt(mapping.get(col))

    # --- helpers ---
    def set_rows(self, rows: List[Dict[str, Any]]):
        self.beginResetModel()
        self._rows = rows or []
        self.endResetModel()

    def get_all_rows(self) -> List[Dict[str, Any]]:
        return list(self._rows)


# ----------------------------
# Plugin
# ----------------------------
class SlopePlugin(IPlugin):

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None

        # UI
        self.widget: QtWidgets.QWidget | None = None
        self.ui: Ui_Slope | None = None

        # Modelo
        self.model: SlopeTableModel | None = None

    # ---------- util de logs ----------
    def _log(self, *args):
        print("[SLOPE]", *args)
        sys.stdout.flush()

    def _notify(self, msg: str):
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(msg, 2500)
                return
            except Exception:
                pass
        self._log(msg)

    def _warn(self, msg: str):
        try:
            QMessageBox.warning(self.widget, "Slope", msg)
        except Exception:
            self._log("WARN:", msg)

    # ---------- ciclo de vida ----------
    def initialize(self, kernel):
        self.kernel = kernel
        self._log("initialize()")

    def start(self, kernel):
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        self._log("start()")

    def stop(self):
        self._log("stop()")

    def process(self, data: Any):
        # Cuando el host "procesa" algo, refrescamos la tabla (opcional).
        self._log("process(): refresh table")
        self._reload_from_store()

    # ---------- UI ----------
    def get_widget(self, parent=None):
        if self.widget is None:
            self._log("get_widget(): creando UI")
            self.ui = Ui_Slope()
            self.widget = QtWidgets.QWidget(parent)
            self.ui.setupUi(self.widget)

            # Modelo + tabla
            self.model = SlopeTableModel([])
            tv = self.ui.tableView
            tv.setModel(self.model)
            tv.setSortingEnabled(True)
            tv.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            tv.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
            tv.setAlternatingRowColors(True)
            tv.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tv.verticalHeader().setVisible(False)

            # Botón derecha -> export CSV
            self.ui.pushButton.setText("Export CSV")
            self.ui.pushButton.clicked.connect(self._on_export_csv)

            # Primer load
            self._reload_from_store()
        else:
            self.widget.setParent(parent)
        return self.widget

    # ---------- DataStore ----------
    def _reload_from_store(self):
        rows = self._load_slope_rows_from_store()
        if self.model:
            self.model.set_rows(rows)
        self._notify(f"Slope: {len(rows)} mediciones")

    def _load_slope_rows_from_store(self) -> List[Dict[str, Any]]:
        """
        Lee DataStore['measurements'] (también tolera 'meassurements'),
        filtra tipo 'slope' y normaliza a filas con:
          id, type, p1x, p1y, p2x, p2y, dx, dy, slope, dist, timestamp
        Si faltan métricas, las calcula.
        """
        # Obtener servicio DataStore
        store = None
        try:
            if self.mainwin:
                store = self.mainwin.kernel.get_service("DataStore")
            if store is None and self.kernel:
                store = self.kernel.get_service("DataStore")
        except Exception:
            store = None

        if store is None:
            self._warn("No se encontró DataStore.")
            return []

        # Leer lista cruda
        raw = None
        for key in ("measurements", "meassurements"):  # tolera typo
            try:
                if hasattr(store, "get"):
                    raw = store.get(key)
                elif hasattr(store, "get_data"):
                    raw = store.get_data(key)
                elif hasattr(store, "get_value"):
                    raw = store.get_value(key)
                else:
                    raw = None
            except Exception:
                raw = None
            if raw:
                break

        if not raw or not isinstance(raw, (list, tuple)):
            self._log("DataStore['measurements'] vacío o inválido.")
            return []

        rows: List[Dict[str, Any]] = []
        seq = 0
        for item in raw:
            try:
                if not isinstance(item, dict) or item.get("type") != "slope":
                    continue

                p1 = item.get("p1"); p2 = item.get("p2")
                if not (isinstance(p1, (list, tuple)) and isinstance(p2, (list, tuple)) and len(p1) == 2 and len(p2) == 2):
                    continue

                p1x, p1y = float(p1[0]), float(p1[1])
                p2x, p2y = float(p2[0]), float(p2[1])

                dx    = item.get("dx");    dx    = float(dx) if dx is not None else (p2x - p1x)
                dy    = item.get("dy");    dy    = float(dy) if dy is not None else (p2y - p1y)
                slope = item.get("slope"); slope = float(slope) if slope is not None else (dy / dx if dx != 0 else float("inf"))
                dist  = item.get("dist");  dist  = float(dist) if dist is not None else ((dx**2 + dy**2) ** 0.5)

                mid = item.get("id")
                if not mid:
                    seq += 1
                    mid = f"slope-{seq:03d}"

                ts = item.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                rows.append({
                    "id": mid, "type": "slope",
                    "p1x": p1x, "p1y": p1y, "p2x": p2x, "p2y": p2y,
                    "dx": dx, "dy": dy, "slope": slope, "dist": dist,
                    "timestamp": ts
                })
            except Exception as e:
                self._log("Fila inválida en measurements:", e)

        return rows

    # ---------- Export ----------
    def _on_export_csv(self):
        if not self.model:
            return
        rows = self.model.get_all_rows()
        if not rows:
            self._warn("No hay mediciones para exportar.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self.widget,
            "Exportar mediciones (slope) a CSV",
            "slope_measurements.csv",
            "CSV (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(SlopeTableModel.HEADERS)
                for r in rows:
                    w.writerow([
                        r.get("id", ""),
                        r.get("type", ""),
                        r.get("p1x", ""),
                        r.get("p1y", ""),
                        r.get("p2x", ""),
                        r.get("p2y", ""),
                        r.get("dx", ""),
                        r.get("dy", ""),
                        r.get("slope", ""),
                        r.get("dist", ""),
                        r.get("timestamp", ""),
                    ])
            self._notify(f"Exportado CSV: {path}")
        except Exception as e:
            self._warn(f"No se pudo exportar CSV:\n{e}")

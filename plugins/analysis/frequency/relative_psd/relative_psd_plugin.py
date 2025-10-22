# Ubicación: plugins/analysis/frequency/relative_psd/relative_psd_plugin.py

import sys
import numpy as np
import vtk
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtWidgets import QMessageBox
from scipy.signal import welch

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.services.signal_dataset import SignalDataset
# Importar nuestra UI específica
from plugins.analysis.frequency.relative_psd.relative_psd_plugin_ui import Ui_Relative_psd
# (No necesitamos VTK ni adaptadores de plot)

class Relative_psd_plugin(IPlugin):
    """
    Plugin para calcular la Potencia Relativa (y Absoluta) de una banda
    de frecuencia, basado en el promedio de PSD de todos los trials.
    
    Implementa la lógica de f_PSD_Relative (la parte de 'pow' y 'powr').
    """
    
    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.kernel = None
        self.mainwin = None

        # UI
        self.widget: QtWidgets.QWidget | None = None
        self.ui: Ui_Relative_psd | None = None # Usamos la UI de Relative_psd

        self.active_signal: SignalDataset | None = None

    # ---------- util de logs ----------
    def _log(self, *args):
        print("[Relative PSD]", *args)
        sys.stdout.flush()

    def initialize(self, kernel):
        self.kernel = kernel
        self._log("initialize()")

    def start(self, kernel):
        self._log("start() - obteniendo MainWindow")
        self.mainwin = kernel.get_service("MainWindow")

    def stop(self):
        self._log("stop()")
        
    def process(self, data):
        self._log(f"[Relative PSD] Process: {data}")

    def get_widget(self, parent=None):
        if self.widget is None:
            self._log("get_widget(): creando UI")
            self.ui = Ui_Relative_psd() # Usamos la UI de Relative_psd
            self.widget = QtWidgets.QWidget(parent)
            self.ui.setupUi(self.widget)

            self._log("UI creada.")
            self._wire_ui()
        else:
            self.widget.setParent(parent)
        return self.widget

    def _wire_ui(self):
        self._log("wire ui")
        self.ui.pushButton.clicked.connect(self._on_calculate_clicked)
        
        # Sincronizar noverlap con nperseg
        self.ui.npersegSpinBox.valueChanged.connect(self._sync_noverlap)

    def _sync_noverlap(self):
        """Ajusta noverlap a la mitad de nperseg por defecto."""
        nperseg = self.ui.npersegSpinBox.value()
        self.ui.noverlapSpinBox.setValue(nperseg // 2)
        # Asegurar que nfft también siga a nperseg (comportamiento común)
        self.ui.nfftSpinBox.setValue(nperseg)

    # ------- acciones -------
    def _on_calculate_clicked(self):
        self._log("_on_calculate_clicked()")

        # 1) Cargar trials de la señal activa
        fs, X, ch_name = self._load_trials_from_store()
        if X is None or fs is None:
            self._notify("Relative PSD: No hay trials en la señal activa.")
            return

        # 2) Parámetros UI
        try:
            target_fs = float(self.ui.sampleDensityDoubleSpinBox.value())
            
            # Parámetros de Welch
            window = self.ui.windowComboBox.currentText()
            nperseg = self.ui.npersegSpinBox.value()
            noverlap = self.ui.noverlapSpinBox.value()
            nfft = self.ui.nfftSpinBox.value()
            
            # Parámetros de Banda (Fq1, Fq2)
            f1 = self.ui.f1DoubleSpinBox.value()
            f2 = self.ui.f2DoubleSpinBox.value()

            if f1 >= f2:
                 raise ValueError("Fq1 (Low) debe ser menor que Fq2 (High).")
            if noverlap >= nperseg:
                 raise ValueError("N-overlap debe ser menor que N-per-seg.")
        
        except Exception as e:
            QMessageBox.warning(self.widget, "Error de Parámetros", str(e))
            return

        # 3) PSD (Cálculo base)
        try:
            freq, power_all_trials, fs_eff = self._compute_psd(X, fs, target_fs,
                                                    window, nperseg, noverlap, nfft)
            # power_all_trials tiene forma (Nf, T) -> Equivale a 'pxx'
            
        except Exception as e:
            self._log(f"Error en _compute_psd: {e}")
            QMessageBox.critical(self.widget, "Error de Cálculo", 
                                 f"No se pudo calcular la PSD: {e}")
            return
            
        # --- LÓGICA DE RELATIVE PSD ---
        
        # 4. Calcular el promedio (pxx_av = mean(pxx'))
        #    USAMOS nanmean para ignorar trials con NaN
        power_avg = np.nanmean(power_all_trials, axis=1) # (Nf,)

        # 5. Calcular potencias
        try:
            abs_power, rel_power = self._calculate_relative_power(freq, power_avg, f1, f2)
        except Exception as e:
            self._notify(f"Error calculando potencia: {e}")
            # Resetear UI en caso de error
            self.ui.absPowerValue.setText("Error")
            self.ui.relPowerValue.setText("Error")
            return

        # 6. Actualizar UI con resultados
        self.ui.absPowerValue.setText(f"{abs_power: .4e}") # Formato científico
        self.ui.relPowerValue.setText(f"{rel_power: .2f} %") # Porcentaje
        
        self._notify(f"PSD Relativa [Band {f1}-{f2} Hz] calculada.")



    def _calculate_relative_power(self, freq: np.ndarray, power_avg: np.ndarray, 
                                  f1: float, f2: float):
        """
        Calcula la potencia absoluta y relativa para una banda.
        Usa nansum para ignorar valores NaN.
        """
        
        # 1. Potencia Total (Ptot)
        # --- ARREGLO: Replicar el rango [0.5, 490] Hz de MATLAB ---
        total_power_indices = np.where((freq >= 0.5) & (freq <= 490))[0]
        if total_power_indices.size == 0:
            self._log("Error: No se encontraron bins entre 0.5 y 490 Hz para Ptot.")
            return 0.0, 0.0
            
        total_power = np.nansum(power_avg[total_power_indices])
        # --- FIN DEL ARREGLO ---
        
        if total_power == 0 or np.isnan(total_power):
            self._log("Error: Potencia total (0.5-490Hz) es cero o NaN.")
            return 0.0, 0.0

        # 2. Encontrar índices de la banda (id1, id2)
        band_indices = np.where((freq >= f1) & (freq <= f2))[0]
        
        if band_indices.size == 0:
            self._log(f"Advertencia: No se encontraron bins de frecuencia en el rango {f1}-{f2} Hz.")
            return 0.0, 0.0
            
        # 3. Potencia Absoluta en la banda (pow)
        # Usamos nansum para ignorar NaN
        abs_power_in_band = np.nansum(power_avg[band_indices])
        
        # 4. Potencia Relativa en la banda (powr)
        # (pow / Ptot) * 100
        rel_power_percent = (abs_power_in_band / total_power) * 100.0
        
        self._log(f"Banda {f1}-{f2} Hz: Abs={abs_power_in_band:.4e}, Rel={rel_power_percent:.2f}%")
        
        # Devolver 0 si el resultado sigue siendo nan (por si acaso)
        if np.isnan(rel_power_percent):
             self._log("Resultado fue NaN, devolviendo 0.")
             return abs_power_in_band, 0.0
             
        return abs_power_in_band, rel_power_percent


    def _notify(self, msg: str):
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(msg, 3000)
                return
            except Exception:
                pass
        self._log(msg)

    # ====== DATA ======
    def _load_trials_from_store(self):
        # (Función idéntica a la de Psd_average_plugin)
        if not self.mainwin:
            return None, None, None

        store = self.mainwin.kernel.get_service("DataStore")
        if store is None:
            QMessageBox.warning(self.widget, "Error", "No se encontró el DataStore.")
            return None, None, None

        self.active_signal = store.get_active_signal()
        if not self.active_signal or not getattr(self.active_signal, "trials_dataset", None):
            self.active_signal = store.get_active_signal()
            if not self.active_signal or not getattr(self.active_signal, "trials_dataset", None):
                QMessageBox.warning(self.widget, "Error", "No hay señal activa o no tiene TrialDataset.")
                return None, None, None

        td = self.active_signal.trials_dataset[-1]  # último TD creado
        fs = float(getattr(td, "sampling_rate", 0.0))
        X  = np.asarray(getattr(td, "trials", None), dtype=np.float64)  # (Ns, T)
        ch = getattr(td, "channel_name", "")
        if X is None or X.ndim != 2 or fs <= 0:
            self._log("TrialDataset inválido (fs<=0 o trials no 2D).")
            return None, None, None

        self._log(f"Trials: Ns={X.shape[0]}, T={X.shape[1]}, fs={fs}")
        return fs, X, ch

    # ====== PSD Logic (CON ARREGLO PARA NAN) ======
    def _compute_psd(self, X: np.ndarray, fs: float, target_fs: float,
                        window: str, nperseg: int, noverlap: int, nfft: int):
            
            Ns, T = X.shape
            if target_fs and target_fs > 0:
                srt = max(1, int(round(fs / float(target_fs))))
            else:
                srt = 1

            fs_eff = fs / srt
            Xds = X[::srt, :] if srt > 1 else X
            Ns_eff = Xds.shape[0]
            
            # --- NUEVO ARREGLO v3: Reemplazar NaNs con Cero ---
            # 1. Encontrar NaNs
            nan_mask = np.isnan(Xds)
            num_nans = np.sum(nan_mask)
            if num_nans > 0:
                self._log(f"Advertencia: Se encontraron {num_nans} puntos NaN. Serán reemplazados por 0.")
                # 2. Reemplazar NaNs con 0
                # copy=False modifica Xds en el lugar
                np.nan_to_num(Xds, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
            
            # 3. Usar todos los trials (ahora X_clean = Xds)
            X_clean = Xds
            # --- FIN DEL ARREGLO ---
            
            if nperseg > Ns_eff:
                self._log(f"Advertencia: nperseg ({nperseg}) > Ns_eff ({Ns_eff}). "
                        f"Ajustando nperseg a {Ns_eff}.")
                nperseg = Ns_eff
            if noverlap >= nperseg:
                self._log(f"Advertencia: noverlap >= nperseg. Ajustando noverlap.")
                noverlap = nperseg // 2

            self._log(f"Welch params: fs_eff={fs_eff}, window={window}, nperseg={nperseg}, "
                    f"noverlap={noverlap}, nfft={nfft}, axis=0")

            # 4. Correr Welch en los datos (ahora X_clean = Xds con ceros)
            freq, power = welch(
                X_clean, # <-- Usar X_clean
                fs=fs_eff,
                window=window,
                nperseg=nperseg,
                noverlap=noverlap,
                nfft=nfft,
                scaling='density', # V^2/Hz
                axis=0
            )
            
            power = power.astype(np.float64) # (Nf, T)
            freq = freq.astype(np.float64)   # (Nf,)

            self._log(f"PSD: srt={srt}, fs_eff={fs_eff:.3f} Hz, Nf={freq.size}, T_calc={power.shape[1]}")
            return freq, power, fs_eff
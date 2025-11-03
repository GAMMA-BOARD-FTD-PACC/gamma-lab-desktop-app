from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk
import numpy as np
import pywt
from scipy.interpolate import interp1d

from core.plugins.interfaces import IPlugin
from core.plugins.meta import PluginMeta
from core.plugins.vtk_context_menu import VTKContextMenu
from core.services.signal_dataset import SignalDataset
from core.services.data_store import DataStore
from plugins.analysis.time_frequency.wavelet_average.wavelet_average_plugin_ui import Ui_Wavelet_Average


class Wavelet_average_plugin(IPlugin):
    """Time-Frequency Analysis Plugin (Wavelet CWT average across trials + VTK Visualization)."""

    def __init__(self, meta: PluginMeta):
        super().__init__(meta)
        self.mainwin = None
        self.widget = None
        self.vtk_widget = None
        self.renwin = None
        self.started = False
        self.kernel = None
        self.ui = None
        self.vtk_menu = None
        self._context_view = None
        self._vtk_renderer = None
    # end def

    # =====================================================
    # === Lifecycle
    # =====================================================

    def process(self, data: any):
        """Optional hook; show status message if available."""
        if self.mainwin:
            try:
                self.mainwin.statusBar().showMessage(f"Wavelet Average processed: {data}", 3000)
            except Exception as e:
                self._log("process: failed to show status message:", e)
    # end def

    def start(self, kernel):
        """Start plugin and obtain main window reference."""
        self.kernel = kernel
        self.mainwin = kernel.get_service("MainWindow")
        if self.mainwin:
            self.started = True
            self._log("Plugin started.")
    # end def

    def stop(self):
        """Stop plugin and disable VTK interactor if present."""
        if self.vtk_widget and self.vtk_widget.GetRenderWindow():
            interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
            if interactor:
                interactor.Disable()
                self._log("VTK interactor disabled.")
    # end def


    # =====================================================
    # === UI + VTK creation
    # =====================================================
    def get_widget(self, parent=None):
        """Create or reuse the widget and wire UI events."""
        if self.widget is not None:
            self.widget.setParent(parent)
            return self.widget

        self.widget = QWidget(parent)
        self.ui = Ui_Wavelet_Average()
        self.ui.setupUi(self.widget)

        # initialize controls and VTK container
        self._init_controls()
        self._create_vtk_container()

        self.ui.createWaveletButton.clicked.connect(self.on_create_wavelet)
        return self.widget
    # end def

    def _init_controls(self):
        """Initialize UI control ranges and connections."""

        self.ui.splitter.setStretchFactor(0, 0)
        self.ui.splitter.setStretchFactor(1, 1)
        self.ui.splitter.widget(1).setMaximumWidth(300)

        self.ui.sampleDensitySpinBox.setRange(1, 10000)
        self.ui.sampleDensitySpinBox.setValue(1000)
        self.ui.highFrequencySpinBox.setRange(0, 10000)
        self.ui.highFrequencySpinBox.setValue(500)
        self.ui.lowFrequencySpinBox.setRange(0, 10000)
        self.ui.lowFrequencySpinBox.setValue(1)
        self.ui.cyclesSpinBox.setRange(1, 20)
        self.ui.cyclesSpinBox.setValue(2)

        self.ui.normalizeComboBox.setEnabled(False)
        self.ui.normalizeComboBox.addItems(["Z-Score", "Percent change", "Relative power", "Min-Max"])
        self.ui.normalizeCheckBox.stateChanged.connect(
            lambda state: self.ui.normalizeComboBox.setEnabled(state == Qt.Checked)
        )

        self.ui.scaleComboBox.setEnabled(False)
        self.ui.scaleComboBox.addItems(["Log"])
        self.ui.scaleCheckBox.stateChanged.connect(
            lambda state: self.ui.scaleComboBox.setEnabled(state == Qt.Checked)
        )
    # end def

    def _create_vtk_container(self):
        """Create VTK widget and context view container in the UI frame."""
        try:
            vtk_layout = QVBoxLayout(self.ui.frame)
            vtk_layout.setContentsMargins(0, 0, 0, 0)
            self.vtk_widget = QVTKRenderWindowInteractor(self.ui.frame)
            vtk_layout.addWidget(self.vtk_widget)

            self.renwin = self.vtk_widget.GetRenderWindow()
            self._context_view = vtk.vtkContextView()
            self._context_view.SetRenderWindow(self.renwin)
            renderer = self._context_view.GetRenderer()
            renderer.SetBackground(0.98, 0.98, 0.98)
            self._vtk_renderer = renderer

            interactor = self.vtk_widget.GetRenderWindow().GetInteractor()
            if interactor and not interactor.GetInitialized():
                interactor.Initialize()

            self._log("VTK container initialized.")
        except Exception as e:
            self._log("Error creating VTK container:", e)
    # end def

    def ensure_vtk(self):
        """Ensure VTK context view exists and is configured."""
        try:
            if not self.vtk_widget or not self.renwin:
                self._log("ensure_vtk: no vtk widget or render window available.")
                return
            if not self._context_view:
                self._context_view = vtk.vtkContextView()
                self._context_view.SetRenderWindow(self.renwin)
            renderer = self._context_view.GetRenderer()
            renderer.SetBackground(0.98, 0.98, 0.98)
            self._vtk_renderer = renderer
        except Exception as e:
            self._log("ensure_vtk error:", e)
    # end def

    # =====================================================
    # === Data access
    # =====================================================
    def _get_active_signal(self) -> SignalDataset | None:
        """Return the currently active SignalDataset from the DataStore."""
        try:
            store: DataStore | None = self.mainwin.kernel.get_service("DataStore")
            if store is None:
                QMessageBox.warning(self.widget, "Error", "DataStore not found.")
                self._log("_get_active_signal: DataStore service missing.")
                return None
            ds = store.get_active_signal() if store else None
            if not ds:
                self._log("_get_active_signal: no active signal in DataStore.")
                return None
            self._log("_get_active_signal: active signal obtained.")
            return ds
        except Exception as e:
            self._log("_get_active_signal error:", e)
            return None
    # end def

    # =====================================================
    # === Main logic: compute average CWT and render
    # =====================================================
    def on_create_wavelet(self):
        """Compute average CWT across all active trials and render the average scalogram."""
        active_signal = self._get_active_signal()
        if active_signal is None:
            QMessageBox.warning(self.widget, "Error", "No active signal found.")
            return

        channel_name = active_signal.channel_names[0]
        trials = active_signal.get_active_trials(active_signal.name, channel_name)

        t = trials.time_rel
        if t is None or len(t) < 2:
            QMessageBox.warning(self.widget, "Error", "Insufficient time information.")
            return

        try:
            data = np.array(trials.trials)  # shape: (n_samples, n_trials) or (n_trials, n_samples)
            # Ensure shape is (n_samples, n_trials)
            if data.ndim == 1:
                data = data[:, np.newaxis]
            if data.shape[0] < data.shape[1]:
                data = data.T
        except Exception as e:
            QMessageBox.warning(self.widget, "Error", f"Unable to obtain trials matrix: {e}")
            self._log("on_create_wavelet: failed to convert trials to array:", e)
            return

        fs_calculado = round(1.0 / (t[1] - t[0]), 3)

        # UI parameters
        fs = self.ui.sampleDensitySpinBox.value()
        fmin = self.ui.lowFrequencySpinBox.value()
        fmax = self.ui.highFrequencySpinBox.value()
        cycles = float(self.ui.cyclesSpinBox.value())
        normalize = self.ui.normalizeCheckBox.isChecked()
        scaled = self.ui.scaleCheckBox.isChecked()
        norm_method = self.ui.normalizeComboBox.currentText().lower()

        # compute scalogram per trial
        scalograms = []
        n_trials = data.shape[1]
        if n_trials == 0:
            QMessageBox.warning(self.widget, "Error", "No trials available.")
            self._log("on_create_wavelet: no trials found.")
            return

        self._log(f"Computing wavelet for {n_trials} trials...")

        for trial_idx in range(n_trials):
            try:
                sig = np.nan_to_num(data[:, trial_idx], nan=0.0, posinf=0.0, neginf=0.0)
                scalogram, times, freqs = self.compute_wavelet(sig, fs_calculado, fs, fmin, fmax, cycles)
                if scalogram is None or scalogram.size == 0:
                    self._log(f"  Trial {trial_idx+1}/{n_trials}: empty scalogram, skipping.")
                    continue
                scalograms.append(scalogram)
                self._log(f"  Trial {trial_idx+1}/{n_trials}: min={np.min(scalogram):.4f}, max={np.max(scalogram):.4f}")
            except Exception as e:
                self._log(f"  Trial {trial_idx+1}/{n_trials} failed:", e)

        if len(scalograms) == 0:
            QMessageBox.warning(self.widget, "Error", "No valid scalograms computed.")
            self._log("on_create_wavelet: no valid scalograms after processing trials.")
            return

        # stack and compute average
        try:
            stacked = np.stack(scalograms, axis=0)  # shape: (n_valid_trials, n_freqs, n_times)
            avg_scalogram = np.mean(stacked, axis=0)  # shape: (n_freqs, n_times)
            self._log(f"Average scalogram computed: min={np.min(avg_scalogram):.4f}, max={np.max(avg_scalogram):.4f}")
        except Exception as e:
            self._log("Error while stacking/averaging scalograms:", e)
            QMessageBox.warning(self.widget, "Error", f"Failed to compute average scalogram: {e}")
            return

        # optional normalization
        if normalize:
            try:
                avg_scalogram = self.normalize_tf(avg_scalogram, norm_method)
                self._log(f"Normalization applied: method={norm_method}")
            except Exception as e:
                self._log("Normalization failed:", e)

        # optional log scaling (resample rows logarithmically)
        if scaled:
            try:
                avg_scalogram, freqs = self._scale_log(avg_scalogram, freqs)
                self._log("Log scaling applied.")
            except Exception as e:
                self._log("Log scaling failed:", e)

        # ensure VTK and render
        self.ensure_vtk()
        try:
            self.render_scalogram(times, freqs, avg_scalogram, "Wavelet Average (Morlet)", scaled)
            self._log("Rendering complete.")
        except Exception as e:
            self._log("Render failed:", e)
            QMessageBox.warning(self.widget, "Error", f"Rendering failed: {e}")
    # end def

    # =====================================================
    # === Wavelet computation (single trial)
    # =====================================================
    def compute_wavelet(self, sig, fs_calculado, fs, fmin, fmax, num_cycles):
        """Compute Continuous Wavelet Transform (Morlet) for a single signal vector."""
        try:
            freq_seg = 2 * int(max(1, fmax - fmin))
            factor = int(round(fs_calculado / fs)) if fs > 0 else 1
            factor = max(1, factor)
            sig = sig[::factor]

            if len(sig) < 4:
                # return empty but shaped scalogram to indicate no meaningful output
                return np.zeros((1, 1)), np.array([0.0]), np.array([0.0])
        except Exception as e:
            self._log("compute_wavelet: parameter processing failed:", e)
            return np.zeros((1, 1)), np.array([0.0]), np.array([0.0])

        try:
            freq_axis = np.linspace(fmin, fmax, freq_seg)[::-1]
            wavelet = f"cmor{num_cycles}-1.0"
            central_freq = pywt.central_frequency(wavelet)
            # protect against division by zero in freq_axis
            freq_axis_safe = np.copy(freq_axis)
            freq_axis_safe[freq_axis_safe == 0] = 1e-6
            scales = central_freq * fs / freq_axis_safe

            coef, _ = pywt.cwt(sig, scales, wavelet, sampling_period=1/fs if fs > 0 else 1.0)
            scalogram = np.abs(coef)
            time_axis = np.arange(len(sig)) / (fs if fs > 0 else 1.0)

            return scalogram, time_axis, freq_axis
        except Exception as e:
            self._log("compute_wavelet error:", e)
            return np.zeros((1, 1)), np.array([0.0]), np.array([0.0])
    # end def

    # =====================================================
    # === Normalization and scaling helpers
    # =====================================================
    def normalize_tf(self, tf, method="z-score"):
        """Normalize time-frequency map. Method names: 'z-score', 'percent change', 'relative power', 'min-max'."""
        try:
            base_mean = np.mean(tf, axis=1, keepdims=True)
            base_std = np.std(tf, axis=1, ddof=0, keepdims=True)
            base_min = np.min(tf)
            base_max = np.max(tf)

            if method == "z-score":
                return (tf - base_mean) / (base_std + 1e-12)

            elif method == "percent change":
                return ((tf - base_mean) / (base_mean + 1e-12)) * 100

            elif method == "relative power":
                return tf / (base_mean + 1e-12)

            elif method == "min-max":
                denom = (base_max - base_min) if (base_max - base_min) != 0 else 1.0
                return (tf - base_min) / denom

            else:
                raise ValueError("Unrecognized normalization method.")
        except Exception as e:
            self._log("normalize_tf error:", e)
            raise
    # end def

    def _scale_log(self, scalogram, freqs):
        """Resample scalogram rows so rows are spaced logarithmically in frequency."""
        freqs_numeric = np.asarray(freqs, dtype=np.float64)
        # filter positive freqs
        positive_mask = freqs_numeric > 0
        if not np.any(positive_mask):
            raise ValueError("scale_log: no positive frequencies available.")

        fmin = np.min(freqs_numeric[positive_mask])
        fmax = np.max(freqs_numeric)

        n_freqs_new = scalogram.shape[0]

        log_fmin = np.log10(fmin)
        log_fmax = np.log10(fmax)

        log_freqs_new = np.linspace(log_fmin, log_fmax, n_freqs_new)
        freqs_new = 10**log_freqs_new

        scalogram_new = np.zeros_like(scalogram)

        freqs_orig_sorted = np.sort(freqs_numeric)

        for i in range(scalogram.shape[1]):
            # flip so that lowest freq corresponds to first element when interpolating
            data_col = np.flipud(scalogram[:, i])
            try:
                interp_func = interp1d(freqs_orig_sorted, data_col, kind='linear', fill_value='extrapolate')
                scalogram_new[:, i] = interp_func(freqs_new)
            except Exception as e:
                self._log(f"_scale_log: interpolation failed at time index {i}:", e)
                # fallback: fill with zeros for this column
                scalogram_new[:, i] = 0.0

        return scalogram_new, freqs_new
    # end def

    def _get_log_ticks_coords(self, f_min_log, f_max_log):
        """Return tick coordinates and labels for log10 axis (inputs are log10 values)."""
        start = np.floor(f_min_log)
        end = np.ceil(f_max_log)

        tick_coords = np.arange(start, end + 0.5, 0.5)
        tick_coords = tick_coords[(tick_coords >= f_min_log) & (tick_coords <= f_max_log)]

        labels = []
        for t_coord in tick_coords:
            label_val = 10**t_coord
            labels.append(f"{label_val:.1f}")

        return tick_coords, labels
    # end def

    # =====================================================
    # === Rendering (VTK) - adapted from Wavelet plugin
    # =====================================================
    def render_scalogram(self, t, freqs, scalogram, title="Scalogram", log_scale=False):
        """Render a 2D scalogram using VTK chart (histogram2D)."""
        if not self.vtk_widget or not self._context_view:
            self._log("render_scalogram: VTK not initialized.")
            return

        context_view = self._context_view
        scene = context_view.GetScene()
        scene.ClearItems()

        # Preprocess scalogram array and compute geometry
        n_freqs, n_times = scalogram.shape
        if n_times <= 0 or n_freqs <= 0:
            self._log("render_scalogram: invalid scalogram shape:", scalogram.shape)
            return

        t0, t_end = float(t[0]), float(t[-1]) if len(t) > 1 else (0.0, float(t[0]) if len(t) > 0 else 1.0)[1]
        dt = (t_end - t0) / n_times if n_times > 1 else 1.0

        if log_scale:
            Z = np.nan_to_num(scalogram.astype(np.float32))
            ax_title = "Frequency (Hz) - Log"

            f0_orig = float(freqs[0]) if freqs[0] > 0 else 1e-6
            f_end_orig = float(freqs[-1])

            f0_coord = np.log10(f0_orig)
            f_end_coord = np.log10(f_end_orig)
            df_coord = (f_end_coord - f0_coord) / n_freqs if n_freqs > 1 else 1.0

            f0_range, f_end_range = f0_coord, f_end_coord
            df_spacing = df_coord
        else:
            Z = np.flipud(np.nan_to_num(scalogram.astype(np.float32)))
            ax_title = "Frequency (Hz)"

            f0_range = float(freqs[0])
            f_end_range = float(freqs[-1])
            df_spacing = (f_end_range - f0_range) / n_freqs if n_freqs > 1 else 1.0

        # Configure vtkImageData
        img = vtk.vtkImageData()
        img.SetDimensions(n_times, n_freqs, 1)
        img.SetSpacing(dt, df_spacing, 1.0)
        img.SetOrigin(t0, f0_range, 0.0)

        img.AllocateScalars(vtk.VTK_FLOAT, 1)

        for j in range(n_freqs):
            for i in range(n_times):
                img.SetScalarComponentFromFloat(i, j, 0, 0, float(Z[j, i]))
        img.Modified()

        # Compute limits and LUT
        vmin, vmax = np.min(Z), np.max(Z)
        vmin, vmax = np.round([vmin, vmax], 2)
        lut = self._build_lut("viridis", vmin, vmax)

        # Create chart
        chart = vtk.vtkChartHistogram2D()
        chart.SetInputData(img, 0)
        chart.SetTransferFunction(lut)

        ax_bottom, ax_left = chart.GetAxis(vtk.vtkAxis.BOTTOM), chart.GetAxis(vtk.vtkAxis.LEFT)
        ax_bottom.SetBehavior(0)
        ax_bottom.SetTitle("Time (s)")
        ax_bottom.SetRange(t0, t_end)

        ax_left.SetTitle(ax_title)
        ax_left.SetBehavior(0)
        ax_left.SetLogScale(False)
        ax_left.SetRange(f0_range, f_end_range)

        if log_scale:
            tick_values, tick_labels = self._get_log_ticks_coords(f0_range, f_end_range)

            tick_positions_array = vtk.vtkDoubleArray()
            [tick_positions_array.InsertNextValue(float(pos)) for pos in tick_values]

            tick_labels_array = vtk.vtkStringArray()
            [tick_labels_array.InsertNextValue(label) for label in tick_labels]

            ax_left.SetCustomTickPositions(tick_positions_array, tick_labels_array)
            ax_left.SetNumberOfTicks(0)
        else:
            ax_left.SetTickLabelAlgorithm(vtk.vtkAxis.TICK_WILKINSON_EXTENDED)
            ax_left.SetNumberOfTicks(-1)
            ax_left.SetPrecision(2)

        ax_bottom.GetLabelProperties().SetColor(0, 0, 0)
        ax_left.GetLabelProperties().SetColor(0, 0, 0)

        scene.AddItem(chart)

        # --- Contextual menu ---
        try:
            self.vtk_menu = VTKContextMenu(chart, self.vtk_widget, parent=self.widget)
            self.vtk_menu.set_datastore(self.kernel.get_service("DataStore"))

        except Exception as e:
            QMessageBox.information(self.widget, "Menu", "Error creating contextual map\n" + str(e))

        context_view.GetRenderer().SetBackground(0.98, 0.98, 0.98)
        context_view.GetRenderWindow().Render()
    # end def

    # =====================================================
    # === Colormap LUT & helpers (same logic as individual plugin)
    # =====================================================
    def _build_lut(self, mode: str, vmin: float, vmax: float) -> vtk.vtkLookupTable:
        """Build a lookup table (similar to 'jet' like mapping)."""
        N = 256
        lut = vtk.vtkLookupTable()
        lut.SetNumberOfTableValues(N)
        lut.SetRange(vmin, vmax)
        lut.Build()

        for i in range(N):
            t = i / (N - 1)

            if t < 0.125:
                r, g, b = 0, 0, 0.5 + 0.5 * (t / 0.125)
            elif t < 0.375:
                r, g, b = 0, (t - 0.125) / 0.25, 1
            elif t < 0.625:
                r, g, b = (t - 0.375) / 0.25, 1, 1 - (t - 0.375) / 0.25
            elif t < 0.875:
                r, g, b = 1, 1 - (t - 0.625) / 0.25, 0
            else:
                r, g, b = 1, 0.15 * (1 - (t - 0.875) / 0.125), 0

            r = 0.9 * r + 0.03
            g = 0.9 * g + 0.03
            b = 0.9 * b + 0.03

            lut.SetTableValue(i, r, g, b, 1.0)

        return lut
    # end def

    def _lut_to_ctf(self, lut: vtk.vtkLookupTable) -> vtk.vtkColorTransferFunction:
        """Convert a VTK lookup table into a vtkColorTransferFunction."""
        ctf = vtk.vtkColorTransferFunction()
        ctf.ClampingOn()
        n = lut.GetNumberOfTableValues()
        if n <= 0:
            return ctf
        vmin, vmax = lut.GetRange()
        if vmax == vmin:
            vmin -= 0.5
            vmax += 0.5
        for i in range(n):
            rgba = lut.GetTableValue(i)
            x = vmin + (vmax - vmin) * (i / (n - 1))
            ctf.AddRGBPoint(x, *rgba[:3])
        return ctf
    # end def

# end class

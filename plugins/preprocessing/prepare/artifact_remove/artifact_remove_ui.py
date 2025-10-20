# plugins/preprocessing/prepare/artifact_remove/artifact_remove_ui.py
from PyQt5 import QtWidgets, QtCore, QtGui

class ArtifactPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12); layout.setContentsMargins(10, 10, 10, 10)

        title = QtWidgets.QLabel("Parameters")
        title.setStyleSheet("font-weight: 600; font-size: 14pt; margin-bottom: 5px;")
        layout.addWidget(title)

        group_box = QtWidgets.QGroupBox("Artifact Removal")
        group_layout = QtWidgets.QVBoxLayout(group_box)

        # --- Controles de Navegación de Trials ---
        nav_container = QtWidgets.QWidget()
        nav_layout = QtWidgets.QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(0, 5, 0, 5)

        self.prev_button = QtWidgets.QPushButton("Previous")
        self.next_button = QtWidgets.QPushButton("Next")
        # <<< AÑADIDO: Asignamos el objectName para el estilo QSS >>>
        self.prev_button.setObjectName("trialNavButton")
        self.next_button.setObjectName("trialNavButton")
        # <<< FIN AÑADIDO >>>

        self.trial_status_label = QtWidgets.QLabel("Trial: - / -")
        self.trial_status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.trial_status_label.setStyleSheet("color: red; font-weight: bold;") # Estilo inicial

        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)

        group_layout.addWidget(nav_container)
        group_layout.addWidget(self.trial_status_label)
        
        separator = QtWidgets.QFrame(); separator.setFrameShape(QtWidgets.QFrame.HLine); separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        group_layout.addWidget(separator)

        mod_container = QtWidgets.QWidget()
        form_layout = QtWidgets.QFormLayout(mod_container)
        form_layout.setContentsMargins(0, 10, 0, 0)
        
        self.mode_combo = QtWidgets.QComboBox(); self.mode_combo.addItems(["Interpolate Interval", "Cut From Start"])
        form_layout.addRow("Mode:", self.mode_combo)
        self.point_a = QtWidgets.QLineEdit("0.0"); self.point_b = QtWidgets.QLineEdit("0.0")
        self.point_a.setValidator(QtGui.QDoubleValidator()); self.point_b.setValidator(QtGui.QDoubleValidator())
        self.label_a = QtWidgets.QLabel("Point A:"); self.label_b = QtWidgets.QLabel("Point B:")
        form_layout.addRow(self.label_a, self.point_a); form_layout.addRow(self.label_b, self.point_b)
        group_layout.addWidget(mod_container)
        layout.addWidget(group_box)
        
        self.apply_button = QtWidgets.QPushButton("Apply Changes")
        self.apply_button.setObjectName("mainActionButton")
        self.apply_button.setCursor(QtCore.Qt.PointingHandCursor); self.apply_button.setMinimumHeight(35)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)
        
        self.mode_combo.currentIndexChanged.connect(self.update_ui_for_mode)
        self.update_ui_for_mode()

    def update_ui_for_mode(self):
        is_cut_mode = self.mode_combo.currentText() == "Cut From Start"
        self.label_a.setText("Cut until (s):" if is_cut_mode else "Point A (s):")
        self.label_b.setVisible(not is_cut_mode); self.point_b.setVisible(not is_cut_mode)

class Ui_ArtifactRemove(object):
    def setupUi(self, Form):
        main_layout = QtWidgets.QHBoxLayout(Form)
        self.plotArea = QtWidgets.QFrame(Form); self.plotArea.setFrameShape(QtWidgets.QFrame.StyledPanel)
        main_layout.addWidget(self.plotArea, 3)
        self.artifact_panel = ArtifactPanel(Form); main_layout.addWidget(self.artifact_panel, 1)
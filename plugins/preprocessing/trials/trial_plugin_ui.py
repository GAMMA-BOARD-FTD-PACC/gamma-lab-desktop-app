from PyQt5 import QtCore, QtWidgets

class Ui_Trials(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.setObjectName("TrialsWidget")
        self.resize(938, 665)

        # ===== Root =====
        self._root = QtWidgets.QVBoxLayout(self)
        self._root.setContentsMargins(10, 10, 10, 10)
        self._root.setSpacing(0)

        # ===== Splitter L/R =====
        self.splitter = QtWidgets.QSplitter(self)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self._root.addWidget(self.splitter)

        # ----- Left: VTK viewer frame (keep name) -----
        self.VtkViewer = QtWidgets.QFrame(self.splitter)
        self.VtkViewer.setObjectName("VtkViewer")
        self.VtkViewer.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.VtkViewer.setFrameShadow(QtWidgets.QFrame.Raised)
        self.VtkViewer.setMinimumWidth(520)

        # ----- Right: Parameters panel -----
        self.panel = QtWidgets.QWidget(self.splitter)
        self.vbox = QtWidgets.QVBoxLayout(self.panel)
        self.vbox.setContentsMargins(8, 8, 8, 8)
        self.vbox.setSpacing(12)

        # ===== Header: Parameters =====
        self.lblParameters = QtWidgets.QLabel(self.panel)
        _f_h = self.lblParameters.font()
        _f_h.setPointSize(_f_h.pointSize() + 2)
        _f_h.setBold(True)
        self.lblParameters.setFont(_f_h)
        self.lblParameters.setText("Parameters")
        self.vbox.addWidget(self.lblParameters)

        self.sep0 = QtWidgets.QFrame(self.panel)
        self.sep0.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep0.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep0)

        _f_sub = self.lblParameters.font()
        _f_sub.setPointSize(_f_sub.pointSize() - 2)
        _f_sub.setBold(True)

        # ===== Subtítulo: Channel =====
        self.lblChannelTitle = QtWidgets.QLabel(self.panel)
        self.lblChannelTitle.setFont(_f_sub)
        self.lblChannelTitle.setText("Channel")
        self.vbox.addWidget(self.lblChannelTitle)

        self.sep1 = QtWidgets.QFrame(self.panel)
        self.sep1.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep1.setFrameShadow(QtWidgets.QFrame.Plain)
        self.vbox.addWidget(self.sep1)

        self.formChannel = QtWidgets.QFormLayout()
        self.formChannel.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.formChannel.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        self.channelLabel = QtWidgets.QLabel(self.panel)
        self.channelLabel.setText("Name")
        self.channelComboBox = QtWidgets.QComboBox(self.panel) 
        self.channelComboBox.setObjectName("channelComboBox") # se mantiene el nombre
        self.formChannel.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.channelLabel)
        self.formChannel.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.channelComboBox)

        self.vbox.addLayout(self.formChannel)

        # ===== Subtítulo: Threshold =====
        self.lblThTitle = QtWidgets.QLabel(self.panel)
        self.lblThTitle.setFont(_f_sub)
        self.lblThTitle.setText("Threshold")
        self.vbox.addWidget(self.lblThTitle)

        self.sep2 = QtWidgets.QFrame(self.panel)
        self.sep2.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep2.setFrameShadow(QtWidgets.QFrame.Plain)
        self.vbox.addWidget(self.sep2)

        self.formTh = QtWidgets.QFormLayout()
        self.formTh.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.thresholdLabel = QtWidgets.QLabel(self.panel)
        self.thresholdLabel.setText("")  # como en la captura, solo el valor con sufijo
        self.thresholdDoubleSpinBox = QtWidgets.QDoubleSpinBox(self.panel)
        self.thresholdDoubleSpinBox.setDecimals(4)
        self.thresholdDoubleSpinBox.setRange(-1e9, 1e9)
        self.thresholdDoubleSpinBox.setSingleStep(0.01)
        self.thresholdDoubleSpinBox.setValue(0.05)
        self.thresholdDoubleSpinBox.setSuffix(" Hz")
        self.formTh.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.thresholdLabel)
        self.formTh.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.thresholdDoubleSpinBox)

        self.vbox.addLayout(self.formTh)

        # ===== Subtítulo: Stim Number =====
        self.lblStimTitle = QtWidgets.QLabel(self.panel)
        self.lblStimTitle.setFont(_f_sub)
        self.lblStimTitle.setText("Stim Number")
        self.vbox.addWidget(self.lblStimTitle)

        self.sep3 = QtWidgets.QFrame(self.panel)
        self.sep3.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep3.setFrameShadow(QtWidgets.QFrame.Plain)
        self.vbox.addWidget(self.sep3)

        self.formStim = QtWidgets.QFormLayout()
        self.formStim.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # etiqueta vacía para que se vea solo el campo (como tu mock)
        self.stimNumberLabel = QtWidgets.QLabel(self.panel)
        self.stimNumberLabel.setText("")
        self.stimNumberSpinBox = QtWidgets.QSpinBox(self.panel)
        self.stimNumberSpinBox.setRange(0, 1_000_000)
        self.stimNumberSpinBox.setValue(1)
        self.formStim.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.stimNumberLabel)
        self.formStim.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.stimNumberSpinBox)

        self.vbox.addLayout(self.formStim)

        # ===== Subtítulo: Time =====
        self.lblTimeTitle = QtWidgets.QLabel(self.panel)
        self.lblTimeTitle.setFont(_f_sub)
        self.lblTimeTitle.setText("Time")
        self.vbox.addWidget(self.lblTimeTitle)

        self.sep4 = QtWidgets.QFrame(self.panel)
        self.sep4.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep4.setFrameShadow(QtWidgets.QFrame.Plain)
        self.vbox.addWidget(self.sep4)

        self.formTime = QtWidgets.QFormLayout()
        self.formTime.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.initialTimeLabel = QtWidgets.QLabel(self.panel)
        self.initialTimeLabel.setText("Initial Time")
        self.initialTimeDoubleSpinBox = QtWidgets.QDoubleSpinBox(self.panel)
        self.initialTimeDoubleSpinBox.setDecimals(4)
        self.initialTimeDoubleSpinBox.setRange(-1e9, 1e9)
        self.initialTimeDoubleSpinBox.setSingleStep(0.001)
        self.initialTimeDoubleSpinBox.setValue(-0.05)

        self.finalTimeLabel = QtWidgets.QLabel(self.panel)
        self.finalTimeLabel.setText("Final Time")
        self.finalTimeDoubleSpinBox = QtWidgets.QDoubleSpinBox(self.panel)
        self.finalTimeDoubleSpinBox.setDecimals(4)
        self.finalTimeDoubleSpinBox.setRange(-1e9, 1e9)
        self.finalTimeDoubleSpinBox.setSingleStep(0.001)
        self.finalTimeDoubleSpinBox.setValue(3.0)

        self.interStimTimeLabel = QtWidgets.QLabel(self.panel)
        self.interStimTimeLabel.setText("Inter Stim Time")
        self.interStimTimeDoubleSpinBox = QtWidgets.QDoubleSpinBox(self.panel)
        self.interStimTimeDoubleSpinBox.setDecimals(4)
        self.interStimTimeDoubleSpinBox.setRange(-1e9, 1e9)
        self.interStimTimeDoubleSpinBox.setSingleStep(0.001)
        self.interStimTimeDoubleSpinBox.setValue(0.0)

        #Trial End Mode
        self.endModeComboLabel = QtWidgets.QLabel(self.panel)
        self.endModeComboLabel.setText("Trial End Mode")
        self.endModeCombo = QtWidgets.QComboBox(self.panel)
        self.endModeCombo.addItem("Fixed window", userData="fixed")
        self.endModeCombo.addItem("Cut to the next stim", userData="until_next_onset")

        self.formTime.addRow(self.initialTimeLabel, self.initialTimeDoubleSpinBox)
        self.formTime.addRow(self.finalTimeLabel, self.finalTimeDoubleSpinBox)
        self.formTime.addRow(self.interStimTimeLabel, self.interStimTimeDoubleSpinBox)
        self.formTime.addRow(self.endModeComboLabel, self.endModeCombo)

        self.vbox.addLayout(self.formTime)

        # ===== Spacer & Actions =====
        self.vbox.addStretch(1)

        self.Btn_generate_trials = QtWidgets.QPushButton(self.panel)
        self.Btn_generate_trials.setText("Generate Trials")
        self.Btn_generate_trials.setMinimumHeight(36)
        self.vbox.addWidget(self.Btn_generate_trials)

        # Tamaños por defecto del splitter
        self.splitter.setSizes([560, 350])

        self.retranslateUi()

    def retranslateUi(self):
        self.setWindowTitle("Trials")
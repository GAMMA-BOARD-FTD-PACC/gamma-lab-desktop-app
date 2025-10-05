# plugins/preprocessing/trials/trial_plugin_ui.py
from PyQt5 import QtCore, QtWidgets

class Ui_Trials(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.setObjectName("TrialsWidget")
        self.resize(900, 600)

        # layout raíz
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # --- Panel VTK a la izquierda ---
        self.VtkViewer = QtWidgets.QFrame(self)
        self.VtkViewer.setObjectName("VtkViewer")
        self.VtkViewer.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.VtkViewer.setFrameShadow(QtWidgets.QFrame.Raised)
        self.VtkViewer.setMinimumWidth(520)
        root.addWidget(self.VtkViewer, 1)  # expansible

        # --- Formulario a la derecha ---
        formWrap = QtWidgets.QWidget(self)
        formLay = QtWidgets.QFormLayout(formWrap)
        formLay.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        formLay.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        self.channelLabel = QtWidgets.QLabel("Channel", formWrap)
        self.channelSpinBox = QtWidgets.QSpinBox(formWrap)
        formLay.addRow(self.channelLabel, self.channelSpinBox)

        self.stimNumberLabel = QtWidgets.QLabel("Stim Number", formWrap)
        self.stimNumberSpinBox = QtWidgets.QSpinBox(formWrap)
        formLay.addRow(self.stimNumberLabel, self.stimNumberSpinBox)

        self.thresholdLabel = QtWidgets.QLabel("Threshold", formWrap)
        self.thresholdDoubleSpinBox = QtWidgets.QDoubleSpinBox(formWrap)
        formLay.addRow(self.thresholdLabel, self.thresholdDoubleSpinBox)

        self.initialTimeLabel = QtWidgets.QLabel("Initial Time", formWrap)
        self.initialTimeDoubleSpinBox = QtWidgets.QDoubleSpinBox(formWrap)
        formLay.addRow(self.initialTimeLabel, self.initialTimeDoubleSpinBox)
        
        self.finalTimeLabel = QtWidgets.QLabel("Final Time", formWrap)
        self.finalTimeDoubleSpinBox = QtWidgets.QDoubleSpinBox(formWrap)
        formLay.addRow(self.finalTimeLabel, self.finalTimeDoubleSpinBox)

        self.interStimTimeLabel = QtWidgets.QLabel("Inter Stim Time", formWrap)
        self.interStimTimeDoubleSpinBox = QtWidgets.QDoubleSpinBox(formWrap)
        formLay.addRow(self.interStimTimeLabel, self.interStimTimeDoubleSpinBox)

        self.Btn_generate_trials = QtWidgets.QPushButton("Generate Trials", formWrap)
        formLay.addRow(QtWidgets.QLabel("", formWrap), self.Btn_generate_trials)

        root.addWidget(formWrap, 0)  # tamaño preferido, no expansible principal

        # traducciones opcionales (por si quieres usar QCoreApplication.translate)
        self.retranslateUi()

    def retranslateUi(self):
        self.setWindowTitle("Trials")

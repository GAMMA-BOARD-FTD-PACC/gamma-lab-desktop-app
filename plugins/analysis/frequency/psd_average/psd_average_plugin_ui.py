# Ubicación: plugins/analysis/frequency/psd_average/psd_average_plugin_ui.py

# -*- coding: utf-8 -*-
from PyQt5 import QtCore, QtWidgets

class Ui_Psd_average(object):
    """
    UI para el plugin PSD Average.
    """
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(760, 520)

        # Layout raíz del Form
        self._root = QtWidgets.QVBoxLayout(Form)
        self._root.setContentsMargins(10, 10, 10, 10)
        self._root.setSpacing(0)

        # ====== Splitter: izquierda visor / derecha panel ======
        self.splitter = QtWidgets.QSplitter(Form)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self._root.addWidget(self.splitter)

        # --- Lado izquierdo: contenedor para el gráfico/VTK ---
        self.plotArea = QtWidgets.QFrame(self.splitter)
        self.plotArea.setObjectName("plotArea")
        self.plotArea.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.plotArea.setFrameShadow(QtWidgets.QFrame.Raised)

        # --- Lado derecho: panel de parámetros ---
        self.panel = QtWidgets.QWidget(self.splitter)
        self.panel.setObjectName("panel")
        self.vbox = QtWidgets.QVBoxLayout(self.panel)
        self.vbox.setContentsMargins(8, 8, 8, 8)
        self.vbox.setSpacing(12)

        # ====== Header: Parameters ======
        self.lblParameters = QtWidgets.QLabel(self.panel)
        font_h = self.lblParameters.font()
        font_h.setPointSize(font_h.pointSize() + 2)
        font_h.setBold(True)
        self.lblParameters.setFont(font_h)
        self.lblParameters.setText("Parameters")
        self.vbox.addWidget(self.lblParameters)

        self.sep_header = QtWidgets.QFrame(self.panel)
        self.sep_header.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep_header.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep_header)
        
        font_st = self.lblParameters.font() # Re-usamos la fuente
        font_st.setBold(True)

        # ====== Subtítulo: Sample density (Resample) ======
        self.lblSampleTitle = QtWidgets.QLabel(self.panel)
        self.lblSampleTitle.setFont(font_st)
        self.lblSampleTitle.setText("Sample density")
        self.vbox.addWidget(self.lblSampleTitle)

        self.formSample = QtWidgets.QFormLayout()
        self.formSample.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.formSample.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        self.sampleDensityLabel = QtWidgets.QLabel(self.panel)
        self.sampleDensityLabel.setText("Target Fs")
        self.formSample.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.sampleDensityLabel)

        self.sampleDensityDoubleSpinBox = QtWidgets.QDoubleSpinBox(self.panel)
        self.sampleDensityDoubleSpinBox.setDecimals(3)
        self.sampleDensityDoubleSpinBox.setRange(0.0, 1_000_000.0)
        self.sampleDensityDoubleSpinBox.setSingleStep(10.0)
        self.sampleDensityDoubleSpinBox.setValue(0.0)  # 0 = no resample
        self.sampleDensityDoubleSpinBox.setSuffix(" Hz")
        self.sampleDensityDoubleSpinBox.setToolTip("0 = Usar Fs original")
        self.formSample.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.sampleDensityDoubleSpinBox)

        self.vbox.addLayout(self.formSample)

        # Separador
        self.sep2 = QtWidgets.QFrame(self.panel)
        self.sep2.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep2)

        # ====== Subtítulo: Welch Parameters ======
        self.lblWelchTitle = QtWidgets.QLabel(self.panel)
        self.lblWelchTitle.setFont(font_st)
        self.lblWelchTitle.setText("Welch Parameters")
        self.vbox.addWidget(self.lblWelchTitle)

        self.formWelch = QtWidgets.QFormLayout()
        self.formWelch.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # Window
        self.windowLabel = QtWidgets.QLabel(self.panel)
        self.windowLabel.setText("Window")
        self.windowComboBox = QtWidgets.QComboBox(self.panel)
        self.windowComboBox.addItems(['hann', 'hamming', 'blackman', 'bartlett'])
        self.formWelch.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.windowLabel)
        self.formWelch.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.windowComboBox)
        
        # Nperseg
        self.npersegLabel = QtWidgets.QLabel(self.panel)
        self.npersegLabel.setText("N-per-seg")
        self.npersegSpinBox = QtWidgets.QSpinBox(self.panel)
        self.npersegSpinBox.setRange(32, 65536)
        self.npersegSpinBox.setValue(256)
        self.formWelch.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.npersegLabel)
        self.formWelch.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.npersegSpinBox)
        
        # Noverlap
        self.noverlapLabel = QtWidgets.QLabel(self.panel)
        self.noverlapLabel.setText("N-overlap")
        self.noverlapSpinBox = QtWidgets.QSpinBox(self.panel)
        self.noverlapSpinBox.setRange(0, 65535)
        self.noverlapSpinBox.setValue(128)
        self.formWelch.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.noverlapLabel)
        self.formWelch.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.noverlapSpinBox)

        # Nfft
        self.nfftLabel = QtWidgets.QLabel(self.panel)
        self.nfftLabel.setText("N-FFT")
        self.nfftSpinBox = QtWidgets.QSpinBox(self.panel)
        self.nfftSpinBox.setRange(32, 65536)
        self.nfftSpinBox.setValue(256)
        self.formWelch.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.nfftLabel)
        self.formWelch.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.nfftSpinBox)

        self.vbox.addLayout(self.formWelch)

        # Separador
        self.sep3 = QtWidgets.QFrame(self.panel)
        self.sep3.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep3.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep3)
        
        # ====== Subtítulo: Range (Plot) ======
        self.lblRangeTitle = QtWidgets.QLabel(self.panel)
        self.lblRangeTitle.setFont(font_st)
        self.lblRangeTitle.setText("Plot Range")
        self.vbox.addWidget(self.lblRangeTitle)

        self.formRange = QtWidgets.QFormLayout()
        self.formRange.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.highFrecuencyLabel = QtWidgets.QLabel(self.panel)
        self.highFrecuencyLabel.setText("High")
        self.formRange.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.highFrecuencyLabel)

        self.highFrecuencyDoubleSpinBox = QtWidgets.QDoubleSpinBox(self.panel)
        self.highFrecuencyDoubleSpinBox.setDecimals(2)
        self.highFrecuencyDoubleSpinBox.setRange(0.0, 1_000_000.0)
        self.highFrecuencyDoubleSpinBox.setSingleStep(1.0)
        self.highFrecuencyDoubleSpinBox.setValue(40.0)
        self.highFrecuencyDoubleSpinBox.setSuffix(" Hz")
        self.formRange.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.highFrecuencyDoubleSpinBox)

        self.lowFrecuencyLabel = QtWidgets.QLabel(self.panel)
        self.lowFrecuencyLabel.setText("Low")
        self.formRange.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.lowFrecuencyLabel)

        self.lowFrecuencyDoubleSpinBox = QtWidgets.QDoubleSpinBox(self.panel)
        self.lowFrecuencyDoubleSpinBox.setDecimals(2)
        self.lowFrecuencyDoubleSpinBox.setRange(0.0, 1_000_000.0)
        self.lowFrecuencyDoubleSpinBox.setSingleStep(1.0)
        self.lowFrecuencyDoubleSpinBox.setValue(1.0)
        self.lowFrecuencyDoubleSpinBox.setSuffix(" Hz")
        self.formRange.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.lowFrecuencyDoubleSpinBox)

        self.vbox.addLayout(self.formRange)

        # Spacer
        self.vbox.addStretch(1)

        # Botón
        self.pushButton = QtWidgets.QPushButton(self.panel)
        self.pushButton.setObjectName("mainActionButton")
        self.pushButton.setMinimumHeight(36)
        self.vbox.addWidget(self.pushButton)

        # --- Ajuste del splitter ---
        self.splitter.setStretchFactor(0, 1)  # El VtkViewer (izquierda) se expande
        self.splitter.setStretchFactor(1, 0)  # El panel derecho ocupa solo su tamaño mínimo

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _ = QtCore.QCoreApplication.translate
        Form.setWindowTitle(_("PSD Average", "PSD Average"))
        self.pushButton.setText(_("PSD Average", "Calculate PSD Average"))
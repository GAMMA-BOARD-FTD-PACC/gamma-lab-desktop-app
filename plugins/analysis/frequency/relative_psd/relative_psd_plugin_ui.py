# Ubicación: plugins/analysis/frequency/relative_psd/relative_psd_plugin_ui.py

# -*- coding: utf-8 -*-
from PyQt5 import QtCore, QtWidgets

class Ui_Relative_psd(object):
    """
    UI para el plugin Relative PSD.
    Este plugin no tiene área de ploteo, solo panel de
    parámetros y resultados.
    """
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(350, 700) # Más angosto, solo es un panel

        # Layout raíz del Form
        self.vbox = QtWidgets.QVBoxLayout(Form)
        self.vbox.setContentsMargins(10, 10, 10, 10)
        self.vbox.setSpacing(12)
        self.vbox.setAlignment(QtCore.Qt.AlignTop)

        # ====== Header: Parameters ======
        self.lblParameters = QtWidgets.QLabel(Form)
        font_h = self.lblParameters.font()
        font_h.setPointSize(font_h.pointSize() + 2)
        font_h.setBold(True)
        self.lblParameters.setFont(font_h)
        self.lblParameters.setText("Parameters")
        self.vbox.addWidget(self.lblParameters)

        self.sep_header = QtWidgets.QFrame(Form)
        self.sep_header.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep_header.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep_header)
        
        font_st = self.lblParameters.font() # Re-usamos la fuente
        font_st.setBold(True)

        # ====== Subtítulo: Sample density (Resample) ======
        self.lblSampleTitle = QtWidgets.QLabel(Form)
        self.lblSampleTitle.setFont(font_st)
        self.lblSampleTitle.setText("Sample density")
        self.vbox.addWidget(self.lblSampleTitle)

        self.formSample = QtWidgets.QFormLayout()
        self.formSample.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.formSample.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

        self.sampleDensityLabel = QtWidgets.QLabel(Form)
        self.sampleDensityLabel.setText("Target Fs")
        self.formSample.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.sampleDensityLabel)

        self.sampleDensityDoubleSpinBox = QtWidgets.QDoubleSpinBox(Form)
        self.sampleDensityDoubleSpinBox.setDecimals(3)
        self.sampleDensityDoubleSpinBox.setRange(0.0, 1_000_000.0)
        self.sampleDensityDoubleSpinBox.setSingleStep(10.0)
        self.sampleDensityDoubleSpinBox.setValue(0.0)  # 0 = no resample
        self.sampleDensityDoubleSpinBox.setSuffix(" Hz")
        self.sampleDensityDoubleSpinBox.setToolTip("0 = Usar Fs original")
        self.formSample.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.sampleDensityDoubleSpinBox)

        self.vbox.addLayout(self.formSample)

        # Separador
        self.sep2 = QtWidgets.QFrame(Form)
        self.sep2.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep2.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep2)

        # ====== Subtítulo: Welch Parameters ======
        self.lblWelchTitle = QtWidgets.QLabel(Form)
        self.lblWelchTitle.setFont(font_st)
        self.lblWelchTitle.setText("Welch Parameters")
        self.vbox.addWidget(self.lblWelchTitle)

        self.formWelch = QtWidgets.QFormLayout()
        self.formWelch.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        # Window, Nperseg, Noverlap, Nfft... (Idéntico a Psd_average)
        self.windowLabel = QtWidgets.QLabel(Form)
        self.windowLabel.setText("Window")
        self.windowComboBox = QtWidgets.QComboBox(Form)
        self.windowComboBox.addItems(['hann', 'hamming', 'blackman', 'bartlett'])
        self.formWelch.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.windowLabel)
        self.formWelch.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.windowComboBox)
        
        self.npersegLabel = QtWidgets.QLabel(Form)
        self.npersegLabel.setText("N-per-seg")
        self.npersegSpinBox = QtWidgets.QSpinBox(Form)
        self.npersegSpinBox.setRange(32, 65536)
        self.npersegSpinBox.setValue(256)
        self.formWelch.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.npersegLabel)
        self.formWelch.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.npersegSpinBox)
        
        self.noverlapLabel = QtWidgets.QLabel(Form)
        self.noverlapLabel.setText("N-overlap")
        self.noverlapSpinBox = QtWidgets.QSpinBox(Form)
        self.noverlapSpinBox.setRange(0, 65535)
        self.noverlapSpinBox.setValue(128)
        self.formWelch.setWidget(2, QtWidgets.QFormLayout.LabelRole, self.noverlapLabel)
        self.formWelch.setWidget(2, QtWidgets.QFormLayout.FieldRole, self.noverlapSpinBox)

        self.nfftLabel = QtWidgets.QLabel(Form)
        self.nfftLabel.setText("N-FFT")
        self.nfftSpinBox = QtWidgets.QSpinBox(Form)
        self.nfftSpinBox.setRange(32, 65536)
        self.nfftSpinBox.setValue(256)
        self.formWelch.setWidget(3, QtWidgets.QFormLayout.LabelRole, self.nfftLabel)
        self.formWelch.setWidget(3, QtWidgets.QFormLayout.FieldRole, self.nfftSpinBox)

        self.vbox.addLayout(self.formWelch)

        # Separador
        self.sep3 = QtWidgets.QFrame(Form)
        self.sep3.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep3.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep3)
        
        # ====== Subtítulo: Frequency Band (Fq1, Fq2) ======
        self.lblBandTitle = QtWidgets.QLabel(Form)
        self.lblBandTitle.setFont(font_st)
        self.lblBandTitle.setText("Frequency Band")
        self.vbox.addWidget(self.lblBandTitle)

        self.formBand = QtWidgets.QFormLayout()
        self.formBand.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        self.f1Label = QtWidgets.QLabel(Form)
        self.f1Label.setText("Low (Fq1)")
        self.f1DoubleSpinBox = QtWidgets.QDoubleSpinBox(Form)
        self.f1DoubleSpinBox.setDecimals(2)
        self.f1DoubleSpinBox.setRange(0.0, 1_000_000.0)
        self.f1DoubleSpinBox.setValue(8.0) # Default Alpha
        self.f1DoubleSpinBox.setSuffix(" Hz")
        self.formBand.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.f1Label)
        self.formBand.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.f1DoubleSpinBox)

        self.f2Label = QtWidgets.QLabel(Form)
        self.f2Label.setText("High (Fq2)")
        self.f2DoubleSpinBox = QtWidgets.QDoubleSpinBox(Form)
        self.f2DoubleSpinBox.setDecimals(2)
        self.f2DoubleSpinBox.setRange(0.0, 1_000_000.0)
        self.f2DoubleSpinBox.setValue(12.0) # Default Alpha
        self.f2DoubleSpinBox.setSuffix(" Hz")
        self.formBand.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.f2Label)
        self.formBand.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.f2DoubleSpinBox)

        self.vbox.addLayout(self.formBand)

        # Spacer
        self.vbox.addStretch(1)
        
        # ====== Resultados ======
        self.sep4 = QtWidgets.QFrame(Form)
        self.sep4.setFrameShape(QtWidgets.QFrame.HLine)
        self.sep4.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.vbox.addWidget(self.sep4)

        self.lblResultsTitle = QtWidgets.QLabel(Form)
        self.lblResultsTitle.setFont(font_st)
        self.lblResultsTitle.setText("Results")
        self.vbox.addWidget(self.lblResultsTitle)
        
        self.formResults = QtWidgets.QFormLayout()
        self.formResults.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        self.absPowerLabel = QtWidgets.QLabel(Form)
        self.absPowerLabel.setText("Absolute Power (Pow)")
        self.absPowerValue = QtWidgets.QLineEdit("0.0", Form)
        self.absPowerValue.setReadOnly(True)
        self.formResults.setWidget(0, QtWidgets.QFormLayout.LabelRole, self.absPowerLabel)
        self.formResults.setWidget(0, QtWidgets.QFormLayout.FieldRole, self.absPowerValue)

        self.relPowerLabel = QtWidgets.QLabel(Form)
        self.relPowerLabel.setText("Relative Power (Powr)")
        self.relPowerValue = QtWidgets.QLineEdit("0.0", Form)
        self.relPowerValue.setReadOnly(True)
        self.relPowerValue.setToolTip("Porcentaje de la potencia total")
        self.formResults.setWidget(1, QtWidgets.QFormLayout.LabelRole, self.relPowerLabel)
        self.formResults.setWidget(1, QtWidgets.QFormLayout.FieldRole, self.relPowerValue)
        
        self.vbox.addLayout(self.formResults)

        # Botón
        self.pushButton = QtWidgets.QPushButton(Form)
        self.pushButton.setObjectName("mainActionButton")
        self.pushButton.setMinimumHeight(36)
        self.vbox.addWidget(self.pushButton)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        _ = QtCore.QCoreApplication.translate
        Form.setWindowTitle(_("Relative PSD", "Relative PSD"))
        self.pushButton.setText(_("Relative PSD", "Calculate Relative PSD"))
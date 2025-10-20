from PyQt5 import QtCore, QtWidgets

class Ui_ErpPlot(QtWidgets.QWidget):
    """
    Panel ERP Plot (versión simplificada):
    - Centro: QSplitter con dos áreas (butterflyPlot y heatmapPlot).
    - Derecha: parámetros (Select all / Single / Range / Lista de trials / Plot).
    - Sin grupo Advanced y sin botones auxiliares en la lista de trials.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.setObjectName("ErpPlotWidget")
        self.resize(1100, 650)

        # ====== Root layout ======
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ====== Splitter principal (horizontal) ======
        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.main_splitter.setObjectName("main_splitter")
        root.addWidget(self.main_splitter)

        # ====== Centro: QSplitter con 2 zonas de gráficos ======
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.splitter.setObjectName("splitterPlots")

        # Arriba: butterfly plot
        self.butterflyPlot = QtWidgets.QFrame(self.splitter)
        self.butterflyPlot.setObjectName("butterflyPlot")
        self.butterflyPlot.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.butterflyPlot.setMinimumHeight(220)

        # Abajo: heatmap
        self.heatmapPlot = QtWidgets.QFrame(self.splitter)
        self.heatmapPlot.setObjectName("heatmapPlot")
        self.heatmapPlot.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.heatmapPlot.setMinimumHeight(220)

        self.splitter.setSizes([350, 250])
        #root.addWidget(self.splitter, 1)  # expansible


        # ====== Derecha: Panel de parámetros ======
        self.panel = QtWidgets.QFrame(self)
        self.panel.setObjectName("panel_param")
        self.panel.setMinimumWidth(320)
        self.panel.setMaximumWidth(360)
        panelLay = QtWidgets.QVBoxLayout(self.panel)
        panelLay.setContentsMargins(8, 8, 8, 8)
        panelLay.setSpacing(10)

        # --- Group: Parameters ---
        self.grpParameters = QtWidgets.QGroupBox("Parameters", self.panel)
        self.grpParameters.setObjectName("grpParameters")
        g1 = QtWidgets.QVBoxLayout(self.grpParameters)
        g1.setContentsMargins(10, 8, 10, 8)
        g1.setSpacing(8)

        self.chkSelectAll = QtWidgets.QCheckBox("Select all trials", self.grpParameters)
        self.chkSelectAll.setObjectName("chkSelectAll")
        self.chkSelectAll.setChecked(True)

        rowSingle = QtWidgets.QHBoxLayout()
        self.chkSingleTrial = QtWidgets.QCheckBox("Single trial", self.grpParameters)
        self.chkSingleTrial.setObjectName("chkSingleTrial")
        self.spnSingleTrial = QtWidgets.QSpinBox(self.grpParameters)
        self.spnSingleTrial.setObjectName("spnSingleTrial")
        self.spnSingleTrial.setEnabled(False)
        self.spnSingleTrial.setMinimum(1)
        rowSingle.addWidget(self.chkSingleTrial)
        rowSingle.addStretch(1)
        rowSingle.addWidget(self.spnSingleTrial)

        g1.addWidget(self.chkSelectAll)
        g1.addLayout(rowSingle)
        panelLay.addWidget(self.grpParameters)

        # --- Group: Range ---
        self.grpRange = QtWidgets.QGroupBox("Range", self.panel)
        self.grpRange.setObjectName("grpRange")
        g2 = QtWidgets.QGridLayout(self.grpRange)
        g2.setContentsMargins(10, 8, 10, 8)
        g2.setHorizontalSpacing(6)
        g2.setVerticalSpacing(6)

        self.chkUseRange = QtWidgets.QCheckBox("Trials", self.grpRange)
        self.chkUseRange.setObjectName("chkUseRange")
        self.chkUseRange.setChecked(False)

        self.spnFrom = QtWidgets.QSpinBox(self.grpRange)
        self.spnFrom.setObjectName("spnFrom")
        self.spnFrom.setEnabled(False)
        self.spnFrom.setMinimum(1)

        self.lblTo = QtWidgets.QLabel("To", self.grpRange)
        self.lblTo.setAlignment(QtCore.Qt.AlignCenter)

        self.spnTo = QtWidgets.QSpinBox(self.grpRange)
        self.spnTo.setObjectName("spnTo")
        self.spnTo.setEnabled(False)
        self.spnTo.setMinimum(1)

        g2.addWidget(self.chkUseRange, 0, 0)
        g2.addWidget(self.spnFrom,     0, 1)
        g2.addWidget(self.lblTo,       0, 2)
        g2.addWidget(self.spnTo,       0, 3)
        panelLay.addWidget(self.grpRange)

        # --- Group: Trials (filtro + lista) ---
        self.grpTrials = QtWidgets.QGroupBox("Trials", self.panel)
        self.grpTrials.setObjectName("grpTrials")
        g3 = QtWidgets.QVBoxLayout(self.grpTrials)
        g3.setContentsMargins(10, 8, 10, 8)
        g3.setSpacing(6)

        self.txtFilter = QtWidgets.QLineEdit(self.grpTrials)
        self.txtFilter.setObjectName("txtFilter")
        self.txtFilter.setPlaceholderText("filter…")
        g3.addWidget(self.txtFilter)

        self.lstTrials = QtWidgets.QListWidget(self.grpTrials)
        self.lstTrials.setObjectName("lstTrials")
        self.lstTrials.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.lstTrials.setAlternatingRowColors(True)
        g3.addWidget(self.lstTrials, 1)

        panelLay.addWidget(self.grpTrials, 1)

        # --- Plot button ---
        self.btnPlot = QtWidgets.QPushButton("Plot ERP", self.panel)
        self.btnPlot.setObjectName("mainActionButton")

       # self.btnPlot.setObjectName("btnPlot")
        self.btnPlot.setMinimumHeight(36)
        panelLay.addWidget(self.btnPlot)

        panelLay.addStretch(1)
        #root.addWidget(self.panel, 0)  # no expansible principal
        self.main_splitter.addWidget(self.splitter)


        self.panel.setMinimumWidth(250)
        # self.panel.setMaximumWidth(600)
        self.main_splitter.setSizes([1000, self.panel.minimumWidth()])


        self.main_splitter.addWidget(self.splitter)
        self.main_splitter.addWidget(self.panel)

        
        # Tamaños por defecto del splitter
        self.main_splitter.setStretchFactor(0, 1)  # El VtkViewer (izquierda) se expande
        self.main_splitter.setStretchFactor(1, 0)  # El panel derecho ocupa solo su tamaño mínimo


        self._wireDefaultState()
        self.retranslateUi()

    def _wireDefaultState(self):
        # Estados por defecto y reglas de habilitación
        self.chkSelectAll.toggled.connect(self._onSelectAllToggled)
        self.chkSingleTrial.toggled.connect(self._onSingleToggled)
        self.chkUseRange.toggled.connect(self._onRangeToggled)

        self._onSelectAllToggled(self.chkSelectAll.isChecked())
        self._onSingleToggled(self.chkSingleTrial.isChecked())
        self._onRangeToggled(self.chkUseRange.isChecked())

    # ==== reglas de habilitación ====
    def _onSelectAllToggled(self, on: bool):
        if on:
            self.chkSingleTrial.setChecked(False)
            self.chkUseRange.setChecked(False)
        self._updateEnabled()

    def _onSingleToggled(self, on: bool):
        if on:
            self.chkSelectAll.setChecked(False)
            self.chkUseRange.setChecked(False)
        self._updateEnabled()

    def _onRangeToggled(self, on: bool):
        if on:
            self.chkSelectAll.setChecked(False)
            self.chkSingleTrial.setChecked(False)
        self._updateEnabled()

    def _updateEnabled(self):
        sel_all = self.chkSelectAll.isChecked()
        single  = self.chkSingleTrial.isChecked()
        rng     = self.chkUseRange.isChecked()

        self.spnSingleTrial.setEnabled(single)
        self.spnFrom.setEnabled(rng)
        self.spnTo.setEnabled(rng)

        # Lista de trials habilitada solo en modo manual
        manual = not (sel_all or single or rng)
        self.txtFilter.setEnabled(manual)
        self.lstTrials.setEnabled(manual)

    def retranslateUi(self):
        self.setWindowTitle("ERP Plot")

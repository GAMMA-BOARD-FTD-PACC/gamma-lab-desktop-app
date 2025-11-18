from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWebEngineWidgets import QWebEngineView


class Ui_FAQ(object):
    def setupUi(self, FAQ):
        FAQ.setObjectName("FAQ")

        # Layout principal horizontal
        self.mainLayout = QtWidgets.QHBoxLayout(FAQ)
        self.mainLayout.setObjectName("mainLayout")
        self.mainLayout.setSpacing(0)

        # Splitter horizontal
        self.splitter = QtWidgets.QSplitter(FAQ)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")
        self.mainLayout.addWidget(self.splitter)

        # --- Left Area: PDF Workspace ---
        self.pdfArea = QtWidgets.QFrame(self.splitter)
        self.pdfArea.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.pdfArea.setFrameShadow(QtWidgets.QFrame.Raised)
        self.pdfArea.setObjectName("pdfArea")

        self.pdfLayout = QtWidgets.QVBoxLayout(self.pdfArea)
        self.pdfLayout.setContentsMargins(0, 0, 0, 0)
        self.pdfLayout.setSpacing(0)

        self.pdfView = QWebEngineView(self.pdfArea)
        self.pdfLayout.addWidget(self.pdfView)

        # --- Right Area: Button Panel ---
        self.scrollArea = QtWidgets.QScrollArea(self.splitter)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scrollArea.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.layoutWidget = QtWidgets.QWidget()
        self.layoutWidget.setObjectName("layoutWidget")

        self.paramsLayout = QtWidgets.QVBoxLayout(self.layoutWidget)
        self.paramsLayout.setContentsMargins(8, 0, 8, 0)
        self.paramsLayout.setSpacing(12)

        self.scrollArea.setWidget(self.layoutWidget)
        self.splitter.addWidget(self.scrollArea)

        # ==== Title ====
        self.titleLabel = QtWidgets.QLabel(self.layoutWidget)
        self.titleLabel.setObjectName("titleLabel")
        self.titleLabel.setProperty("variant", "title")
        self.titleLabel.setAlignment(QtCore.Qt.AlignLeft)
        self.paramsLayout.addWidget(self.titleLabel)

        self.line = QtWidgets.QFrame(self.layoutWidget)
        self.line.setFrameShape(QtWidgets.QFrame.HLine)
        self.line.setProperty("role", "section-divider")
        self.paramsLayout.addWidget(self.line)

        # ==== Buttons ====
        self.repoButton = QtWidgets.QPushButton(self.layoutWidget)
        self.repoButton.setObjectName("mainActionButton")
        self.paramsLayout.addWidget(self.repoButton)

        self.docsButton = QtWidgets.QPushButton(self.layoutWidget)
        self.docsButton.setObjectName("mainActionButton")
        self.paramsLayout.addWidget(self.docsButton)

        self.videosButton = QtWidgets.QPushButton(self.layoutWidget)
        self.videosButton.setObjectName("mainActionButton")
        self.paramsLayout.addWidget(self.videosButton)

        self.downloadButton = QtWidgets.QPushButton(self.layoutWidget)
        self.downloadButton.setObjectName("mainActionButton")
        self.paramsLayout.addWidget(self.downloadButton)

        self.paramsLayout.addStretch(1)

        # Size splitter: PDF workspace grande, panel pequeño
        self.splitter.setSizes([700, 300])
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)

        self.retranslateUi(FAQ)
        QtCore.QMetaObject.connectSlotsByName(FAQ)

    def retranslateUi(self, FAQ):
        _translate = QtCore.QCoreApplication.translate
        FAQ.setWindowTitle(_translate("FAQ", "Documentation"))
        self.titleLabel.setText(_translate("FAQ", "Resources and Documentation"))
        self.repoButton.setText(_translate("FAQ", "Official project repository"))
        self.docsButton.setText(_translate("FAQ", "Project documentation"))
        self.videosButton.setText(_translate("FAQ", "Tutorial videos and guides"))
        self.downloadButton.setText(_translate("FAQ", "Download Gamma Lab"))

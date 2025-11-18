from PyQt5 import QtCore, QtGui, QtWidgets
import webbrowser


class Ui_FAQ(object):
    def setupUi(self, FAQ):
        FAQ.setObjectName("FAQ")

        self.mainLayout = QtWidgets.QVBoxLayout(FAQ)
        self.mainLayout.setObjectName("mainLayout")
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(14)

        # ==== Title ====
        self.titleLabel = QtWidgets.QLabel(FAQ)
        self.titleLabel.setObjectName("titleLabel")
        self.titleLabel.setProperty("variant", "title")
        self.titleLabel.setAlignment(QtCore.Qt.AlignLeft)
        self.mainLayout.addWidget(self.titleLabel)

        self.line = QtWidgets.QFrame(FAQ)
        self.line.setFrameShape(QtWidgets.QFrame.HLine)
        self.line.setObjectName("line")
        self.line.setProperty("role", "section-divider")
        self.mainLayout.addWidget(self.line)

        # ==== Buttons ====

        # Repositorio oficial
        self.repoButton = QtWidgets.QPushButton(FAQ)
        self.repoButton.setObjectName("mainActionButton")
        self.mainLayout.addWidget(self.repoButton)

        # Documentación del proyecto
        self.docsButton = QtWidgets.QPushButton(FAQ)
        self.docsButton.setObjectName("mainActionButton")
        self.mainLayout.addWidget(self.docsButton)

        # Videos tutoriales
        self.videosButton = QtWidgets.QPushButton(FAQ)
        self.videosButton.setObjectName("mainActionButton")
        self.mainLayout.addWidget(self.videosButton)

        # Descargas / Releases
        self.downloadButton = QtWidgets.QPushButton(FAQ)
        self.downloadButton.setObjectName("mainActionButton")
        self.mainLayout.addWidget(self.downloadButton)

        self.mainLayout.addStretch(1)

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

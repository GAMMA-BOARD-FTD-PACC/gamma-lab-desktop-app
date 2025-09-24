from PyQt5 import QtCore, QtGui, QtWidgets

class Ui_OpenAbfSignal(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi()

    def setupUi(self):
        self.resize(800, 600)
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(QtCore.QRect(30, 50, 241, 16))
        self.label.setObjectName("label")
        
        self.VtkViewr = QtWidgets.QFrame(self)
        self.VtkViewr.setGeometry(QtCore.QRect(30, 100, 701, 461))
        self.VtkViewr.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.VtkViewr.setFrameShadow(QtWidgets.QFrame.Raised)
        self.VtkViewr.setObjectName("VtkViewr")

        self.Btn_abrir_senal = QtWidgets.QPushButton(self)
        self.Btn_abrir_senal.setGeometry(QtCore.QRect(320, 50, 75, 23))
        self.Btn_abrir_senal.setObjectName("Btn_abrir_senal")

        self.retranslateUi()

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.label.setText(_translate("OpenAbfSignal", "Lectura de señal abf usando VTK y pyqt"))
        self.Btn_abrir_senal.setText(_translate("OpenAbfSignal", "Abrir señal"))

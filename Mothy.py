from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy
import sys
from motor import MotorSettings
from cam import Controls
from dpad import DPad
from visuals import ImagePlotWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(0)  # Reduce space between widgets
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        # Add three instances of SimpleWidget
        self.dpad = DPad()
        self.motor1 = MotorSettings("Alt", self)
        self.motor2 = MotorSettings("Azi", self)
        self.motor3 = MotorSettings("Focus", self)
        self.cmaera_controls = Controls()
        self.imgplot = ImagePlotWidget()

        # Set fixed size policy to preserve geometry
        self.dpad.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        controols = QVBoxLayout()
        controols.addWidget(self.dpad)
        controols.addWidget(self.motor1)
        controols.addWidget(self.motor2)
        controols.addWidget(self.motor3)
        controols.addWidget(self.cmaera_controls)

        visuals = QVBoxLayout()
        visuals.addWidget(self.imgplot)

        self.main_layout.addLayout(visuals)
        self.main_layout.addLayout(controols)




        central_widget.setLayout(self.main_layout)
        self.setCentralWidget(central_widget)
        self.setWindowTitle("PyQt5 Main Window with SimpleWidgets")

        # self.setGeometry(100, 100, 400, 600)

    def adjust_size(self):
        """ Dynamically resize main window based on visible widgets. """
        total_height = 0
        for i in range(self.main_layout.count()):
            widget = self.main_layout.itemAt(i).widget()
            if widget.isVisible():
                total_height += widget.sizeHint().height()

        # Adjust the window height dynamically
        self.resize(self.width(), total_height )  # Add padding

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
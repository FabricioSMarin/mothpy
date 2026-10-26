from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QCheckBox
from PyQt5.QtCore import pyqtSignal
import sys

class MotorSettings(QWidget):
    settingsChanged = pyqtSignal()

    def __init__(self, title, parent=None):
        super().__init__(parent)  # Pass parent reference
        self.title = title
        self.res = None
        self.velo = None
        self.acc = None
        self.bac = None
        self.inverted = False
        self.initUI()


    def initUI(self):
        self.main_layout = QVBoxLayout()
        
        # Toggle button
        self.toggle_button = QPushButton(self.title)
        self.toggle_button.setCheckable(True)
        self.main_layout.addWidget(self.toggle_button)
        
        # Widget container for collapsible section
        self.container = QWidget()
        self.fields_layout = QVBoxLayout()
        self.container.setLayout(self.fields_layout)
        
        # Define labels and line edits
        self.fields = {}
        labels = [
            ("Resolution", "Resolution (steps/rev):"),
            ("Velocity", "Velocity (steps/sec):"),
            ("Acceleration", "Acceleration:"),
            ("Backlash", "Backlash:"),
        ]
        
        for key, display in labels:
            row_layout = QHBoxLayout()
            lbl = QLabel(display)
            lbl.setFixedWidth(160)
            line_edit = QLineEdit()
            line_edit.setFixedWidth(120)
            self.fields[key] = line_edit
            row_layout.addWidget(lbl)
            row_layout.addWidget(line_edit)
            self.fields_layout.addLayout(row_layout)
        
        # Add Invert checkbox
        invert_layout = QHBoxLayout()
        self.invert_checkbox = QCheckBox("Invert Direction")
        self.invert_checkbox.setStyleSheet("color: #ffaa66;")
        invert_layout.addWidget(self.invert_checkbox)
        invert_layout.addStretch()
        self.fields_layout.addLayout(invert_layout)
        
        self.main_layout.addWidget(self.container)
        self.setLayout(self.main_layout)
        self.setWindowTitle("Collapsible PyQt5 Widget")
        # self.setGeometry(100, 100, 300, 200)

        self.toggle_button.toggled.connect(self.toggle_fields)
        self.fields["Resolution"].editingFinished.connect(self.update_resolution)
        self.fields["Velocity"].editingFinished.connect(self.update_velocity)
        self.fields["Acceleration"].editingFinished.connect(self.update_acceleration)
        self.fields["Backlash"].editingFinished.connect(self.update_backlash)
        self.invert_checkbox.stateChanged.connect(self.update_inverted)

        return self.main_layout

    def toggle_fields(self, checked):

        # Notify parent MainWindow to adjust size
        if self.parent():
            self.parent().adjust_size()

    def toggle_fields(self, checked):
        if checked:
            self.container.hide()
            self.toggle_button.setText(f"Show {self.title}")
        else:
            self.container.show()
            self.toggle_button.setText(self.title)

        # Notify MainWindow to adjust size
        main_window = self.window()  # Get reference to MainWindow
        # if isinstance(main_window, QMainWindow):  # Ensure it's MainWindow
        #     main_window.adjust_size()

    def update_resolution(self):
        try:
            res = eval(self.fields["Resolution"].text())
            if res<=0: 
                raise Exception()
            setattr(self, "res", res)
            self.settingsChanged.emit()
        except:
            setattr(self, "res", None)
            print("Invalid resolution")
            self.fields["Resolution"].setText("")
        
    def update_velocity(self):
        try:
            velo = eval(self.fields["Velocity"].text())
            if velo<=0: 
                raise Exception()
            setattr(self, "velo", velo)
            self.settingsChanged.emit()
        except:
            setattr(self, "velo", None)
            print("Invalid velocity")
            self.fields["Velocity"].setText("")

    def update_acceleration(self):
        try:
            acc = eval(self.fields["Acceleration"].text())
            if acc<=0: 
                raise Exception()
            setattr(self, "acc", acc)
            self.settingsChanged.emit()
        except:
            setattr(self, "acc", None)
            print("Invalid acceleration")
            self.fields["Acceleration"].setText("")

    def update_backlash(self):
        try:
            bac = eval(self.fields["Backlash"].text())
            if bac < 0: 
                raise Exception()
            setattr(self, "bac", bac)
            self.settingsChanged.emit()
        except:
            setattr(self, "bac", None)
            print("Invalid backlash")
            self.fields["Backlash"].setText("")
    
    def update_inverted(self, state):
        self.inverted = bool(state)
        self.settingsChanged.emit()
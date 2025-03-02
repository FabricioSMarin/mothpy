from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame
import sys

class MotorSettings(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)  # Pass parent reference
        self.title = title
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
        labels = ["Resolution", "Velocity", "Acceleration", "Backlash"]
        
        for label in labels:
            row_layout = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(100)
            line_edit = QLineEdit()
            line_edit.setFixedWidth(150)
            self.fields[label] = line_edit
            row_layout.addWidget(lbl)
            row_layout.addWidget(line_edit)
            self.fields_layout.addLayout(row_layout)
        
        self.main_layout.addWidget(self.container)
        self.setLayout(self.main_layout)
        self.setWindowTitle("Collapsible PyQt5 Widget")
        # self.setGeometry(100, 100, 300, 200)

        self.toggle_button.toggled.connect(self.toggle_fields)
        self.fields["Resolution"].editingFinished.connect(self.update_resolution)
        self.fields["Velocity"].editingFinished.connect(self.update_velocity)
        self.fields["Acceleration"].editingFinished.connect(self.update_acceleration)
        self.fields["Backlash"].editingFinished.connect(self.update_backlash)

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
            setattr(self, "res", )
        except:
            setattr(self, "res", None)
            print("Invalid resolution")
            self.fields["Resolution"].setText("")
        
    def update_velocity(self):
        try:
            velo = eval(self.fields["Velocity"].text())
            if velo<=0: 
                raise Exception()
            setattr(self, "velo", eval(self.fields["Velocity"].text()))
        except:
            setattr(self, "velo", None)
            print("Invalid velocity")
            self.fields["Velocity"].setText("")

    def update_acceleration(self):
        try:
            acc = eval(self.fields["Acceleration"].text())
            if acc<=0: 
                raise Exception()
            setattr(self, "acc", eval(self.fields["Acceleration"].text()))
        except:
            setattr(self, "acc", None)
            print("Invalid acceleration")
            self.fields["Acceleration"].setText("")

    def update_backlash(self):
        try:
            bac = eval(self.fields["Backlash"].text())
            if bac <= 0: 
                raise Exception()
            setattr(self, "bac", eval(self.fields["Backlash"].text()))
        except:
            setattr(self, "bac", None)
            print("Invalid backlash")
            self.fields["Backlash"].setText("")
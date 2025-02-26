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
        self.toggle_button.toggled.connect(self.toggle_fields)
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
        if isinstance(main_window, QMainWindow):  # Ensure it's MainWindow
            main_window.adjust_size()
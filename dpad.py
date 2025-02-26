from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QGridLayout, QSizePolicy, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
import sys
from PyQt5.QtCore import Qt

class DPad(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.layout = QVBoxLayout()
        dpad_layout = QGridLayout()
        dpad_layout.setColumnStretch(0, 1)
        dpad_layout.setColumnStretch(1, 1)
        dpad_layout.setColumnStretch(2, 1)
        dpad_layout.setRowStretch(0, 1)
        dpad_layout.setRowStretch(1, 1)
        dpad_layout.setRowStretch(2, 1)
        
        button_width = 100  # Twice the height
        button_height = 50
        
        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.left_button = QPushButton("Left")
        self.right_button = QPushButton("Right")
        
        for button in [self.up_button, self.down_button, self.left_button, self.right_button]:
            button.setFixedSize(button_width, button_height)
        
        self.center_button = QPushButton()
        self.center_button.setCheckable(True)
        self.center_button.setStyleSheet(
            "border-radius: 25px; background-color: gray;"
            "border: 5px solid transparent;"
        )
        self.center_button.setFixedSize(button_height, button_height)  # Keep center button square
        self.center_button.clicked.connect(self.toggle_center_button)
        self.center_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        dpad_layout.addWidget(self.up_button, 0, 1, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.left_button, 1, 0, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.center_button, 1, 1, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.right_button, 1, 2, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.down_button, 2, 1, alignment=Qt.AlignCenter)
        
        self.layout.addLayout(dpad_layout)
        
        # Add label/lineedit pairs
        controls_layout = QVBoxLayout()
        
        ud_layout = QHBoxLayout()
        ud_label = QLabel("U/D:")
        self.ud_lineedit = QLineEdit()
        ud_layout.addWidget(ud_label)
        ud_layout.addWidget(self.ud_lineedit)
        
        lr_layout = QHBoxLayout()
        lr_label = QLabel("L/R:")
        self.lr_lineedit = QLineEdit()
        lr_layout.addWidget(lr_label)
        lr_layout.addWidget(self.lr_lineedit)
        
        controls_layout.addLayout(ud_layout)
        controls_layout.addLayout(lr_layout)
        
        self.layout.addLayout(controls_layout)
        
        self.setLayout(self.layout)
        self.setWindowTitle("D-Pad Widget")
        self.setGeometry(100, 100, 300, 250)

        return self.layout

    def toggle_center_button(self):
        if self.center_button.isChecked():
            self.center_button.setStyleSheet(
                "border-radius: 25px; background-color: gray;"
                "border: 5px solid green;"
            )
        else:
            self.center_button.setStyleSheet(
                "border-radius: 25px; background-color: gray;"
                "border: 5px solid transparent;"
            )

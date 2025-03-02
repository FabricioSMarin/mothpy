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
        dpad_layout.setRowStretch(3, 1)  # Additional row for Near & Far buttons

        button_width = 100  # Twice the height
        button_height = 50

        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.left_button = QPushButton("Left")
        self.right_button = QPushButton("Right")
        self.near_button = QPushButton("Near")  # Below "Left"
        self.far_button = QPushButton("Far")  # Below "Right"

        # Set button sizes
        for button in [self.up_button, self.down_button, self.left_button, self.right_button, self.near_button, self.far_button]:
            button.setFixedSize(button_width, button_height)

        # track button (toggleable)
        self.track_button = QPushButton()
        self.track_button.setCheckable(True)
        self.track_button.setStyleSheet(
            "border-radius: 25px; background-color: gray;"
            "border: 5px solid transparent;"
        )
        self.track_button.setFixedSize(button_height, button_height)  # Keep center button square
        self.track_button.clicked.connect(self.toggle_track_button)
        self.track_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Grid structure:
        dpad_layout.addWidget(self.up_button, 0, 1, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.left_button, 1, 0, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.track_button, 1, 1, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.right_button, 1, 2, alignment=Qt.AlignCenter)

        # Add "Down" button in its usual place
        dpad_layout.addWidget(self.down_button, 2, 1, alignment=Qt.AlignCenter)

        # Add "Near" and "Far" directly below "Left" and "Right" respectively
        dpad_layout.addWidget(self.near_button, 2, 0, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.far_button, 2, 2, alignment=Qt.AlignCenter)

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

        nf_layout = QHBoxLayout()
        lr_label = QLabel("N/F:")
        self.nf_lineedit = QLineEdit()
        nf_layout.addWidget(lr_label)
        nf_layout.addWidget(self.nf_lineedit)

        controls_layout.addLayout(ud_layout)
        controls_layout.addLayout(lr_layout)
        controls_layout.addLayout(nf_layout)

        self.layout.addLayout(controls_layout)

        self.setLayout(self.layout)
        self.setWindowTitle("D-Pad Widget")
        self.setGeometry(100, 100, 300, 300)

        return self.layout
    
    def toggle_track_button(self):
        if self.track_button.isChecked():
            self.track_button.setStyleSheet(
                "border-radius: 25px; background-color: gray;"
                "border: 5px solid green;"
            )
        else:
            self.track_button.setStyleSheet(
                "border-radius: 25px; background-color: gray;"
                "border: 5px solid transparent;"
            )

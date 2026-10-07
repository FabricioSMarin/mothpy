from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QGridLayout, QSizePolicy, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox
import sys
from PyQt5.QtCore import Qt

class DPad(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        button_width = 100
        button_height = 50

        self.up_button = QPushButton("Up")
        self.down_button = QPushButton("Down")
        self.left_button = QPushButton("Left")
        self.right_button = QPushButton("Right")
        self.near_button = QPushButton("Near")
        self.far_button = QPushButton("Far")

        for button in [self.up_button, self.down_button, self.left_button, self.right_button, self.near_button, self.far_button]:
            button.setFixedSize(button_width, button_height)

        self.track_button = QPushButton()
        self.track_button.setCheckable(True)
        self.track_button.setStyleSheet(
            "border-radius: 25px; background-color: gray;"
            "border: 5px solid transparent;"
        )
        self.track_button.setFixedSize(button_height, button_height)
        self.track_button.clicked.connect(self.toggle_track_button)
        self.track_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Compact 3x3 pad — no column stretch so it stays centered as a block
        dpad_layout = QGridLayout()
        dpad_layout.setContentsMargins(0, 0, 0, 0)
        dpad_layout.setHorizontalSpacing(6)
        dpad_layout.setVerticalSpacing(6)
        dpad_layout.addWidget(self.up_button, 0, 1, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.left_button, 1, 0, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.track_button, 1, 1, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.right_button, 1, 2, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.near_button, 2, 0, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.down_button, 2, 1, alignment=Qt.AlignCenter)
        dpad_layout.addWidget(self.far_button, 2, 2, alignment=Qt.AlignCenter)

        dpad_buttons = QWidget()
        dpad_buttons.setLayout(dpad_layout)
        dpad_buttons.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(dpad_buttons)
        button_row.addStretch(1)
        self.layout.addLayout(button_row)

        # Step amount fields below the pad
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)

        ud_layout = QHBoxLayout()
        ud_label = QLabel("U/D:")
        ud_label.setFixedWidth(36)
        self.ud_lineedit = QLineEdit()
        self.ud_lineedit.setPlaceholderText("steps")
        self.ud_angle_label = QLabel("—")
        self.ud_angle_label.setMinimumWidth(140)
        ud_layout.addWidget(ud_label)
        ud_layout.addWidget(self.ud_lineedit)
        ud_layout.addWidget(self.ud_angle_label)

        lr_layout = QHBoxLayout()
        lr_label = QLabel("L/R:")
        lr_label.setFixedWidth(36)
        self.lr_lineedit = QLineEdit()
        self.lr_lineedit.setPlaceholderText("steps")
        self.lr_angle_label = QLabel("—")
        self.lr_angle_label.setMinimumWidth(140)
        lr_layout.addWidget(lr_label)
        lr_layout.addWidget(self.lr_lineedit)
        lr_layout.addWidget(self.lr_angle_label)

        nf_layout = QHBoxLayout()
        nf_label = QLabel("N/F:")
        nf_label.setFixedWidth(36)
        self.nf_lineedit = QLineEdit()
        self.nf_lineedit.setPlaceholderText("steps")
        self.nf_angle_label = QLabel("—")
        self.nf_angle_label.setMinimumWidth(140)
        nf_layout.addWidget(nf_label)
        nf_layout.addWidget(self.nf_lineedit)
        nf_layout.addWidget(self.nf_angle_label)

        self.stack_checkbox = QCheckBox("Stack while tracking")
        self.stack_checkbox.setChecked(False)
        self.stack_checkbox.setToolTip(
            "Translate to ROI1 and rotate using the ROI1→ROI2 angle before averaging. "
            "Turn off to watch live pointing while tracking."
        )

        controls_layout.addLayout(ud_layout)
        controls_layout.addLayout(lr_layout)
        controls_layout.addLayout(nf_layout)
        controls_layout.addWidget(self.stack_checkbox)
        self.layout.addLayout(controls_layout)

        self.setLayout(self.layout)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setWindowTitle("D-Pad Widget")

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

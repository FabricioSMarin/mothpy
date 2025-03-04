from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox
)
import sys

class Controls(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.layout = QVBoxLayout()

        label_width = 120
        edit_width = 150

        # Connect button
        connection_layout = QHBoxLayout()
        self.connect_camera = QPushButton("Connect Camera")
        self.connect_status = QLabel("Disconnected")
        connection_layout.addWidget(self.connect_camera)
        connection_layout.addWidget(self.connect_status)
        self.layout.addLayout(connection_layout)

        # Exposure Time row
        exposure_layout = QHBoxLayout()
        exposure_label = QLabel("Exposure Time (s):")
        exposure_label.setFixedWidth(label_width)
        self.exposure_edit = QLineEdit()
        self.exposure_edit.setFixedWidth(edit_width)
        exposure_layout.addWidget(exposure_label)
        exposure_layout.addWidget(self.exposure_edit)
        self.layout.addLayout(exposure_layout)

        # Gain row
        gain_layout = QHBoxLayout()
        gain_label = QLabel("Gain:")
        gain_label.setFixedWidth(label_width)
        self.gain_edit = QLineEdit()
        self.gain_edit.setFixedWidth(edit_width)
        gain_layout.addWidget(gain_label)
        gain_layout.addWidget(self.gain_edit)
        self.layout.addLayout(gain_layout)

        color_mode_layout = QHBoxLayout()
        color_mode_label = QLabel("Color Mode:")
        color_mode_label.setFixedWidth(label_width)
        self.color_mode_combobox = QComboBox()
        self.color_mode_combobox.addItems(["Color", "Grayscale"])
        color_mode_layout.addWidget(color_mode_label)
        color_mode_layout.addWidget(self.color_mode_combobox)
        self.layout.addLayout(color_mode_layout)
        
        # Mode selection and start/stop button
        capture_layout = QHBoxLayout()
        self.capture_button = QPushButton("Capture")
        self.capture_button.setCheckable(True)
        
        capture_layout.addWidget(self.capture_button)
        self.layout.addLayout(capture_layout)
        
        self.setLayout(self.layout)
        self.setWindowTitle("Camera Control Widget")
        # self.setGeometry(100, 100, 300, 200)

        return self.layout

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
        self.connect_camera = QPushButton("Connect")
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

        # Number of images row
        num_images_layout = QHBoxLayout()
        num_images_label = QLabel("# images:")
        num_images_label.setFixedWidth(label_width)
        self.num_images_edit = QLineEdit()
        self.num_images_edit.setFixedWidth(edit_width)
        num_images_layout.addWidget(num_images_label)
        num_images_layout.addWidget(self.num_images_edit)
        self.layout.addLayout(num_images_layout)

        # Mode selection and start/stop button
        mode_layout = QHBoxLayout()
        self.mode_combobox = QComboBox()
        self.mode_combobox.addItems(["single", "multiple", "continuous"])
        
        self.start_stop_button = QPushButton("Start")
        self.start_stop_button.setCheckable(True)
        self.start_stop_button.toggled.connect(self.toggle_start_stop)
        
        mode_layout.addWidget(self.mode_combobox)
        mode_layout.addWidget(self.start_stop_button)
        self.layout.addLayout(mode_layout)
        
        self.setLayout(self.layout)
        self.setWindowTitle("Camera Control Widget")
        # self.setGeometry(100, 100, 300, 200)

        return self.layout

    def toggle_start_stop(self, checked):
        self.start_stop_button.setText("Stop" if checked else "Start")

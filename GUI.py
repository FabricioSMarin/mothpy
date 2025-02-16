import sys
import serial
import serial.tools.list_ports
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, 
    QWidget, QLineEdit, QTextEdit, QComboBox
)
from PyQt5.QtCore import QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

CONFIG_FILE = "motor_config.json"

class StepperControlGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ESP32 Stepper Motor Control")
        self.setGeometry(100, 100, 800, 600)

        self.serial_port = None
        self.connect_serial()

        # Load motor settings (resolution & units)
        self.motor_settings = self.load_motor_settings()

        # Position tracking
        self.position_history = [[], [], []]
        self.time_history = []

        self.initUI()

        # Timer for real-time updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_positions)
        self.timer.start(1000)

    def connect_serial(self):
        """Automatically detects ESP32 Serial port and connects."""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            if "USB" in port.description or "ESP32" in port.description:
                try:
                    self.serial_port = serial.Serial(port.device, 115200, timeout=1)
                    print(f"Connected to {port.device}")
                    return
                except serial.SerialException:
                    pass
        print("No ESP32 device found.")

    def load_motor_settings(self):
        """Load or initialize motor settings."""
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            default_settings = {
                "resolution": [200.0, 200.0, 200.0],
                "units": ["degrees", "degrees", "degrees"]
            }
            self.save_motor_settings(default_settings)
            return default_settings

    def save_motor_settings(self, settings):
        """Save motor settings to file."""
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f)

    def initUI(self):
        """Create the GUI layout."""
        main_layout = QVBoxLayout()

        # Motor Resolution and Units
        self.resolution_inputs = []
        self.unit_selectors = []
        main_layout.addWidget(QLabel("Set Motor Resolution & Units:"))

        for i in range(3):
            h_layout = QHBoxLayout()
            h_layout.addWidget(QLabel(f"Motor {i+1}:"))
            res_input = QLineEdit(str(self.motor_settings["resolution"][i]))
            unit_selector = QComboBox()
            unit_selector.addItems(["degrees", "mm", "revolutions"])
            unit_selector.setCurrentText(self.motor_settings["units"][i])
            self.resolution_inputs.append(res_input)
            self.unit_selectors.append(unit_selector)

            set_button = QPushButton("Set")
            set_button.clicked.connect(lambda _, x=i: self.set_resolution(x))
            h_layout.addWidget(res_input)
            h_layout.addWidget(unit_selector)
            h_layout.addWidget(set_button)
            main_layout.addLayout(h_layout)

        # Real-time Position Display
        self.position_display = QTextEdit()
        self.position_display.setReadOnly(True)
        main_layout.addWidget(QLabel("Real-Time Positions:"))
        main_layout.addWidget(self.position_display)

        # Matplotlib Plot
        self.figure, self.ax = plt.subplots()
        self.canvas = FigureCanvas(self.figure)
        main_layout.addWidget(self.canvas)

        # Set main widget and layout
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def send_command(self, command):
        """Sends a command to the ESP32 over Serial."""
        if self.serial_port:
            self.serial_port.write((command + "\n").encode())
            print(f"Sent: {command}")

    def set_resolution(self, motor_index):
        """Sets motor resolution and unit."""
        resolution = float(self.resolution_inputs[motor_index].text())
        unit = self.unit_selectors[motor_index].currentText()
        self.motor_settings["resolution"][motor_index] = resolution
        self.motor_settings["units"][motor_index] = unit
        self.save_motor_settings(self.motor_settings)
        print(f"Motor {motor_index+1} set to {resolution} steps per {unit}")

    def update_positions(self):
        """Requests and displays real-time motor positions."""
        self.send_command("GET_POSITIONS")
        if self.serial_port and self.serial_port.in_waiting:
            response = self.serial_port.readline().decode().strip()
            self.position_display.setText(response)

            # Parse motor positions and update graph
            positions = [int(pos.split(":")[-1].strip()) for pos in response.split("\n") if ":" in pos]
            if len(positions) == 3:
                self.time_history.append(len(self.time_history))
                for i in range(3):
                    converted_position = positions[i] / self.motor_settings["resolution"][i]
                    self.position_history[i].append(converted_position)

                self.ax.clear()
                for i in range(3):
                    self.ax.plot(self.time_history, self.position_history[i], label=f"Motor {i+1} ({self.motor_settings['units'][i]})")
                self.ax.legend()
                self.ax.set_xlabel("Time")
                self.ax.set_ylabel("Position")
                self.canvas.draw()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StepperControlGUI()
    window.show()
    sys.exit(app.exec_())
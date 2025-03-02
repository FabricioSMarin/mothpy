from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy
from PyQt5.QtCore import Qt, QSettings
import sys
import serial
import time
import numpy as np
from scipy.optimize import curve_fit
from motor import MotorSettings
from cam import Controls
from dpad import DPad
from visuals import ImagePlotWidget
import cv2

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("Auranox", "Mothpy")  # Unique organization/app name
        self.esp32_connected = False
        self.trajectory = np.zeros((3,10000))
        self.tracked_points = 0
        self.initUI()
        self.loadSettings()
        self.update_settings()

    def initUI(self):
        central_widget = QWidget()
        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(0)  # Reduce space between widgets
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins

        # Add three instances of SimpleWidget
        self.esp32_connect = QPushButton("connect esp32")
        self.dpad = DPad()
        self.motor1 = MotorSettings("Alt", self)
        self.motor1.setFixedWidth(300)
        self.motor2 = MotorSettings("Azi", self)
        self.motor2.setFixedWidth(300)
        self.motor3 = MotorSettings("Focus", self)
        self.motor3.setFixedWidth(300)
        self.camera_controls = Controls()
        self.camera_controls.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.imgplot = ImagePlotWidget()

        # Set fixed size policy to preserve geometry
        self.dpad.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        controols = QVBoxLayout()
        controols.addWidget(self.esp32_connect)
        controols.addWidget(self.dpad)
        controols.addWidget(self.motor1)
        controols.addWidget(self.motor2)
        controols.addWidget(self.motor3)
        controols.addWidget(self.camera_controls)
        controols.setAlignment(Qt.AlignTop)

        visuals = QVBoxLayout()
        visuals.addWidget(self.imgplot)

        self.main_layout.addLayout(visuals)
        self.main_layout.addLayout(controols)

        central_widget.setLayout(self.main_layout)
        self.setCentralWidget(central_widget)
        self.setWindowTitle("PyQt5 Main Window with SimpleWidgets")

        self.esp32_connect.clicked.connect(self.connect_ESP)
        self.dpad.up_button.clicked.connect(self.up_clicked)
        self.dpad.down_button.clicked.connect(self.down_clicked)
        self.dpad.left_button.clicked.connect(self.left_clicked)
        self.dpad.right_button.clicked.connect(self.right_clicked)
        self.dpad.near_button.clicked.connect(self.near_clicked)
        self.dpad.far_button.clicked.connect(self.far_clicked)
        self.dpad.track_button.clicked.connect(self.track_clicked)

    def closeEvent(self, event):
        """ Triggered when the window is closed, used to save settings. """
        self.saveSettings()
        event.accept()

    def saveSettings(self):
        """ Save the QLineEdit contents to QSettings """
        self.settings.setValue("ud_text", self.dpad.ud_lineedit.text())
        self.settings.setValue("lr_text", self.dpad.lr_lineedit.text())
        self.settings.setValue("nf_text", self.dpad.nf_lineedit.text())

        self.settings.setValue("m1_visibility", self.motor1.toggle_button.isChecked())
        self.settings.setValue("m1_res", self.motor1.fields["Resolution"].text())
        self.settings.setValue("m1_velo", self.motor1.fields["Velocity"].text())
        self.settings.setValue("m1_acc", self.motor1.fields["Acceleration"].text())
        self.settings.setValue("m1_back", self.motor1.fields["Backlash"].text())

        self.settings.setValue("m2_visibility", self.motor2.toggle_button.isChecked())
        self.settings.setValue("m2_res", self.motor2.fields["Resolution"].text())
        self.settings.setValue("m2_velo", self.motor2.fields["Velocity"].text())
        self.settings.setValue("m2_acc", self.motor2.fields["Acceleration"].text())
        self.settings.setValue("m2_back", self.motor2.fields["Backlash"].text())

        self.settings.setValue("m3_visibility", self.motor3.toggle_button.isChecked())
        self.settings.setValue("m3_res", self.motor3.fields["Resolution"].text())
        self.settings.setValue("m3_velo", self.motor3.fields["Velocity"].text())
        self.settings.setValue("m3_acc", self.motor3.fields["Acceleration"].text())
        self.settings.setValue("m3_back", self.motor3.fields["Backlash"].text())

        self.settings.setValue("exposure", self.camera_controls.exposure_edit.text())
        self.settings.setValue("gain", self.camera_controls.gain_edit.text())
        self.settings.setValue("num_images", self.camera_controls.num_images_edit.text())
        self.settings.setValue("mode", self.camera_controls.mode_combobox.currentIndex())

    def loadSettings(self):
        """ Load the QLineEdit contents from QSettings """
        self.dpad.ud_lineedit.setText(self.settings.value("ud_text", ""))
        self.dpad.lr_lineedit.setText(self.settings.value("lr_text", ""))
        self.dpad.nf_lineedit.setText(self.settings.value("nf_text", ""))

        self.motor1.toggle_button.setChecked(self.settings.value("m1_visibility", True))
        self.motor1.fields["Resolution"].setText(self.settings.value("m1_res", ""))
        self.motor1.fields["Velocity"].setText(self.settings.value("m1_velo", ""))
        self.motor1.fields["Acceleration"].setText(self.settings.value("m1_acc", ""))
        self.motor1.fields["Backlash"].setText(self.settings.value("m1_back", ""))

        self.motor2.toggle_button.setChecked(self.settings.value("m2_visibility", True))
        self.motor2.fields["Resolution"].setText(self.settings.value("m2_res", ""))
        self.motor2.fields["Velocity"].setText(self.settings.value("m2_velo", ""))
        self.motor2.fields["Acceleration"].setText(self.settings.value("m2_acc", ""))
        self.motor2.fields["Backlash"].setText(self.settings.value("m2_back", ""))

        self.motor3.toggle_button.setChecked(self.settings.value("m3_visibility", True))
        self.motor3.fields["Resolution"].setText(self.settings.value("m3_res", ""))
        self.motor3.fields["Velocity"].setText(self.settings.value("m3_velo", ""))
        self.motor3.fields["Acceleration"].setText(self.settings.value("m3_acc", ""))
        self.motor3.fields["Backlash"].setText(self.settings.value("m3_back", ""))

        self.camera_controls.exposure_edit.setText(self.settings.value("exposure", ""))
        self.camera_controls.gain_edit.setText(self.settings.value("gain", ""))
        self.camera_controls.num_images_edit.setText(self.settings.value("num_images", ""))
        self.camera_controls.mode_combobox.setCurrentIndex(self.settings.value("mode", 0))
        
    def update_settings(self): 
        attrs = {"res":"Resolution","velo":"Velocity","acc":"Acceleration","bac":"Backlash"}
        for motor in [self.motor1, self.motor2, self.motor3]:
            for attr in attrs.keys():
                try:
                    setattr(motor, attr, eval(motor.fields[attrs[attr]].text()))
                except:
                    setattr(motor, attr, None)
         

    def connect_ESP(self):
        # Replace with the correct port (e.g., "COM3" for Windows, "/dev/ttyUSB0" for Linux/Mac)
        SERIAL_PORT = "/dev/cu.usbserial-0001"  
        BAUD_RATE = 115200  # Default ESP32 baud rate
        self.esp32 = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        self.esp32.write(b'Hello\n')
        time.sleep(2)
        response = self.esp32.readline().decode().strip()
        if response == "Hi":
            self.esp32_connected = True
            self.camera_controls.connect_status.setText("Connected")
        else: 
            self.esp32_connected = False
            self.camera_controls.connect_status.setText("Disconnected")

    def check_esp_connection(self):
        if self.esp32.is_open():
            self.esp32_connected=True
        else:
            self.esp32_connected=False

    def up_clicked(self):
        #"{motor_num},{resolution},{direction},{steps},{velocity},{acceltime},{backlash}\n"
        command =f"{1},{self.motor1.res},{1},{self.dpad.ud_lineedit.text()},{self.motor1.velo},{self.motor1.acc},{self.motor1.bac}\n" 
        self.esp32.write(command.encode())

    def down_clicked(self):
        command =f"{1},{self.motor1.res},{0},{self.dpad.ud_lineedit.text()},{self.motor1.velo},{self.motor1.acc},{self.motor1.bac}\n" 
        self.esp32.write(command.encode())

    def left_clicked(self):
        command =f"{2},{self.motor2.res},{0},{self.dpad.lr_lineedit.text()},{self.motor2.velo},{self.motor2.acc},{self.motor2.bac}\n" 
        self.esp32.write(command.encode())

    def right_clicked(self):
        command =f"{2},{self.motor2.res},{1},{self.dpad.lr_lineedit.text()},{self.motor2.velo},{self.motor2.acc},{self.motor2.bac}\n" 
        self.esp32.write(command.encode())

    def near_clicked(self):
        command =f"{3},{self.motor3.res},{0},{self.dpad.nf_lineedit.text()},{self.motor3.velo},{self.motor3.acc},{self.motor3.bac}\n" 
        self.esp32.write(command.encode())

    def far_clicked(self):
        command =f"{3},{self.motor3.res},{1},{self.dpad.nf_lineedit.text()},{self.motor3.velo},{self.motor3.acc},{self.motor3.bac}\n" 
        self.esp32.write(command.encode())

    def track_clicked(self):
        #if !track.isChecked(): closee thread
        t0 = time.time()
        # x,y = self.get_position()
        #imgs = get_imgs(ROI, exposure_time, gain, num_images, update=True)
        #for i in range (1, imgs.shape[0]):
        #   self.tracked_points+=1
        #   dx,dy = registration(imgs[i-1], imga[i])
            # self.trajectory[self.tracked_points+1][0]+=self.trajectory[self.tracked_points][0]+dx
            # self.trajectory[self.tracked_points+1][1]+=self.trajectory[self.tracked_points][1]+dy
            # self.trajectory[self.tracked_points+1][2]+=self.trajectory[self.tracked_points][2]+time.time()

        #predict(t) = predict_trajectory(self.trajectory)
        #t_overhead = 0.5 
        #x,y = predict(t_overhead+time.time()-t0) 
        #command ="{1},{200},{x>1?1:0},{abs(x)},{300},{0},{backlash}\n"
        # self.esp32.write(command.encode())

        # while tracking.isChecked():
            #start_thread(period=5):
            #when available:
                #get tracking_image (ROI,exposure time, gain, 1, show=False)
                #calculate and append dx, dy, t to self.trajectory. 
                #update predict(t) = predict_trajectory(self.trajectory)

        #plot X vs t, y vs t, X vs Y

        pass

    def connect_camera(self):
        #TODO: 
        pass


    def best_fit_curve(x, y, t, degree=2):
        """
        Create a best fit curve function given arrays of x positions, y positions, and time t.

        Parameters:
            x (array-like): Array of x positions.
            y (array-like): Array of y positions.
            t (array-like): Time array corresponding to x and y positions.
            degree (int): Degree of the polynomial fit (default is 2 for quadratic).

        Returns:
            tuple: Two functions (fx, fy) that predict x and y positions given time.
        """
        # Fit polynomial to x(t) and y(t)
        x_coeffs = np.polyfit(t, x, degree)
        y_coeffs = np.polyfit(t, y, degree)

        # Create polynomial functions
        fx = np.poly1d(x_coeffs)
        fy = np.poly1d(y_coeffs)


        # fx, fy = best_fit_curve(x_data, y_data, t_data)

        # # Predict positions at t=2.5
        # t_test = 2.5
        # print("Predicted x:", fx(t_test))
        # print("Predicted y:", fy(t_test))

        return fx, fy
            
    def check_idle(self, period=600):
        #TODO: if no motion command has been issued in the last 10 minutes, disable motors
        pass

    def image_to_ascii(self, image_path):
        ASCII_CHARS = "@%#*+=-:. "
        # Load image using OpenCV
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not load image. Check the path.")

        # Convert to grayscale if it is RGB
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Resize to 30x30
        resized_image = cv2.resize(gray_image, (30, 30), interpolation=cv2.INTER_AREA)

        # Normalize pixel values to the range of ASCII characters
        ascii_str = ""
        for row in resized_image:
            for pixel in row:
                ascii_str += ASCII_CHARS[pixel // 32]  # Map grayscale value to ASCII character
            ascii_str += "\n"

        # # Example Usage
        # ascii_art = image_to_ascii("example.jpg")
        # print(ascii_art)

        return ascii_str


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
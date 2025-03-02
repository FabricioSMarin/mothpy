from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy
from PyQt5.QtCore import Qt, QSettings
import sys
import serial
import time
import numpy as np
from motor import MotorSettings
from cam import Controls
from dpad import DPad
from visuals import ImagePlotWidget


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
        for motor in [self.motor1, self.motor2, self.motor3]
            for attr in attrs.keys():
                try:
                    setattr(motor, attr, eval(fields[attrs[attr]].text())
                except:
                    setattr(motor, attr, None)

    def update_resolution(self, motor):
        try:
            setattr(motor, "res", eval(fields["Resolution"].text())
        except:
            setattr(motor, "res", None)
        
    def update_velocity(self, motor):
        try:
            setattr(motor, "velo", eval(fields["Velocity"].text())
        except:
            setattr(motor, "velo", None)
        
        
    def update_acceleration(self, motor):
        try:
            setattr(motor, "acc", eval(fields["Acceleration"].text())
        except:
            setattr(motor, "acc", None)
        
    def update_backlash(self, motor):
        try:
            setattr(motor, "bac", eval(fields["Backlash"].text())
        except:
            setattr(motor, "bac", None)
      
         
    def adjust_size(self):
        """ Dynamically resize main window based on visible widgets. """
        total_height = 0
        for i in range(self.main_layout.count()):
            widget = self.main_layout.itemAt(i).widget()
            if widget.isVisible():
                total_height += widget.sizeHint().height()

        # Adjust the window height dynamically
        self.resize(self.width(), total_height )  # Add padding

    def connect_ESP(self):
        # Replace with the correct port (e.g., "COM3" for Windows, "/dev/ttyUSB0" for Linux/Mac)
        SERIAL_PORT = "/dev/ttyUSB0"  
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
        command ="{1},{self.motor1.res},{1},{self.dpad.ud_lineedit.text()},{self.motor1.velo},{self.motor1.acc},{self.motor1.bac}\n" 
        self.esp32.write(command.encode())

    def down_clicked(self):
        command ="{1},{self.motor1.res},{0},{self.dpad.ud_lineedit.text()},{self.motor1.velo},{self.motor1.acc},{self.motor1.bac}\n" 
        self.esp32.write(command.encode())

    def left_clicked(self):
        command ="{2},{self.motor2.res},{0},{self.dpad.lr_lineedit.text()},{self.motor2.velo},{self.motor2.acc},{self.motor2.bac}\n" 
        self.esp32.write(command.encode())

    def right_clicked(self):
        command ="{2},{self.motor2.res},{1},{self.dpad.lr_lineedit.text()},{self.motor2.velo},{self.motor2.acc},{self.motor2.bac}\n" 
        self.esp32.write(command.encode())

    def near_clicked(self):
        command ="{3},{self.motor3.res},{0},{self.dpad.nf_lineedit.text()},{self.motor3.velo},{self.motor3.acc},{self.motor3.bac}\n" 
        self.esp32.write(command.encode())

    def far_clicked(self):
        command ="{3},{self.motor3.res},{1},{self.dpad.nf_lineedit.text()},{self.motor3.velo},{self.motor3.acc},{self.motor3.bac}\n" 
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

    def predict_trajectory(self, data_points, extrapolated_num):

        #TODO: given [x,y,t] build a function as a function of time that best fits the trajectory 
        pass
        
    def check_idle(self, period=600):
        #TODO: if no motion command has been issued in the last 10 minutes, disable motors
        pass
        
    def send_ascii_art(self,img):
        #TODO: send ascii representation of the live image resized to 30x30
        pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QSizePolicy
from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QTimer
from PyQt5 import QtCore
import sys
import serial
import time
import numpy as np
import imageio
from scipy.optimize import curve_fit
import PySpin
from PIL import Image  # Only used for resizing if needed


from motor import MotorSettings
from cam import Controls
from dpad import DPad
from visuals import ImagePlotWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.set_dark_theme()

        self.original_stdout = sys.__stdout__  # Use sys.__stdout__ instead of sys.stdout
        self.stdout_stream = Stream(newText=self.onUpdateText)
        sys.stdout = self.stdout_stream
        self.settings = QSettings("Auranox", "Mothpy")  # Unique organization/app name
        self.esp32_connected = False
        self.trajectory = np.zeros((3,10000))
        self.tracked_points = 0
        self.initUI()
        self.loadSettings()
        self.update_settings()
        self.connect_camera()


    def initUI(self):
        central_widget = QWidget()
        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(0)  # Reduce space between widgets
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins

        self.logbox = QTextEdit("")
        self.logbox.setMinimumWidth(600)
        self.logbox.setFixedHeight(150)
        self.logbox.setStyleSheet("background: rgb(30,30,30); color: rgb(30,70,30)")
        self.logbox.setReadOnly(True)

        # Add three instances of SimpleWidget
        self.esp32_connect = QPushButton("connect esp32")
        self.esp32_label = QLabel("Dsiconnected")
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
        esp32_box = QHBoxLayout()
        esp32_box.addWidget(self.esp32_connect)
        esp32_box.addWidget(self.esp32_label)
        controols = QVBoxLayout()
        controols.addLayout(esp32_box)
        controols.addWidget(self.dpad)
        controols.addWidget(self.motor1)
        controols.addWidget(self.motor2)
        controols.addWidget(self.motor3)
        controols.addWidget(self.camera_controls)
        controols.setAlignment(Qt.AlignTop)

        visuals = QVBoxLayout()
        visuals.addWidget(self.imgplot)
        visuals.addWidget(self.logbox)

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
        self.camera_controls.connect_camera.clicked.connect(self.connect_camera)
        self.camera_controls.capture_button.clicked.connect(self.capture_image)
        self.camera_controls.red_slider.valueChanged.connect(self.update_color_correction)
        self.camera_controls.green_slider.valueChanged.connect(self.update_color_correction)
        self.camera_controls.blue_slider.valueChanged.connect(self.update_color_correction)
        

    def set_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QPushButton {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #4b4b4b;
            }
            QPushButton:pressed {
                background-color: #2b2b2b;
            }
            QLineEdit {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                padding: 3px;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QComboBox {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 3px;
                color: #ffffff;
            }
            QComboBox:drop-down {
                border: 0px;
            }
            QComboBox:down-arrow {
                background-color: #3b3b3b;
            }
            QComboBox QAbstractItemView {
                background-color: #3b3b3b;
                color: #ffffff;
                selection-background-color: #4b4b4b;
            }
        """)
        
    def onUpdateText(self, text):
        cursor = self.logbox.textCursor()
        cursor.insertText(text)
        self.logbox.setTextCursor(cursor)
        self.logbox.ensureCursorVisible()

    def closeEvent(self, event):
        """ Triggered when the window is closed, used to save settings. """
        sys.stdout = self.original_stdout
        self.stdout_stream.newText.disconnect()  
        self.saveSettings()
        self.disconnec_camera()
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
        self.settings.setValue("mode", self.camera_controls.color_mode_combobox.currentIndex())

    def loadSettings(self):
        """ Load the QLineEdit contents from QSettings """
        try:
            self.dpad.ud_lineedit.setText(self.settings.value("ud_text", ""))
            self.dpad.lr_lineedit.setText(self.settings.value("lr_text", ""))
            self.dpad.nf_lineedit.setText(self.settings.value("nf_text", ""))


            val = self.settings.value("m1_visibility", True)
            self.motor1.toggle_button.setChecked(val.lower()=="true" if isinstance(val,str) else val)
            self.motor1.fields["Resolution"].setText(self.settings.value("m1_res", ""))
            self.motor1.fields["Velocity"].setText(self.settings.value("m1_velo", ""))
            self.motor1.fields["Acceleration"].setText(self.settings.value("m1_acc", ""))
            self.motor1.fields["Backlash"].setText(self.settings.value("m1_back", ""))

            val = self.settings.value("m2_visibility", True)
            self.motor2.toggle_button.setChecked(val.lower()=="true" if isinstance(val,str) else val)
            self.motor2.fields["Resolution"].setText(self.settings.value("m2_res", ""))
            self.motor2.fields["Velocity"].setText(self.settings.value("m2_velo", ""))
            self.motor2.fields["Acceleration"].setText(self.settings.value("m2_acc", ""))
            self.motor2.fields["Backlash"].setText(self.settings.value("m2_back", ""))

            val = self.settings.value("m3_visibility", True)
            self.motor3.toggle_button.setChecked(val.lower()=="true" if isinstance(val,str) else val)
            self.motor3.fields["Resolution"].setText(self.settings.value("m3_res", ""))
            self.motor3.fields["Velocity"].setText(self.settings.value("m3_velo", ""))
            self.motor3.fields["Acceleration"].setText(self.settings.value("m3_acc", ""))
            self.motor3.fields["Backlash"].setText(self.settings.value("m3_back", ""))

            self.camera_controls.exposure_edit.setText(self.settings.value("exposure", ""))
            self.camera_controls.gain_edit.setText(self.settings.value("gain", ""))
            self.camera_controls.num_images_edit.setText(self.settings.value("num_images", ""))
            self.camera_controls.mode_combobox.setCurrentIndex(self.settings.value("mode", 0))
        except:
            pass

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
        # SERIAL_PORT = "/dev/cu.usbserial-0001"  #for macos
        SERIAL_PORT = "COM3"  #for Windows
        BAUD_RATE = 115200  # Default ESP32 baud rate
        self.esp32 = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        self.esp32.write(b'Hello\n')
        time.sleep(2)
        response = self.esp32.readline().decode().strip()
        if response == "Hi":
            self.esp32_connected = True
            self.esp32_label.setText("Connected")
            self.send_motor_settings()
        else: 
            self.esp32_connected = False
            self.esp32_label.setText("Disconnected")

    def check_esp_connection(self):
        if self.esp32.is_open():
            self.esp32_connected=True
        else:
            self.esp32_connected=False
            
    def send_motor_settings(self):
        for i, motor, in enumerate([self.motor1, self.motor2, self.motor3]):
            cmd = f"set_backlash:{i},{motor.bac}"
            self.esp32.write(cmd.encode())
            time.sleep(0.1)
            cmd = f"set_acceleration:{i},{motor.acc}"
            self.esp32.write(cmd.encode())
            time.sleep(0.1)
            cmd = f"set_velocity:{i},{motor.velo}"
            self.esp32.write(cmd.encode())

    def up_clicked(self):
        #"{motor_num},{direction},{steps},{velocity},{acceltime},{backlash}\n"
        command =f"move:{1},F,{self.dpad.ud_lineedit.text()}\n"
        self.esp32.write(command.encode())

    def down_clicked(self):
        command =f"move:{1},B,{self.dpad.ud_lineedit.text()}\n" 
        self.esp32.write(command.encode())

    def left_clicked(self):
        command =f"move:{2},B,{self.dpad.lr_lineedit.text()}\n" 
        self.esp32.write(command.encode())

    def right_clicked(self):
        command =f"move:{2},F,{self.dpad.lr_lineedit.text()}\n" 
        self.esp32.write(command.encode())

    def near_clicked(self):
        command =f"move:{3},B,{self.dpad.nf_lineedit.text()}\n" 
        self.esp32.write(command.encode())

    def far_clicked(self):
        command =f"move:{3},F,{self.dpad.nf_lineedit.text()}\n" 
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
        try: 
            # Initialize the PySpin system and connect to the first available camera.
            self.system = PySpin.System.GetInstance()
            self.camList = self.system.GetCameras()
            if self.camList.GetSize() == 0:
                print("No cameras detected!")
                self.camera_controls.connect_status.setText("Disconnected")
                self.camList.Clear()
                self.system.ReleaseInstance()
                # sys.exit(1)
            self.camera_controls.connect_status.setText("Connected")
            self.cam = self.camList[0]
            self.cam.Init()
        except:
            print("no camera connected")

    def capture_image(self):
        # Read parameter values from UI fields with defaults.
        try:
            exposure_time = float(self.camera_controls.exposure_edit.text())
            # Convert seconds to microseconds
            exposure_time = exposure_time   # µs
        except ValueError:
            exposure_time = 10000  # default exposure time 0.01 seconds

        try:
            gain = float(self.camera_controls.gain_edit.text())
        except ValueError:
            gain = 1.0  # default gain

        display_mode = self.camera_controls.color_mode_combobox.currentText()

        nodemap = self.cam.GetNodeMap()
        # Set exposure time
        try:
            exposure_auto = PySpin.CEnumerationPtr(nodemap.GetNode('ExposureAuto'))
            if PySpin.IsAvailable(exposure_auto) and PySpin.IsWritable(exposure_auto):
                exposure_auto.SetIntValue(exposure_auto.GetEntryByName('Off').GetValue())

            exposure_mode = PySpin.CEnumerationPtr(nodemap.GetNode('ExposureMode'))
            if PySpin.IsAvailable(exposure_mode) and PySpin.IsWritable(exposure_mode):
                exposure_mode.SetIntValue(exposure_mode.GetEntryByName('Timed').GetValue())

            # Now set the exposure time
            exposure_node = PySpin.CFloatPtr(nodemap.GetNode("ExposureTime"))
            if PySpin.IsAvailable(exposure_node) and PySpin.IsWritable(exposure_node):
                # Get the exposure time range
                exposure_min = exposure_node.GetMin()
                exposure_max = exposure_node.GetMax()
                # Ensure exposure_time is within valid range
                exposure_time = max(min(exposure_time, exposure_max), exposure_min)
                exposure_node.SetValue(exposure_time)
                print(f"Set exposure time to {exposure_time} µs")
            else:
                print("Exposure time node not available/writable")
        except Exception as e:
            print("Could not set exposure time:", e)

        # Set gain mode to manual and adjust gain value
        try:
            gain_auto = PySpin.CEnumerationPtr(nodemap.GetNode('GainAuto'))
            if PySpin.IsAvailable(gain_auto) and PySpin.IsWritable(gain_auto):
                gain_auto.SetIntValue(gain_auto.GetEntryByName('Off').GetValue())

            gain_node = PySpin.CFloatPtr(nodemap.GetNode("Gain"))
            if PySpin.IsAvailable(gain_node) and PySpin.IsWritable(gain_node):
                # Get the gain range
                gain_min = gain_node.GetMin()
                gain_max = gain_node.GetMax()
                # Ensure gain is within valid range
                gain = max(min(gain, gain_max), gain_min)
                gain_node.SetValue(gain)
                print(f"Set gain to {gain} dB")
            else:
                print("Gain node not available/writable")
        except Exception as e:
            print("Could not set gain:", e)

        try:
            acquisition_mode_node = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionMode"))
            if PySpin.IsAvailable(acquisition_mode_node) and PySpin.IsWritable(acquisition_mode_node):
                acquisition_mode_node.SetIntValue(PySpin.AcquisitionMode_SingleFrame)
        except Exception as e:
            print("Could not set acquisition mode:", e)

        try:
            # Stop any existing acquisition
            if self.cam.IsStreaming():
                self.cam.EndAcquisition()
                time.sleep(0.1)  # Give camera time to stop

            # Reset the camera if needed
            self.cam.DeInit()
            self.cam.Init()
            time.sleep(0.1)  # Give camera time to initialize

            # ... existing exposure and gain setting code ...

            # Begin new acquisition
            self.cam.BeginAcquisition()
            image_np = None

            # Create an image processor instance
            image_processor = PySpin.ImageProcessor()

            # Acquire single image with longer timeout (5000ms instead of 1000ms)
            image_result = self.cam.GetNextImage(3000)
            if image_result.IsIncomplete():
                print("Image incomplete with status %d" % image_result.GetImageStatus())
            else:
                if display_mode == "Color":
                    converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                    image_np = converted_image.GetNDArray()
                else:
                    image_np = image_result.GetNDArray()
            image_result.Release()
            self.cam.EndAcquisition()

            if image_np is not None:
                if display_mode == "Grayscale":
                    if len(image_np.shape) == 3:
                        image_np = np.dot(image_np[..., :3], [0.114, 0.587, 0.299])
                        image_np = image_np.astype(np.uint8)
                self.display_image(image_np)

        except Exception as e:
            print(f"Error capturing image: {e}")
            # Recovery procedure
            try:
                if self.cam.IsStreaming():
                    self.cam.EndAcquisition()
                self.cam.DeInit()
                time.sleep(0.5)  # Wait longer for camera to reset
                self.cam.Init()
            except Exception as recovery_error:
                print(f"Error during recovery: {recovery_error}")
            self.display_image(image_np)

    def update_color_correction(self):
        """Update color correction labels and apply to current image"""
        # Update labels
        self.camera_controls.red_label.setText(f"Red: {self.camera_controls.red_slider.value()/100:.1f}x")
        self.camera_controls.green_label.setText(f"Green: {self.camera_controls.green_slider.value()/100:.1f}x")
        self.camera_controls.blue_label.setText(f"Blue: {self.camera_controls.blue_slider.value()/100:.1f}x")
        
        # If we have an image, apply color correction
        if hasattr(self.imgplot, 'image_data') and self.imgplot.image_data is not None:
            self.apply_color_correction()


    def apply_color_correction(self):
        """Apply color correction to the current image"""
        if len(self.imgplot.image_data.shape) != 3:
            return  # Skip if image is not RGB/BGR
            
        # Get correction factors
        r_factor = self.camera_controls.red_slider.value() / 100
        g_factor = self.camera_controls.green_slider.value() / 100
        b_factor = self.camera_controls.blue_slider.value() / 100
        
        # Make a copy of the original image
        corrected_image = self.imgplot.image_data.copy()
        
        # Apply correction factors (assuming BGR format from OpenCV)
        corrected_image[:, :, 0] = np.clip(corrected_image[:, :, 0] * b_factor, 0, 255)
        corrected_image[:, :, 1] = np.clip(corrected_image[:, :, 1] * g_factor, 0, 255)
        corrected_image[:, :, 2] = np.clip(corrected_image[:, :, 2] * r_factor, 0, 255)
        
        # Update the display
        self.imgplot.image_item.setImage(corrected_image)


    def display_image(self, image_np):
        """
        Convert the NumPy image (which might be grayscale or color) to a QImage
        and display it in the QLabel.
        """
        # if len(image_np.shape) == 2:  # Grayscale image
        #     height, width = image_np.shape
        #     qimage = QImage(image_np.tobytes(), width, height, width, QImage.Format_Grayscale8)
        # else:
        image_np = np.rot90(image_np, k=-1)  # k=-1 rotates 90 degrees clockwise

        self.imgplot.image_data = image_np

        # Apply any existing color correction
        if hasattr(self, 'red_slider'):
            self.apply_color_correction()
        else:
            self.imgplot.image_item.setImage(image_np)


        # Resize ROIs if this is the first image
        if not hasattr(self, 'rois_initialized'):
            self.resize_rois(image_np)
            self.rois_initialized = True
            
        self.imgplot.update_roi_images()

    def resize_rois(self, image_np):
        """Resize ROIs to 10% of the smallest image dimension"""
        if image_np is None:
            return
            
        # Get image dimensions
        if len(image_np.shape) == 2:
            height, width = image_np.shape
        else:
            height, width, _ = image_np.shape
            
        # Calculate size for ROI (10% of smallest dimension)
        roi_size = min(width, height) * 0.1
        
        # Set ROI1 position (top left quarter)
        x1 = width * 0.25 - roi_size/2
        y1 = height * 0.25 - roi_size/2
        self.imgplot.ROI1.setPos([x1, y1])
        self.imgplot.ROI1.setSize([roi_size, roi_size])
        
        # Set ROI2 position (bottom right quarter)
        x2 = width * 0.75 - roi_size/2
        y2 = height * 0.75 - roi_size/2
        self.imgplot.ROI2.setPos([x2, y2])
        self.imgplot.ROI2.setSize([roi_size, roi_size])


    def disconnec_camera(self):
        # Properly deinitialize and release the camera.
        self.cam.DeInit()
        del self.cam
        self.camList.Clear()
        self.system.ReleaseInstance()

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
            



    def track_and_reposition_zoom_region(self, img):
        """Find the brightest feature inside the second zoom region and reposition it."""
        # Get ROI2 position and size
        roi_pos = self.imgplot.ROI2.pos()
        roi_size = self.imgplot.ROI2.size()
        x, y = int(roi_pos[0]), int(roi_pos[1])
        width, height = int(roi_size[0]), int(roi_size[1])

        # Extract ROI region
        roi_img = img[y:y+height, x:x+width]

        # Convert to grayscale if image is in color
        if len(roi_img.shape) == 3:
            gray = np.dot(roi_img[..., :3], [0.114, 0.587, 0.299])  # BGR to grayscale
        else:
            gray = roi_img

        # Find the brightest pixel
        max_loc = np.unravel_index(np.argmax(gray), gray.shape)
        feature_y, feature_x = max_loc  # numpy uses (y,x) ordering

        # Compute the new position of the ROI to center the feature
        new_x = x + feature_x - (width // 2)
        new_y = y + feature_y - (height // 2)

        # Update ROI position
        self.imgplot.ROI2.setPos([new_x, new_y])

        # Log center position over time
        self.region_center_positions_x.append(new_x + width // 2)
        self.region_center_positions_y.append(new_y + height // 2)

    def check_idle(self, period=600):
        #TODO: if no motion command has been issued in the last 10 minutes, disable motors
        pass

    def image_to_ascii(self, image_path):
        ASCII_CHARS = "@%#*+=-:. "
        
        # Load image using imageio
        image = imageio.imread(image_path)
        
        if image is None:
            raise ValueError("Could not load image. Check the path.")

        # Convert to grayscale if it's RGB
        if len(image.shape) == 3:  # Check if image has multiple channels (RGB)
            gray_image = np.dot(image[..., :3], [0.2989, 0.587, 0.114])  # Grayscale conversion
        else:
            gray_image = image  # Image is already grayscale

        # Resize to 30x30
        resized_image = np.array(Image.fromarray(gray_image).resize((30, 30), resample=Image.LANCZOS))

        # Normalize pixel values to the range of ASCII characters
        ascii_str = ""
        for row in resized_image:
            for pixel in row:
                ascii_str += ASCII_CHARS[int(pixel) // 32]  # Map grayscale value to ASCII character
            ascii_str += "\n"

        return ascii_str

class Stream(QtCore.QObject):
    newText = pyqtSignal(str)
    
    def __init__(self, newText=None):
        super().__init__()
        if newText:
            self.newText.connect(newText)
    
    def write(self, text):
        self.newText.emit(str(text))
    
    def flush(self):
        pass  # Need this for file-like object compatibility

    def __del__(self):
        # Disconnect all signals before deletion
        try:
            self.newText.disconnect()
        except:
            pass
        # Restore original stdout if this is the current stdout
        if sys.stdout is self:
            sys.stdout = sys.__stdout__


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
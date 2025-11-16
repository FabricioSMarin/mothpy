from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QSizePolicy, QLineEdit
from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QTimer, QThread, QObject, QUrl
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5 import QtCore
import sys
import os
import time
import numpy as np
import imageio
from scipy.optimize import curve_fit
import PySpin
from PIL import Image  # Only used for resizing if needed
from urllib.parse import urlencode

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
        self.trajectory = np.zeros((3,10000))
        self.tracked_points = 0
        
        # Setup continuous capture timer
        self.capture_timer = QTimer()
        self.capture_timer.timeout.connect(self.capture_single_frame)
        self.is_capturing = False
        
        # Setup tracking timer
        self.tracking_timer = QTimer()
        self.tracking_timer.timeout.connect(self.perform_tracking_update)
        self.is_tracking = False
        self.tracking_interval = 6000  # 6 seconds in milliseconds
        
        # Initialize Qt Network Manager for async HTTP requests (no threads!)
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.setTransferTimeout(5000)  # 5 second timeout (for motor movements)
        self.pending_requests = []  # Track pending network requests
        self.max_concurrent_requests = 5  # Limit concurrent requests
        self.is_closing = False  # Flag to prevent new requests during shutdown
        
        # Hotspot calibration
        self.hotspot_mask = None  # Will store the hot pixel values to subtract
        self.calibration_frames = []  # Buffer for collecting calibration frames
        self.is_calibrating = False  # Flag for calibration mode
        self.dark_frame_path = "dark_frame.npy"  # Path to save/load dark frame
        
        self.initUI()
        self.loadSettings()
        self.update_settings()
        self.load_dark_frame()  # Load dark frame if available
        self.connect_camera()


    def initUI(self):
        central_widget = QWidget()
        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(0)  # Reduce space between widgets
        self.main_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins

        self.logbox = QTextEdit("")
        self.logbox.setFixedHeight(150)
        self.logbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.logbox.setStyleSheet("background: rgb(30,30,30); color: rgb(30,70,30)")
        self.logbox.setReadOnly(True)

        # Add ESP32 IP address field
        self.esp32_ip_edit = QLineEdit("192.168.1.100")  # Default IP
        self.esp32_ip_edit.setPlaceholderText("ESP32 IP Address")
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
        
        # Set imgplot to expand to fill available space
        self.imgplot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Set fixed size policy to preserve geometry
        self.dpad.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        # ESP32 IP address input
        esp32_ip_layout = QHBoxLayout()
        esp32_ip_layout.addWidget(QLabel("ESP32 IP:"))
        esp32_ip_layout.addWidget(self.esp32_ip_edit)
        
        # Arrow key hint label
        self.arrow_key_hint = QLabel("⌨️ Arrow Keys: ↑↓ = Alt | ←→ = Azi | [ ] = Steps")
        self.arrow_key_hint.setStyleSheet("color: #888888; font-size: 10px; padding: 5px;")
        self.arrow_key_hint.setAlignment(Qt.AlignCenter)
        
        # Create controls layout with fixed width
        controols = QVBoxLayout()
        controols.addLayout(esp32_ip_layout)
        controols.addWidget(self.arrow_key_hint)
        controols.addWidget(self.dpad)
        controols.addWidget(self.motor1)
        controols.addWidget(self.motor2)
        controols.addWidget(self.motor3)
        controols.addWidget(self.camera_controls)
        controols.setAlignment(Qt.AlignTop)
        
        # Wrap controls in a widget with fixed size policy
        controls_widget = QWidget()
        controls_widget.setLayout(controols)
        controls_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        controls_widget.setMaximumWidth(320)  # Slightly wider than motor widgets

        visuals = QVBoxLayout()
        visuals.addWidget(self.imgplot)
        visuals.addWidget(self.logbox)

        # Add layouts with stretch factors - visuals gets priority
        self.main_layout.addLayout(visuals, stretch=1)
        self.main_layout.addWidget(controls_widget, stretch=0)

        central_widget.setLayout(self.main_layout)
        self.setCentralWidget(central_widget)
        self.setWindowTitle("PyQt5 Main Window with SimpleWidgets")

        self.dpad.up_button.clicked.connect(self.up_clicked)
        self.dpad.down_button.clicked.connect(self.down_clicked)
        self.dpad.left_button.clicked.connect(self.left_clicked)
        self.dpad.right_button.clicked.connect(self.right_clicked)
        self.dpad.near_button.clicked.connect(self.near_clicked)
        self.dpad.far_button.clicked.connect(self.far_clicked)
        self.dpad.track_button.clicked.connect(self.track_clicked)
        self.camera_controls.connect_camera.clicked.connect(self.connect_camera)
        self.camera_controls.rm_hotspots_button.clicked.connect(self.calibrate_hotspots)
        self.camera_controls.capture_button.clicked.connect(self.capture_image)
        self.camera_controls.capture_mode_combobox.currentIndexChanged.connect(self.on_capture_mode_changed)
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

    def keyPressEvent(self, event):
        """Handle arrow key presses for motor control and bracket keys for step adjustment"""
        key = event.key()
        
        # Arrow Up = Motor 1 (Alt) Forward
        if key == Qt.Key_Up:
            self.up_clicked()
        # Arrow Down = Motor 1 (Alt) Backward
        elif key == Qt.Key_Down:
            self.down_clicked()
        # Arrow Left = Motor 2 (Azi) Forward
        elif key == Qt.Key_Left:
            self.left_clicked()
        # Arrow Right = Motor 2 (Azi) Backward
        elif key == Qt.Key_Right:
            self.right_clicked()
        # ] = Increase step size
        elif key == Qt.Key_BracketRight:
            self.adjust_step_size(100)
        # [ = Decrease step size
        elif key == Qt.Key_BracketLeft:
            self.adjust_step_size(-100)
        else:
            # Pass other keys to parent handler
            super().keyPressEvent(event)
    
    def adjust_step_size(self, delta):
        """Adjust step size for all motors by delta amount"""
        # Get current step value from U/D field
        try:
            current = int(self.dpad.ud_lineedit.text())
        except ValueError:
            current = 100  # Default if empty or invalid
        
        # Calculate new value (minimum 1 step)
        new_value = max(1, current + delta)
        new_text = str(new_value)
        
        # Update all step size fields
        self.dpad.ud_lineedit.setText(new_text)
        self.dpad.lr_lineedit.setText(new_text)
        self.dpad.nf_lineedit.setText(new_text)
        
        print(f"Step size adjusted to: {new_value} steps")

    def closeEvent(self, event):
        """ Triggered when the window is closed, used to save settings. """
        # Set closing flag to prevent new requests
        self.is_closing = True
        
        sys.stdout = self.original_stdout
        self.stdout_stream.newText.disconnect()  
        self.saveSettings()
        
        # Stop continuous capture if running
        if self.is_capturing:
            self.stop_continuous_capture()
        
        # Stop tracking if running
        if hasattr(self, 'is_tracking') and self.is_tracking:
            self.is_tracking = False
            self.tracking_timer.stop()
        
        # Abort all pending network requests
        if hasattr(self, 'pending_requests'):
            for reply in self.pending_requests[:]:
                if reply and not reply.isFinished():
                    reply.abort()
            self.pending_requests.clear()
            print(f"Aborted all pending network requests")
        
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
        
        # Save ESP32 IP address
        self.settings.setValue("esp32_ip", self.esp32_ip_edit.text())
        self.settings.sync()  # Force settings to be written to disk

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
            
            # Load color mode (default to 0 = Color)
            color_mode_index = self.settings.value("mode", 0)
            if isinstance(color_mode_index, str):
                color_mode_index = int(color_mode_index) if color_mode_index.isdigit() else 0
            self.camera_controls.color_mode_combobox.setCurrentIndex(color_mode_index)
            
            # Load ESP32 IP address
            self.esp32_ip_edit.setText(self.settings.value("esp32_ip", "192.168.1.100"))
        except Exception as e:
            print(f"Error loading settings: {e}")

    def update_settings(self): 
        attrs = {"res":"Resolution","velo":"Velocity","acc":"Acceleration","bac":"Backlash"}
        for motor in [self.motor1, self.motor2, self.motor3]:
            for attr in attrs.keys():
                try:
                    setattr(motor, attr, eval(motor.fields[attrs[attr]].text()))
                except:
                    setattr(motor, attr, None)
         
    def get_esp32_url(self):
        """Get the base URL for ESP32 from the IP address field"""
        esp32_ip = self.esp32_ip_edit.text()
        return f"http://{esp32_ip}"
    
    def send_http_request(self, endpoint, params=None, callback=None):
        """Send async HTTP request using Qt's network manager (no threads!)"""
        # Don't start new requests if we're closing
        if self.is_closing:
            return
        
        # Check if we've hit the concurrent request limit
        active_requests = sum(1 for r in self.pending_requests if r and not r.isFinished())
        if active_requests >= self.max_concurrent_requests:
            print(f"Warning: Maximum concurrent HTTP requests ({self.max_concurrent_requests}) reached. Skipping request.")
            return
        
        # Build URL with parameters
        url = f"{self.get_esp32_url()}{endpoint}"
        if params:
            url += "?" + urlencode(params)
        
        # Create and send request
        request = QNetworkRequest(QUrl(url))
        reply = self.network_manager.get(request)
        
        # Store reply to track it
        self.pending_requests.append(reply)
        
        # Connect completion signal
        reply.finished.connect(lambda: self.on_request_finished(reply, callback))
        
    def on_request_finished(self, reply, callback=None):
        """Handle completed network request"""
        # Remove from pending list
        if reply in self.pending_requests:
            self.pending_requests.remove(reply)
        
        # Don't process if we're closing
        if self.is_closing:
            reply.deleteLater()
            return
        
        # Check for errors
        if reply.error() == QNetworkReply.NoError:
            # Success
            result = reply.readAll().data().decode('utf-8')
            if callback:
                callback(result)
        else:
            # Error
            error_string = reply.errorString()
            print(f"ESP32 Error: {error_string}")
            print("Make sure the ESP32 is on the network and the IP is correct.")
        
        # Clean up
        reply.deleteLater()
            
    def send_motor_settings_to_esp32(self):
        """Send motor settings to ESP32 via HTTP (call when settings change)"""
        # Motor 1 = Alt (altitude), Motor 2 = Azi (azimuth)
        motors_to_send = [
            (1, self.motor1),  # Motor 1 = Alt
            (2, self.motor2),  # Motor 2 = Azi
        ]
        
        for motor_num, motor in motors_to_send:
            # Send resolution
            if motor.res:
                self.send_http_request("/set_resolution", {
                    "motor": motor_num,
                    "res": motor.res,
                    "unit": "degrees"
                })
            
            # Send velocity
            if motor.velo:
                self.send_http_request("/set_velocity", {
                    "motor": motor_num,
                    "velocity": motor.velo
                })
            
            # Send acceleration
            if motor.acc:
                self.send_http_request("/set_acceleration", {
                    "motor": motor_num,
                    "accel": motor.acc
                })
            
            # Send backlash
            if motor.bac:
                self.send_http_request("/set_backlash", {
                    "motor": motor_num,
                    "backlsh": motor.bac
                })
            
            time.sleep(0.05)  # Small delay between requests
        
        print("Motor settings sent to ESP32")

    def up_clicked(self):
        """Move Motor 1 (Alt) Backward (reversed for inverted mount)"""
        steps = self.dpad.ud_lineedit.text()
        command = f"move:1,B,{steps}"
        self.send_http_request("/command", {"cmd": command})
        print(f"Moving Alt up: {steps} steps")

    def down_clicked(self):
        """Move Motor 1 (Alt) Forward (reversed for inverted mount)"""
        steps = self.dpad.ud_lineedit.text()
        command = f"move:1,F,{steps}"
        self.send_http_request("/command", {"cmd": command})
        print(f"Moving Alt down: {steps} steps")

    def left_clicked(self):
        """Move Motor 2 (Azi) Forward"""
        steps = self.dpad.lr_lineedit.text()
        command = f"move:2,F,{steps}"
        self.send_http_request("/command", {"cmd": command})
        print(f"Moving Azi left: {steps} steps")

    def right_clicked(self):
        """Move Motor 2 (Azi) Backward"""
        steps = self.dpad.lr_lineedit.text()
        command = f"move:2,B,{steps}"
        self.send_http_request("/command", {"cmd": command})
        print(f"Moving Azi right: {steps} steps")

    def near_clicked(self):
        """Move Motor 3 (Focus) - if connected"""
        steps = self.dpad.nf_lineedit.text()
        print(f"Near/Focus not connected to ESP32 motor")

    def far_clicked(self):
        """Move Motor 3 (Focus) - if connected"""
        steps = self.dpad.nf_lineedit.text()
        print(f"Far/Focus not connected to ESP32 motor")

    def track_clicked(self):
        """Toggle star tracking on/off"""
        if self.dpad.track_button.isChecked():
            # Start tracking
            self.is_tracking = True
            print("=" * 60)
            print("STAR TRACKING STARTED")
            print(f"Update interval: {self.tracking_interval/1000} seconds")
            print(f"Max U/D steps: {self.dpad.ud_lineedit.text()}")
            print(f"Max L/R steps: {self.dpad.lr_lineedit.text()}")
            print("Monitoring left ROI for bright spot...")
            print("=" * 60)
            
            # Ensure continuous capture is running for tracking
            if not self.is_capturing:
                print("Starting continuous capture for tracking...")
                self.camera_controls.capture_mode_combobox.setCurrentText("Continuous")
                self.start_continuous_capture()
            
            # Perform first tracking update immediately
            self.perform_tracking_update()
            
            # Start timer for subsequent updates
            self.tracking_timer.start(self.tracking_interval)
        else:
            # Stop tracking
            self.is_tracking = False
            self.tracking_timer.stop()
            # Hide the crosshair
            self.imgplot.update_star_crosshair(0, 0, visible=False)
            print("=" * 60)
            print("STAR TRACKING STOPPED")
            print("=" * 60)
    
    def perform_tracking_update(self):
        """Analyze ROI and issue correction commands"""
        if not self.is_tracking:
            return
        
        # Make sure we have an image with ROI data
        if not hasattr(self.imgplot, 'image_data') or self.imgplot.image_data is None:
            print("No image available for tracking")
            return
        
        try:
            # Get ROI1 (left box) using pyqtgraph's proper method
            image_data = self.imgplot.image_data
            
            # Use getArraySlice to properly extract the ROI region
            roi_slice, roi_transform = self.imgplot.ROI1.getArraySlice(image_data, self.imgplot.image_item)
            
            if roi_slice is None:
                print("ROI is outside image bounds")
                return
            
            # Extract the ROI data
            roi_img = image_data[roi_slice]
            
            if roi_img.size == 0:
                print("ROI is outside image bounds")
                return
            
            # Get ROI position for coordinate transformation
            roi_pos = self.imgplot.ROI1.pos()
            x, y = int(roi_pos[0]), int(roi_pos[1])
            
            # Convert to grayscale if image is in color
            if len(roi_img.shape) == 3:
                gray = np.dot(roi_img[..., :3], [0.114, 0.587, 0.299])  # BGR to grayscale
            else:
                gray = roi_img
            
            # Find the star using weighted centroid of bright pixels
            # This is more robust than single brightest pixel (which could be noise)
            
            # Get the maximum brightness value
            max_brightness = np.max(gray)
            
            # Set threshold at 80% of max brightness to filter out noise (more aggressive)
            threshold = max_brightness * 0.8
            print(f"  Max brightness in ROI: {max_brightness:.0f}, threshold: {threshold:.0f}")
            
            # Create mask of pixels above threshold
            bright_mask = gray >= threshold
            
            # Check if we found any bright pixels
            if not np.any(bright_mask):
                print("  No bright object found in ROI (all pixels below threshold)")
                return
            
            # Calculate weighted centroid of bright pixels
            # This gives us the center of the bright region (the star)
            y_coords, x_coords = np.where(bright_mask)
            weights = gray[bright_mask]
            
            # Check the spatial extent of the bright region to filter out noise
            x_min, x_max = np.min(x_coords), np.max(x_coords)
            y_min, y_max = np.min(y_coords), np.max(y_coords)
            width_extent = x_max - x_min + 1
            height_extent = y_max - y_min + 1
            diameter = max(width_extent, height_extent)
            
            # Require object to be at least 5 pixels in diameter
            if diameter < 5:
                print(f"  Object too small ({diameter} pixels), likely noise. Need at least 5 pixels.")
                return
            
            star_x = np.average(x_coords, weights=weights)
            star_y = np.average(y_coords, weights=weights)
            
            # Print brightness info for debugging
            num_bright_pixels = np.sum(bright_mask)
            print(f"  Found {num_bright_pixels} bright pixels (diameter: {diameter}px)")
            print(f"  Object bounding box in ROI: X=[{x_min}, {x_max}], Y=[{y_min}, {y_max}]")
            
            # Get ROI dimensions
            roi_height, roi_width = gray.shape if len(gray.shape) == 2 else gray.shape[:2]
            
            # Update crosshair to show tracked star position (in image coordinates)
            star_x_img = x + star_x
            star_y_img = y + star_y
            self.imgplot.update_star_crosshair(star_x_img, star_y_img, visible=True)
            
            print(f"  ROI position: ({x}, {y}), size: ({roi_width}, {roi_height})")
            print(f"  Star centroid in ROI coords: ({star_x:.1f}, {star_y:.1f})")
            print(f"  Star centroid in image coords: ({star_x_img:.1f}, {star_y_img:.1f})")
            
            # Calculate center of ROI
            center_x = roi_width / 2
            center_y = roi_height / 2
            
            # Calculate pixel offset from center
            offset_x = star_x - center_x  # Positive = star is right of center
            offset_y = star_y - center_y  # Positive = star is below center
            
            print(f"\n{'='*50}")
            print(f"TRACKING UPDATE")
            print(f"  Offset from ROI center: X={offset_x:.1f}px, Y={offset_y:.1f}px")
            
            # Get maximum step sizes from UI
            try:
                max_ud_steps = int(self.dpad.ud_lineedit.text())
                max_lr_steps = int(self.dpad.lr_lineedit.text())
            except ValueError:
                print("  Error: Invalid step size in U/D or L/R fields")
                return
            
            # Calculate required steps (scale pixel offset to motor steps)
            # Assume roughly linear relationship: max offset = half ROI size = max steps
            # This gives: steps = offset * (max_steps / (roi_size/2))
            steps_x = int(offset_x * max_lr_steps / (roi_width / 2))
            steps_y = int(offset_y * max_ud_steps / (roi_height / 2))
            
            # Clamp to maximum step sizes
            steps_x = max(min(steps_x, max_lr_steps), -max_lr_steps)
            steps_y = max(min(steps_y, max_ud_steps), -max_ud_steps)
            
            # Determine movement directions
            # Positive offset_x = star right of center = need to move RIGHT (motor 2 backward)
            # Negative offset_x = star left of center = need to move LEFT (motor 2 forward)
            # Positive offset_y = star below center = need to move UP (motor 1 forward)
            # Negative offset_y = star above center = need to move DOWN (motor 1 backward)
            
            # Issue correction commands
            if abs(steps_y) > 5:  # Only move if offset is significant (>5 steps)
                direction_ud = "F" if steps_y > 0 else "B"  # UP/DOWN normal
                command = f"move:1,{direction_ud},{abs(steps_y)}"
                print(f"  Altitude correction: {abs(steps_y)} steps {'UP' if steps_y > 0 else 'DOWN'}")
                self.send_http_request("/command", {"cmd": command})
            else:
                print(f"  Altitude: centered (offset {steps_y} steps)")
            
            if abs(steps_x) > 5:  # Only move if offset is significant (>5 steps)
                direction_lr = "B" if steps_x > 0 else "F"  # LEFT/RIGHT inverted
                command = f"move:2,{direction_lr},{abs(steps_x)}"
                print(f"  Azimuth correction: {abs(steps_x)} steps {'RIGHT' if steps_x > 0 else 'LEFT'}")
                self.send_http_request("/command", {"cmd": command})
            else:
                print(f"  Azimuth: centered (offset {steps_x} steps)")
            
        except Exception as e:
            print(f"Tracking error: {e}")

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
                return  # Exit early if no camera found
            
            # Camera found - initialize it
            self.camera_controls.connect_status.setText("Connected")
            self.cam = self.camList[0]
            self.cam.Init()
            
            # Configure camera for long exposures immediately after init
            try:
                nodemap = self.cam.GetNodeMap()
                s_nodemap = self.cam.GetTLStreamNodeMap()
                
                # Configure stream layer for long exposures
                try:
                    # Set stream buffer count mode to manual
                    stream_buffer_count_mode = PySpin.CEnumerationPtr(s_nodemap.GetNode('StreamBufferCountMode'))
                    if PySpin.IsAvailable(stream_buffer_count_mode) and PySpin.IsWritable(stream_buffer_count_mode):
                        stream_buffer_count_mode.SetIntValue(stream_buffer_count_mode.GetEntryByName('Manual').GetValue())
                        print("Stream buffer count mode set to Manual")
                    
                    # Increase buffer count for long exposures
                    stream_buffer_count = PySpin.CIntegerPtr(s_nodemap.GetNode('StreamBufferCountManual'))
                    if PySpin.IsAvailable(stream_buffer_count) and PySpin.IsWritable(stream_buffer_count):
                        stream_buffer_count.SetValue(10)
                        print("Stream buffer count set to 10")
                    
                    # Set buffer handling mode to NewestOnly to prevent memory issues
                    stream_buffer_handling = PySpin.CEnumerationPtr(s_nodemap.GetNode('StreamBufferHandlingMode'))
                    if PySpin.IsAvailable(stream_buffer_handling) and PySpin.IsWritable(stream_buffer_handling):
                        stream_buffer_handling.SetIntValue(stream_buffer_handling.GetEntryByName('NewestOnly').GetValue())
                        print("Stream buffer handling mode set to NewestOnly")
                except Exception as stream_error:
                    print(f"Warning: Could not configure stream settings: {stream_error}")
                
                # Disable frame rate control to allow long exposures
                try:
                    frame_rate_enable = PySpin.CBooleanPtr(nodemap.GetNode('AcquisitionFrameRateEnable'))
                    if PySpin.IsAvailable(frame_rate_enable) and PySpin.IsWritable(frame_rate_enable):
                        frame_rate_enable.SetValue(False)
                        print("Frame rate control disabled - long exposures enabled")
                except:
                    # Try alternative node name
                    try:
                        frame_rate_auto = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionFrameRateAuto'))
                        if PySpin.IsAvailable(frame_rate_auto) and PySpin.IsWritable(frame_rate_auto):
                            frame_rate_auto.SetIntValue(frame_rate_auto.GetEntryByName('Off').GetValue())
                            print("Frame rate auto set to Off - long exposures enabled")
                    except:
                        print("Could not disable frame rate control (may not be available)")
                
                # Set frame rate to very low value (0.1 fps = 10 second max exposure theoretically)
                try:
                    frame_rate = PySpin.CFloatPtr(nodemap.GetNode('AcquisitionFrameRate'))
                    if PySpin.IsAvailable(frame_rate) and PySpin.IsWritable(frame_rate):
                        frame_rate_min = frame_rate.GetMin()
                        frame_rate.SetValue(frame_rate_min)
                        print(f"Frame rate set to minimum: {frame_rate_min} fps")
                except Exception as fr_error:
                    print(f"Could not set frame rate: {fr_error}")
                
                # Disable trigger mode
                try:
                    trigger_mode = PySpin.CEnumerationPtr(nodemap.GetNode('TriggerMode'))
                    if PySpin.IsAvailable(trigger_mode) and PySpin.IsWritable(trigger_mode):
                        trigger_mode.SetIntValue(trigger_mode.GetEntryByName('Off').GetValue())
                        print("Trigger mode disabled")
                except:
                    pass
                    
            except Exception as config_error:
                print(f"Warning: Could not fully configure camera: {config_error}")
            
            # Enable hotspot calibration button
            self.camera_controls.rm_hotspots_button.setEnabled(True)
            
            print("Camera connected and initialized")
        except Exception as e:
            print(f"Error connecting camera: {e}")
            self.camera_controls.connect_status.setText("Disconnected")
            self.camera_controls.rm_hotspots_button.setEnabled(False)

    def load_dark_frame(self):
        """Load dark frame from disk if available"""
        try:
            if os.path.exists(self.dark_frame_path):
                self.hotspot_mask = np.load(self.dark_frame_path)
                print("=" * 60)
                print("DARK FRAME LOADED FROM DISK")
                print(f"File: {self.dark_frame_path}")
                mean_value = np.mean(self.hotspot_mask)
                max_value = np.max(self.hotspot_mask)
                print(f"Dark frame stats: Mean={mean_value:.1f}, Max={max_value:.1f}")
                print("Dark frame will be subtracted from all images")
                print("=" * 60)
            else:
                print(f"No saved dark frame found at {self.dark_frame_path}")
        except Exception as e:
            print(f"Error loading dark frame: {e}")
            self.hotspot_mask = None
    
    def save_dark_frame(self):
        """Save dark frame to disk"""
        try:
            if self.hotspot_mask is not None:
                np.save(self.dark_frame_path, self.hotspot_mask)
                print(f"Dark frame saved to {self.dark_frame_path}")
        except Exception as e:
            print(f"Error saving dark frame: {e}")
    
    def calibrate_hotspots(self):
        """Start dark frame calibration using 10 frames (lens cap on)"""
        print("=" * 60)
        print("DARK FRAME CALIBRATION STARTED")
        print("*** PUT LENS CAP ON NOW ***")
        print("Collecting 10 frames to create dark frame...")
        print("=" * 60)
        
        # Reset calibration data
        self.calibration_frames = []
        self.is_calibrating = True
        self.hotspot_mask = None
        
        # Set button text to show calibration is in progress
        self.camera_controls.rm_hotspots_button.setText("Calibrating...")
        self.camera_controls.rm_hotspots_button.setEnabled(False)
        
        # Start continuous capture if not already running
        was_capturing = self.is_capturing
        if not was_capturing:
            self.camera_controls.capture_mode_combobox.setCurrentText("Continuous")
            self.start_continuous_capture()
        
        # Timer will automatically stop after 10 frames are collected
        # (handled in capture_single_frame)
    
    def finish_hotspot_calibration(self):
        """Process collected frames to create dark frame (average of all frames)"""
        if len(self.calibration_frames) < 10:
            print(f"Error: Only collected {len(self.calibration_frames)} frames")
            self.is_calibrating = False
            self.camera_controls.rm_hotspots_button.setText("Dark Frame")
            self.camera_controls.rm_hotspots_button.setEnabled(True)
            return
        
        print("Creating dark frame from collected images...")
        
        # Convert frames to numpy array and calculate mean
        # This creates a dark frame by averaging all the lens-cap-on images
        frames = np.array(self.calibration_frames)  # Shape: (10, height, width, [channels])
        
        # Calculate average across all frames - this is our dark frame
        self.hotspot_mask = np.mean(frames, axis=0).astype(np.float32)
        
        # Calculate some statistics for user feedback
        mean_value = np.mean(self.hotspot_mask)
        max_value = np.max(self.hotspot_mask)
        
        print("=" * 60)
        print(f"DARK FRAME CALIBRATION COMPLETE")
        print(f"Created dark frame from {len(self.calibration_frames)} frames")
        print(f"Dark frame stats: Mean={mean_value:.1f}, Max={max_value:.1f}")
        print(f"Dark frame will be subtracted from all subsequent images")
        print("*** YOU CAN REMOVE THE LENS CAP NOW ***")
        print("=" * 60)
        
        # Save dark frame to disk
        self.save_dark_frame()
        
        # Clean up
        self.calibration_frames = []
        self.is_calibrating = False
        self.camera_controls.rm_hotspots_button.setText("Dark Frame")
        self.camera_controls.rm_hotspots_button.setEnabled(True)
    
    def on_capture_mode_changed(self):
        """Handle mode change - stop continuous capture if switching away from it"""
        if self.is_capturing:
            self.stop_continuous_capture()
        
        # Update button text based on mode
        capture_mode = self.camera_controls.capture_mode_combobox.currentText()
        if capture_mode == "Single":
            self.camera_controls.capture_button.setText("Capture")
        else:
            self.camera_controls.capture_button.setText("Start")
    
    def capture_image(self):
        """Main capture function that handles both single and continuous modes"""
        capture_mode = self.camera_controls.capture_mode_combobox.currentText()
        
        if capture_mode == "Single":
            # Single shot mode
            self.capture_single_frame()
            self.camera_controls.capture_button.setChecked(False)
        else:
            # Continuous mode - toggle on/off
            if self.is_capturing:
                # Stop continuous capture
                self.stop_continuous_capture()
            else:
                # Start continuous capture
                self.start_continuous_capture()
    
    def start_continuous_capture(self):
        """Start continuous image capture"""
        self.is_capturing = True
        self.camera_controls.capture_button.setText("Stop")
        # Capture at ~10 fps (100ms interval) - adjust as needed for your camera
        self.capture_timer.start(100)  # milliseconds
        print("Started continuous capture mode")
    
    def stop_continuous_capture(self):
        """Stop continuous image capture"""
        self.is_capturing = False
        self.capture_timer.stop()
        
        # Update button based on current mode
        capture_mode = self.camera_controls.capture_mode_combobox.currentText()
        if capture_mode == "Continuous":
            self.camera_controls.capture_button.setText("Start")
        else:
            self.camera_controls.capture_button.setText("Capture")
        self.camera_controls.capture_button.setChecked(False)
        
        # Stop camera acquisition
        try:
            if self.cam.IsStreaming():
                self.cam.EndAcquisition()
        except:
            pass
        print("Stopped continuous capture mode")
    
    def capture_single_frame(self):
        """Capture a single frame from the camera"""
        # Determine if we're in continuous mode (check this first)
        is_continuous = self.is_capturing
        
        # Read parameter values from UI fields with defaults.
        try:
            exposure_time = float(self.camera_controls.exposure_edit.text())
            # Input is already in microseconds
        except ValueError:
            exposure_time = 10000  # default exposure time 10000 µs

        try:
            gain = float(self.camera_controls.gain_edit.text())
        except ValueError:
            gain = 1.0  # default gain

        display_mode = self.camera_controls.color_mode_combobox.currentText()

        nodemap = self.cam.GetNodeMap()
        # Set exposure time
        try:
            # First, disable frame rate control to allow long exposures
            try:
                frame_rate_enable = PySpin.CBooleanPtr(nodemap.GetNode('AcquisitionFrameRateEnable'))
                if PySpin.IsAvailable(frame_rate_enable) and PySpin.IsWritable(frame_rate_enable):
                    frame_rate_enable.SetValue(False)
                    if not is_continuous:
                        print("Disabled frame rate control to allow long exposures")
            except:
                # Try alternative node name
                try:
                    frame_rate_auto = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionFrameRateAuto'))
                    if PySpin.IsAvailable(frame_rate_auto) and PySpin.IsWritable(frame_rate_auto):
                        frame_rate_auto.SetIntValue(frame_rate_auto.GetEntryByName('Off').GetValue())
                        if not is_continuous:
                            print("Set frame rate auto to Off")
                except:
                    pass  # Frame rate control might not be available
            
            # Ensure trigger mode is off for free-running capture
            try:
                trigger_mode = PySpin.CEnumerationPtr(nodemap.GetNode('TriggerMode'))
                if PySpin.IsAvailable(trigger_mode) and PySpin.IsWritable(trigger_mode):
                    trigger_mode.SetIntValue(trigger_mode.GetEntryByName('Off').GetValue())
                    if not is_continuous:
                        print("Set trigger mode to Off")
            except:
                pass
            
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
                requested_exposure = exposure_time
                was_clamped = False
                
                if exposure_time > exposure_max:
                    exposure_time = exposure_max
                    was_clamped = True
                    if not is_continuous:
                        print(f"WARNING: Requested exposure {requested_exposure} µs exceeds camera maximum!")
                        print(f"         Setting to maximum: {exposure_max} µs ({exposure_max/1000:.3f} ms)")
                elif exposure_time < exposure_min:
                    exposure_time = exposure_min
                    was_clamped = True
                    if not is_continuous:
                        print(f"WARNING: Requested exposure {requested_exposure} µs below camera minimum!")
                        print(f"         Setting to minimum: {exposure_min} µs")
                
                exposure_node.SetValue(exposure_time)
                
                # Read back the actual value set
                actual_exposure = exposure_node.GetValue()
                
                # Only print if not in continuous mode to reduce spam
                if not is_continuous and not was_clamped:
                    print(f"Exposure set to: {actual_exposure} µs ({actual_exposure/1000:.3f} ms)")
                    print(f"Camera range: {exposure_min/1000:.1f} - {exposure_max/1000:.1f} ms")
            else:
                if not is_continuous:
                    print("Exposure time node not available/writable")
        except Exception as e:
            if not is_continuous:
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
                # Only print if not in continuous mode to reduce spam
                if not is_continuous:
                    print(f"Set gain to {gain} dB")
            else:
                if not is_continuous:
                    print("Gain node not available/writable")
        except Exception as e:
            if not is_continuous:
                print("Could not set gain:", e)
        
        try:
            acquisition_mode_node = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionMode"))
            if PySpin.IsAvailable(acquisition_mode_node) and PySpin.IsWritable(acquisition_mode_node):
                if is_continuous:
                    acquisition_mode_node.SetIntValue(PySpin.AcquisitionMode_Continuous)
                else:
                    acquisition_mode_node.SetIntValue(PySpin.AcquisitionMode_SingleFrame)
        except Exception as e:
            if not is_continuous:
                print("Could not set acquisition mode:", e)

        try:
            # Only reset camera if not already in continuous mode
            if not is_continuous or not self.cam.IsStreaming():
                # Stop any existing acquisition
                if self.cam.IsStreaming():
                    self.cam.EndAcquisition()
                    time.sleep(0.1)  # Give camera time to stop

                # Reset the camera if needed (only for single frame mode)
                if not is_continuous:
                    self.cam.DeInit()
                    time.sleep(0.2)  # Wait for camera to fully deinitialize
                    self.cam.Init()
                    time.sleep(0.3)  # Give camera time to initialize

                # Begin new acquisition
                self.cam.BeginAcquisition()
                time.sleep(0.1)  # Wait for acquisition to start
                if not is_continuous:
                    print("Acquisition started, waiting for image...")

            image_np = None

            # Create an image processor instance
            image_processor = PySpin.ImageProcessor()

            # Calculate timeout based on exposure time with generous buffer
            # For short exposures: exposure + 3 seconds
            # For long exposures (>1s): exposure * 2 + 5 seconds (double exposure time plus buffer)
            if exposure_time > 1000000:  # If exposure > 1 second
                timeout_ms = int(exposure_time / 1000 * 2) + 5000
            else:
                timeout_ms = max(3000, int(exposure_time / 1000) + 3000)
            
            # Inform user about long exposure
            if not is_continuous and exposure_time >= 500000:  # 500ms or longer
                if exposure_time >= 1000000:  # 1 second or more
                    print(f"Long exposure: {exposure_time/1000000:.1f} seconds. Please wait...")
                    print(f"Using {timeout_ms/1000:.1f} second timeout")
                else:
                    print(f"Long exposure: {exposure_time/1000:.0f} ms. Please wait...")
            
            # Acquire image with timeout (use calculated timeout for both modes)
            image_result = self.cam.GetNextImage(timeout_ms)
            if image_result.IsIncomplete():
                print("Image incomplete with status %d" % image_result.GetImageStatus())
            else:
                if display_mode == "Color":
                    # Convert to color BGR8
                    converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                    image_np = converted_image.GetNDArray()
                elif display_mode == "Grayscale":
                    # Convert to color first, then to grayscale
                    converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                    image_color = converted_image.GetNDArray()
                    if len(image_color.shape) == 3:
                        image_np = np.dot(image_color[..., :3], [0.114, 0.587, 0.299])
                        image_np = image_np.astype(np.uint8)
                    else:
                        image_np = image_color
                else:  # Mono mode
                    # Get raw monochrome data from camera
                    try:
                        converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_Mono8)
                        image_np = converted_image.GetNDArray()
                    except:
                        # Fallback to raw data if Mono8 conversion fails
                        image_np = image_result.GetNDArray()
            
            image_result.Release()
            
            # Only end acquisition in single frame mode
            if not is_continuous:
                self.cam.EndAcquisition()

            if image_np is not None:
                # Collect frames for dark frame calibration
                if self.is_calibrating and len(self.calibration_frames) < 10:
                    self.calibration_frames.append(image_np.copy())
                    print(f"Dark frame {len(self.calibration_frames)}/10 collected")
                    
                    if len(self.calibration_frames) == 10:
                        # Stop capture and process calibration
                        self.stop_continuous_capture()
                        self.finish_hotspot_calibration()
                
                # Apply dark frame subtraction if available
                if self.hotspot_mask is not None and not self.is_calibrating:
                    # Subtract dark frame (clip to prevent negative values)
                    # Handle both grayscale and color images
                    if len(image_np.shape) == 3 and len(self.hotspot_mask.shape) == 2:
                        # Color image with grayscale dark frame - subtract from each channel
                        image_np = image_np.astype(np.float32)
                        for i in range(image_np.shape[2]):
                            image_np[:, :, i] = np.clip(image_np[:, :, i] - self.hotspot_mask, 0, 255)
                        image_np = image_np.astype(np.uint8)
                    elif image_np.shape == self.hotspot_mask.shape:
                        # Same shape - direct subtraction
                        image_np = np.clip(image_np.astype(np.float32) - self.hotspot_mask, 0, 255).astype(np.uint8)
                    else:
                        print(f"Warning: Dark frame shape {self.hotspot_mask.shape} doesn't match image shape {image_np.shape}. Skipping subtraction.")
                
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
            # Don't try to display image_np if it failed - it may be None

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
        
        # Update pixel info display if mouse is hovering
        self.imgplot.update_pixel_info()


    def display_image(self, image_np):
        """
        Convert the NumPy image (which might be grayscale or color) to a QImage
        and display it in the QLabel.
        """
        # Safety check: make sure we have a valid image
        if image_np is None:
            print("Warning: Cannot display None image")
            return
        
        if not isinstance(image_np, np.ndarray) or image_np.size == 0:
            print("Warning: Invalid image data")
            return
        
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
        
        # Update pixel info display if mouse is hovering
        self.imgplot.update_pixel_info()

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
        # Properly deinitialize and release the camera in correct order.
        # Order matters: camera -> camList -> system
        try:
            # Step 1: Stop streaming and deinitialize camera
            if hasattr(self, 'cam') and self.cam is not None:
                try:
                    if self.cam.IsStreaming():
                        self.cam.EndAcquisition()
                    self.cam.DeInit()
                except Exception as e:
                    print(f"Error deinitializing camera: {e}")
                # Delete the camera reference
                del self.cam
                self.cam = None
            
            # Step 2: Clear the camera list (releases camera references)
            if hasattr(self, 'camList') and self.camList is not None:
                try:
                    self.camList.Clear()
                    # Small delay to ensure references are released
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Error clearing camera list: {e}")
                # Delete the camera list reference
                del self.camList
                self.camList = None
            
            # Step 3: Release the system instance (must be last)
            if hasattr(self, 'system') and self.system is not None:
                try:
                    self.system.ReleaseInstance()
                except Exception as e:
                    print(f"Error releasing system: {e}")
                # Don't delete system - ReleaseInstance handles it
                
            print("Camera disconnected successfully")
        except Exception as e:
            print(f"Unexpected error disconnecting camera: {e}")

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
# coding=utf-8
# =============================================================================
# Copyright (c) 2025 FLIR Integrated Imaging Solutions, Inc. All Rights Reserved.
#
# This software is the confidential and proprietary information of FLIR
# Integrated Imaging Solutions, Inc. ("Confidential Information"). You
# shall not disclose such Confidential Information and shall use it only in
# accordance with the terms of the license agreement you entered into
# with FLIR Integrated Imaging Solutions, Inc. (FLIR).
#
# FLIR MAKES NO REPRESENTATIONS OR WARRANTIES ABOUT THE SUITABILITY OF THE
# SOFTWARE, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE, OR NON-INFRINGEMENT. FLIR SHALL NOT BE LIABLE FOR ANY DAMAGES
# SUFFERED BY LICENSEE AS A RESULT OF USING, MODIFYING OR DISTRIBUTING
# THIS SOFTWARE OR ITS DERIVATIVES.
# =============================================================================
#
# LiveView_PyQt.py shows how to create a PyQt interface to display a live view
# output of a FLIR camera using the Spinnaker SDK and PySpin.
#
# This example demonstrates:
# - PyQt GUI for camera live view
# - Threaded image acquisition to avoid blocking UI
# - Real-time image display using QLabel
# - Camera controls (start/stop acquisition)
# - Proper resource cleanup
#
# NOTE: PyQt5 or PyQt6 must be installed. Install with: pip install PyQt5
#
# Please leave us feedback at: https://www.surveymonkey.com/r/TDYMVAPI
# More source code examples at: https://github.com/Teledyne-MV/Spinnaker-Examples
# Need help? Check out our forum at: https://teledynevisionsolutions.zendesk.com/hc/en-us/community/topics

import sys
import platform
import numpy as np
import PySpin
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QMessageBox, QComboBox, 
                             QCheckBox, QGroupBox, QSlider, QSpinBox, QDoubleSpinBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QMutex
from PyQt5.QtGui import QImage, QPixmap


class StreamMode:
    """
    'Enum' for choosing stream mode
    """
    STREAM_MODE_TELEDYNE_GIGE_VISION = 0  # Teledyne Gige Vision stream mode is the default stream mode for spinview which is supported on Windows
    STREAM_MODE_PGRLWF = 1  # Light Weight Filter driver is our legacy driver which is supported on Windows
    STREAM_MODE_SOCKET = 2  # Socket is supported for MacOS and Linux, and uses native OS network sockets instead of a filter driver


# Determine stream mode based on current OS    
system = platform.system() 
if system == "Windows":
    CHOSEN_STREAMMODE = StreamMode.STREAM_MODE_TELEDYNE_GIGE_VISION
elif system == "Linux" or system == "Darwin":
    CHOSEN_STREAMMODE = StreamMode.STREAM_MODE_SOCKET
else:
    CHOSEN_STREAMMODE = StreamMode.STREAM_MODE_SOCKET


class CameraAcquisitionThread(QThread):
    """
    Worker thread for camera acquisition to avoid blocking the UI.
    """
    image_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)
    acquisition_started = pyqtSignal()
    acquisition_stopped = pyqtSignal()
    balance_range_available = pyqtSignal(float, float)  # min, max

    def __init__(self, cam):
        super().__init__()
        self.cam = cam
        self.is_running = False
        self.processor = None
        self.nodemap = None
        self.color_mode = True  # True for color, False for mono
        self.mode_mutex = QMutex()  # Mutex to protect color_mode access
        self.balance_mutex = QMutex()  # Mutex to protect balance values
        self.balance_ratios = {'Red': 1.0, 'Green': 1.0, 'Blue': 1.0}  # Default balance ratios
        self.balance_nodes_available = False
        self.balance_min = 0.0
        self.balance_max = 10.0
        self.balance_channel_names = {}  # Maps our names ('Red', 'Green', 'Blue') to camera's actual names

    def set_stream_mode(self):
        """
        Set the stream mode based on OS.
        """
        streamMode = "Socket"
        
        if CHOSEN_STREAMMODE == StreamMode.STREAM_MODE_TELEDYNE_GIGE_VISION:
            streamMode = "TeledyneGigeVision"
        elif CHOSEN_STREAMMODE == StreamMode.STREAM_MODE_PGRLWF:
            streamMode = "LWF"
        elif CHOSEN_STREAMMODE == StreamMode.STREAM_MODE_SOCKET:
            streamMode = "Socket"

        result = True
        nodemap_tlstream = self.cam.GetTLStreamNodeMap()
        node_stream_mode = PySpin.CEnumerationPtr(nodemap_tlstream.GetNode('StreamMode'))

        if not PySpin.IsReadable(node_stream_mode) or not PySpin.IsWritable(node_stream_mode):
            return True

        node_stream_mode_custom = PySpin.CEnumEntryPtr(node_stream_mode.GetEntryByName(streamMode))

        if not PySpin.IsReadable(node_stream_mode_custom):
            return False

        stream_mode_custom = node_stream_mode_custom.GetValue()
        node_stream_mode.SetIntValue(stream_mode_custom)
        return result

    def start_acquisition(self):
        """
        Initialize camera and start acquisition.
        """
        try:
            # Initialize camera
            self.cam.Init()
            
            # Get nodemap
            self.nodemap = self.cam.GetNodeMap()
            
            # Set stream mode
            if not self.set_stream_mode():
                self.error_occurred.emit("Failed to set stream mode")
                return False

            # Set buffer handling mode to NewestOnly for live view
            sNodemap = self.cam.GetTLStreamNodeMap()
            node_bufferhandling_mode = PySpin.CEnumerationPtr(sNodemap.GetNode('StreamBufferHandlingMode'))
            if PySpin.IsReadable(node_bufferhandling_mode) and PySpin.IsWritable(node_bufferhandling_mode):
                node_newestonly = node_bufferhandling_mode.GetEntryByName('NewestOnly')
                if PySpin.IsReadable(node_newestonly):
                    node_newestonly_mode = node_newestonly.GetValue()
                    node_bufferhandling_mode.SetIntValue(node_newestonly_mode)

            # Set acquisition mode to continuous
            node_acquisition_mode = PySpin.CEnumerationPtr(self.nodemap.GetNode('AcquisitionMode'))
            if not PySpin.IsReadable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
                self.error_occurred.emit("Unable to set acquisition mode to continuous")
                return False

            node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
            if not PySpin.IsReadable(node_acquisition_mode_continuous):
                self.error_occurred.emit("Unable to set acquisition mode to continuous")
                return False

            acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()
            node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

            # Create image processor
            self.processor = PySpin.ImageProcessor()
            self.processor.SetColorProcessing(PySpin.SPINNAKER_COLOR_PROCESSING_ALGORITHM_HQ_LINEAR)

            # Initialize color balance nodes (returns min/max if available)
            balance_range = self.init_color_balance_nodes()
            
            # Emit signal with balance range info for UI update
            if balance_range:
                min_val, max_val = balance_range
                self.balance_range_available.emit(min_val, max_val)

            # Begin acquisition
            self.cam.BeginAcquisition()
            self.is_running = True
            self.acquisition_started.emit()
            return True

        except PySpin.SpinnakerException as ex:
            self.error_occurred.emit(f"Error starting acquisition: {ex}")
            return False

    def set_color_mode(self, color_mode):
        """
        Set color/mono mode.
        :param color_mode: True for color, False for mono
        """
        self.mode_mutex.lock()
        self.color_mode = color_mode
        self.mode_mutex.unlock()

    def get_color_mode(self):
        """
        Get current color/mono mode.
        :return: True for color, False for mono
        """
        self.mode_mutex.lock()
        mode = self.color_mode
        self.mode_mutex.unlock()
        return mode

    def init_color_balance_nodes(self):
        """
        Initialize color balance nodes and disable auto white balance.
        Returns tuple (min_value, max_value) if nodes are available, None otherwise.
        """
        try:
            # Check if BalanceWhiteAuto node exists
            node_balance_white_auto = PySpin.CEnumerationPtr(self.nodemap.GetNode('BalanceWhiteAuto'))
            if PySpin.IsReadable(node_balance_white_auto) and PySpin.IsWritable(node_balance_white_auto):
                # Disable automatic white balance
                node_balance_white_auto_off = node_balance_white_auto.GetEntryByName('Off')
                if PySpin.IsReadable(node_balance_white_auto_off):
                    node_balance_white_auto.SetIntValue(node_balance_white_auto_off.GetValue())
                
                # Check if BalanceRatioSelector and BalanceRatio exist
                node_balance_ratio_selector = PySpin.CEnumerationPtr(self.nodemap.GetNode('BalanceRatioSelector'))
                node_balance_ratio = PySpin.CFloatPtr(self.nodemap.GetNode('BalanceRatio'))
                
                if (PySpin.IsReadable(node_balance_ratio_selector) and 
                    PySpin.IsWritable(node_balance_ratio_selector) and
                    PySpin.IsReadable(node_balance_ratio) and 
                    PySpin.IsWritable(node_balance_ratio)):
                    self.balance_nodes_available = True
                    
                    # Store min/max values
                    self.balance_min = node_balance_ratio.GetMin()
                    self.balance_max = node_balance_ratio.GetMax()
                    
                    # Discover available channel names by getting all entries
                    self.balance_channel_names = {}  # Map our names to camera names
                    entries = node_balance_ratio_selector.GetEntries()
                    available_names = []
                    green_candidates = []  # Collect all green variants
                    
                    for entry_node in entries:
                        # Cast to CEnumEntryPtr to access entry-specific methods
                        entry = PySpin.CEnumEntryPtr(entry_node)
                        if PySpin.IsReadable(entry):
                            entry_name = entry.GetSymbolic()
                            available_names.append(entry_name)
                            # Map common variations to our standard names
                            entry_name_lower = entry_name.lower()
                            if 'red' in entry_name_lower or entry_name == 'Red':
                                self.balance_channel_names['Red'] = entry_name
                            elif 'blue' in entry_name_lower or entry_name == 'Blue':
                                self.balance_channel_names['Blue'] = entry_name
                            elif 'green' in entry_name_lower:
                                green_candidates.append(entry_name)
                    
                    # Handle green channels - prefer exact 'Green', then Green1, then others
                    if green_candidates:
                        if 'Green' in green_candidates:
                            self.balance_channel_names['Green'] = 'Green'
                        elif 'Green1' in green_candidates:
                            self.balance_channel_names['Green'] = 'Green1'
                        elif green_candidates:
                            # Use the first green candidate found
                            self.balance_channel_names['Green'] = green_candidates[0]
                    
                    # Get initial balance ratios using discovered channel names
                    for our_name, camera_name in self.balance_channel_names.items():
                        node_entry = node_balance_ratio_selector.GetEntryByName(camera_name)
                        if PySpin.IsReadable(node_entry):
                            node_balance_ratio_selector.SetIntValue(node_entry.GetValue())
                            # Verify selector was set correctly
                            if node_balance_ratio_selector.GetIntValue() == node_entry.GetValue():
                                if PySpin.IsReadable(node_balance_ratio):
                                    self.balance_ratios[our_name] = node_balance_ratio.GetValue()
                    
                    return (self.balance_min, self.balance_max)
        except PySpin.SpinnakerException as ex:
            self.balance_nodes_available = False
            return None
        
        self.balance_nodes_available = False
        return None

    def set_balance_ratio(self, color, value):
        """
        Set balance ratio for a specific color channel.
        :param color: 'Red', 'Green', or 'Blue'
        :param value: Balance ratio value
        """
        if not self.balance_nodes_available or not self.nodemap:
            self.error_occurred.emit(f"Balance nodes not available for {color}")
            return False
            
        try:
            self.balance_mutex.lock()
            
            # Get the actual camera channel name for this color
            if color not in self.balance_channel_names:
                self.balance_mutex.unlock()
                available = ', '.join(self.balance_channel_names.keys())
                self.error_occurred.emit(f"Channel '{color}' not found. Available: {available}")
                return False
            
            camera_channel_name = self.balance_channel_names[color]
            
            node_balance_ratio_selector = PySpin.CEnumerationPtr(self.nodemap.GetNode('BalanceRatioSelector'))
            node_balance_ratio = PySpin.CFloatPtr(self.nodemap.GetNode('BalanceRatio'))
            
            if not (PySpin.IsReadable(node_balance_ratio_selector) and 
                    PySpin.IsWritable(node_balance_ratio_selector) and
                    PySpin.IsReadable(node_balance_ratio) and 
                    PySpin.IsWritable(node_balance_ratio)):
                self.balance_mutex.unlock()
                self.error_occurred.emit(f"Balance nodes not readable/writable for {color}")
                return False
                
            # Select the color channel using the camera's actual name
            node_entry = node_balance_ratio_selector.GetEntryByName(camera_channel_name)
            if not PySpin.IsReadable(node_entry):
                self.balance_mutex.unlock()
                self.error_occurred.emit(f"Entry '{camera_channel_name}' not readable for {color}")
                return False
            
            entry_value = node_entry.GetValue()
            
            # Set the selector
            node_balance_ratio_selector.SetIntValue(entry_value)
            
            # Verify the selector was set correctly
            actual_selector_value = node_balance_ratio_selector.GetIntValue()
            if actual_selector_value != entry_value:
                self.balance_mutex.unlock()
                current_entry = node_balance_ratio_selector.GetCurrentEntry()
                current_name = current_entry.GetSymbolic() if PySpin.IsReadable(current_entry) else "unknown"
                self.error_occurred.emit(f"Selector not set correctly for {color}. Expected {camera_channel_name}, got {current_name}")
                return False
            
            # Set the balance ratio value
            node_balance_ratio.SetValue(value)
            
            # Verify the value was set (read it back)
            actual_value = node_balance_ratio.GetValue()
            if abs(actual_value - value) > 0.01:  # More lenient tolerance for verification
                # Try setting again
                node_balance_ratio.SetValue(value)
                actual_value = node_balance_ratio.GetValue()
            
            self.balance_ratios[color] = actual_value
            self.balance_mutex.unlock()
            
            # If the value is significantly different, report it but still return success
            if abs(actual_value - value) > 0.01:
                self.error_occurred.emit(f"{color} balance set to {actual_value:.3f} (requested {value:.3f})")
            
            return True
            
        except PySpin.SpinnakerException as ex:
            self.balance_mutex.unlock()
            # Emit error for debugging
            self.error_occurred.emit(f"Error setting {color} balance ({camera_channel_name if 'camera_channel_name' in locals() else 'unknown'}): {ex}")
            return False
        except Exception as ex:
            self.balance_mutex.unlock()
            self.error_occurred.emit(f"Unexpected error setting {color} balance: {ex}")
            return False

    def get_balance_ratio(self, color):
        """
        Get current balance ratio for a specific color channel.
        :param color: 'Red', 'Green', or 'Blue'
        :return: Balance ratio value
        """
        self.balance_mutex.lock()
        value = self.balance_ratios.get(color, 1.0)
        self.balance_mutex.unlock()
        return value

    def stop_acquisition(self):
        """
        Stop acquisition and cleanup.
        """
        self.is_running = False
        try:
            if self.cam.IsStreaming():
                self.cam.EndAcquisition()
            self.cam.DeInit()
            self.acquisition_stopped.emit()
        except PySpin.SpinnakerException as ex:
            self.error_occurred.emit(f"Error stopping acquisition: {ex}")

    def run(self):
        """
        Main acquisition loop.
        """
        if not self.start_acquisition():
            return

        while self.is_running:
            try:
                # Get next image with timeout
                image_result = self.cam.GetNextImage(1000)

                if image_result.IsIncomplete():
                    image_result.Release()
                    continue

                # Get current mode (thread-safe)
                color_mode = self.get_color_mode()
                
                # Convert image based on selected mode
                if color_mode:
                    # Convert to RGB8 for color display
                    try:
                        # Try RGB8 first (if available)
                        if hasattr(PySpin, 'PixelFormat_RGB8'):
                            image_converted = self.processor.Convert(image_result, PySpin.PixelFormat_RGB8)
                            image_data = image_converted.GetNDArray()
                            image_converted.Release()
                        elif hasattr(PySpin, 'PixelFormat_BGR8'):
                            # Fallback to BGR8
                            image_converted = self.processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                            image_data = image_converted.GetNDArray()
                            image_converted.Release()
                        else:
                            # Use original format if no color format available
                            image_data = image_result.GetNDArray()
                    except (PySpin.SpinnakerException, AttributeError):
                        # Fallback to original image format if conversion fails
                        image_data = image_result.GetNDArray()
                else:
                    # Convert to Mono8 for grayscale display
                    try:
                        image_converted = self.processor.Convert(image_result, PySpin.PixelFormat_Mono8)
                        image_data = image_converted.GetNDArray()
                        image_converted.Release()
                    except PySpin.SpinnakerException:
                        # Fallback to original image format if conversion fails
                        image_data = image_result.GetNDArray()

                # Emit signal with image data
                self.image_ready.emit(image_data)

                # Release image
                image_result.Release()

            except PySpin.SpinnakerException as ex:
                if self.is_running:  # Only emit error if we're supposed to be running
                    self.error_occurred.emit(f"Error acquiring image: {ex}")
                break

        # Cleanup
        self.stop_acquisition()


class LiveViewWindow(QMainWindow):
    """
    Main window for the live view application.
    """
    def __init__(self):
        super().__init__()
        self.system = None
        self.cam_list = None
        self.cam = None
        self.acquisition_thread = None
        self.init_ui()
        self.init_camera_system()

    def init_ui(self):
        """
        Initialize the user interface.
        """
        self.setWindowTitle("FLIR Camera Live View")
        self.setGeometry(100, 100, 1200, 800)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Control panel
        control_layout = QHBoxLayout()
        
        # Camera selection
        camera_label = QLabel("Camera:")
        self.camera_combo = QComboBox()
        self.refresh_cameras_button = QPushButton("Refresh Cameras")
        self.refresh_cameras_button.clicked.connect(self.refresh_cameras)
        
        control_layout.addWidget(camera_label)
        control_layout.addWidget(self.camera_combo)
        control_layout.addWidget(self.refresh_cameras_button)
        control_layout.addStretch()

        # Color/Mono toggle
        self.color_mode_checkbox = QCheckBox("Color Mode")
        self.color_mode_checkbox.setChecked(True)  # Default to color
        self.color_mode_checkbox.setEnabled(False)  # Disabled until acquisition starts
        self.color_mode_checkbox.stateChanged.connect(self.on_color_mode_changed)
        
        control_layout.addWidget(self.color_mode_checkbox)
        control_layout.addStretch()

        # Color Balance Group
        balance_group = QGroupBox("Color Balance")
        balance_layout = QHBoxLayout()
        
        # Red balance
        red_label = QLabel("R:")
        self.red_balance_spin = QDoubleSpinBox()
        self.red_balance_spin.setRange(0.0, 10.0)  # Will be updated from camera
        self.red_balance_spin.setSingleStep(0.01)
        self.red_balance_spin.setValue(1.0)
        self.red_balance_spin.setDecimals(2)
        self.red_balance_spin.setEnabled(False)
        self.red_balance_spin.valueChanged.connect(lambda v: self.on_balance_changed('Red', v))
        
        # Green balance
        green_label = QLabel("G:")
        self.green_balance_spin = QDoubleSpinBox()
        self.green_balance_spin.setRange(0.0, 10.0)  # Will be updated from camera
        self.green_balance_spin.setSingleStep(0.01)
        self.green_balance_spin.setValue(1.0)
        self.green_balance_spin.setDecimals(2)
        self.green_balance_spin.setEnabled(False)
        self.green_balance_spin.valueChanged.connect(lambda v: self.on_balance_changed('Green', v))
        
        # Blue balance
        blue_label = QLabel("B:")
        self.blue_balance_spin = QDoubleSpinBox()
        self.blue_balance_spin.setRange(0.0, 10.0)  # Will be updated from camera
        self.blue_balance_spin.setSingleStep(0.01)
        self.blue_balance_spin.setValue(1.0)
        self.blue_balance_spin.setDecimals(2)
        self.blue_balance_spin.setEnabled(False)
        self.blue_balance_spin.valueChanged.connect(lambda v: self.on_balance_changed('Blue', v))
        
        balance_layout.addWidget(red_label)
        balance_layout.addWidget(self.red_balance_spin)
        balance_layout.addWidget(green_label)
        balance_layout.addWidget(self.green_balance_spin)
        balance_layout.addWidget(blue_label)
        balance_layout.addWidget(self.blue_balance_spin)
        
        balance_group.setLayout(balance_layout)
        control_layout.addWidget(balance_group)
        control_layout.addStretch()

        # Start/Stop buttons
        self.start_button = QPushButton("Start Acquisition")
        self.start_button.clicked.connect(self.start_acquisition)
        self.start_button.setEnabled(False)
        
        self.stop_button = QPushButton("Stop Acquisition")
        self.stop_button.clicked.connect(self.stop_acquisition)
        self.stop_button.setEnabled(False)

        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)

        main_layout.addLayout(control_layout)

        # Image display
        self.image_label = QLabel()
        self.image_label.setMinimumSize(800, 600)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText("No image")
        self.image_label.setStyleSheet("border: 1px solid black; background-color: #2b2b2b; color: white;")
        
        main_layout.addWidget(self.image_label)

        # Status bar
        self.statusBar().showMessage("Ready")

    def init_camera_system(self):
        """
        Initialize the Spinnaker system and detect cameras.
        """
        try:
            self.system = PySpin.System.GetInstance()
            version = self.system.GetLibraryVersion()
            self.statusBar().showMessage(
                f"Spinnaker version: {version.major}.{version.minor}.{version.type}.{version.build}"
            )
            self.refresh_cameras()
        except PySpin.SpinnakerException as ex:
            QMessageBox.critical(self, "Error", f"Failed to initialize Spinnaker system: {ex}")

    def refresh_cameras(self):
        """
        Refresh the list of available cameras.
        """
        try:
            # Clear existing camera list
            if self.cam_list:
                self.cam_list.Clear()
            
            # Get camera list
            self.cam_list = self.system.GetCameras()
            num_cameras = self.cam_list.GetSize()

            # Update combo box
            self.camera_combo.clear()
            if num_cameras == 0:
                self.camera_combo.addItem("No cameras detected")
                self.start_button.setEnabled(False)
            else:
                for i in range(num_cameras):
                    cam = self.cam_list[i]
                    nodemap_tldevice = cam.GetTLDeviceNodeMap()
                    node_device_serial_number = PySpin.CStringPtr(nodemap_tldevice.GetNode('DeviceSerialNumber'))
                    device_serial_number = "Unknown"
                    if PySpin.IsReadable(node_device_serial_number):
                        device_serial_number = node_device_serial_number.GetValue()
                    
                    node_device_model = PySpin.CStringPtr(nodemap_tldevice.GetNode('DeviceModelName'))
                    device_model = "Unknown"
                    if PySpin.IsReadable(node_device_model):
                        device_model = node_device_model.GetValue()
                    
                    self.camera_combo.addItem(f"Camera {i}: {device_model} ({device_serial_number})")
                self.start_button.setEnabled(True)

            self.statusBar().showMessage(f"Found {num_cameras} camera(s)")

        except PySpin.SpinnakerException as ex:
            QMessageBox.critical(self, "Error", f"Failed to refresh cameras: {ex}")

    def start_acquisition(self):
        """
        Start camera acquisition.
        """
        if self.camera_combo.currentIndex() == -1 or self.cam_list.GetSize() == 0:
            QMessageBox.warning(self, "Warning", "No camera selected")
            return

        try:
            # Get selected camera
            cam_index = self.camera_combo.currentIndex()
            self.cam = self.cam_list[cam_index]

            # Create and start acquisition thread
            self.acquisition_thread = CameraAcquisitionThread(self.cam)
            # Set initial color mode from checkbox
            self.acquisition_thread.set_color_mode(self.color_mode_checkbox.isChecked())
            
            self.acquisition_thread.image_ready.connect(self.display_image)
            self.acquisition_thread.error_occurred.connect(self.handle_error)
            self.acquisition_thread.acquisition_started.connect(self.on_acquisition_started)
            self.acquisition_thread.acquisition_stopped.connect(self.on_acquisition_stopped)
            self.acquisition_thread.balance_range_available.connect(self.on_balance_range_available)

            self.acquisition_thread.start()
            self.statusBar().showMessage("Starting acquisition...")

        except PySpin.SpinnakerException as ex:
            QMessageBox.critical(self, "Error", f"Failed to start acquisition: {ex}")

    def stop_acquisition(self):
        """
        Stop camera acquisition.
        """
        if self.acquisition_thread and self.acquisition_thread.isRunning():
            self.acquisition_thread.is_running = False
            self.statusBar().showMessage("Stopping acquisition...")

    def on_acquisition_started(self):
        """
        Handle acquisition started signal.
        """
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.camera_combo.setEnabled(False)
        self.refresh_cameras_button.setEnabled(False)
        self.color_mode_checkbox.setEnabled(True)
        
        # Enable color balance controls if available
        if self.acquisition_thread and self.acquisition_thread.balance_nodes_available:
            self.red_balance_spin.setEnabled(True)
            self.green_balance_spin.setEnabled(True)
            self.blue_balance_spin.setEnabled(True)
            
            # Update spinbox values with current camera values
            self.red_balance_spin.setValue(self.acquisition_thread.get_balance_ratio('Red'))
            self.green_balance_spin.setValue(self.acquisition_thread.get_balance_ratio('Green'))
            self.blue_balance_spin.setValue(self.acquisition_thread.get_balance_ratio('Blue'))
        else:
            self.red_balance_spin.setEnabled(False)
            self.green_balance_spin.setEnabled(False)
            self.blue_balance_spin.setEnabled(False)
        
        self.statusBar().showMessage("Acquisition running...")

    def on_color_mode_changed(self, state):
        """
        Handle color mode checkbox change.
        """
        if self.acquisition_thread and self.acquisition_thread.isRunning():
            color_mode = (state == Qt.Checked)
            self.acquisition_thread.set_color_mode(color_mode)
            mode_text = "Color" if color_mode else "Mono"
            self.statusBar().showMessage(f"Switched to {mode_text} mode")

    def on_acquisition_stopped(self):
        """
        Handle acquisition stopped signal.
        """
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.camera_combo.setEnabled(True)
        self.refresh_cameras_button.setEnabled(True)
        self.color_mode_checkbox.setEnabled(False)
        self.red_balance_spin.setEnabled(False)
        self.green_balance_spin.setEnabled(False)
        self.blue_balance_spin.setEnabled(False)
        self.statusBar().showMessage("Acquisition stopped")
        self.image_label.clear()
        self.image_label.setText("No image")

    def on_balance_range_available(self, min_val, max_val):
        """
        Handle balance range signal from acquisition thread.
        """
        # Update spinbox ranges with camera's actual min/max values
        self.red_balance_spin.setRange(min_val, max_val)
        self.green_balance_spin.setRange(min_val, max_val)
        self.blue_balance_spin.setRange(min_val, max_val)

    def on_balance_changed(self, color, value):
        """
        Handle color balance value change.
        """
        if self.acquisition_thread and self.acquisition_thread.isRunning():
            success = self.acquisition_thread.set_balance_ratio(color, value)
            if success:
                self.statusBar().showMessage(f"{color} balance set to {value:.2f}")
            else:
                self.statusBar().showMessage(f"Failed to set {color} balance")

    def display_image(self, image_data):
        """
        Display image from camera.
        """
        try:
            # Convert numpy array to QImage
            height, width = image_data.shape[:2]
            
            if len(image_data.shape) == 2:
                # Grayscale image
                q_image = QImage(image_data.data, width, height, width, QImage.Format_Grayscale8)
            elif len(image_data.shape) == 3:
                # Color image
                if image_data.shape[2] == 3:
                    q_image = QImage(image_data.data, width, height, width * 3, QImage.Format_RGB888).rgbSwapped()
                else:
                    q_image = QImage(image_data.data, width, height, width * 4, QImage.Format_RGBA8888)
            else:
                return

            # Convert to pixmap and scale to fit label
            pixmap = QPixmap.fromImage(q_image)
            scaled_pixmap = pixmap.scaled(
                self.image_label.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            self.image_label.setPixmap(scaled_pixmap)

        except Exception as ex:
            self.statusBar().showMessage(f"Error displaying image: {ex}")

    def handle_error(self, error_message):
        """
        Handle errors from acquisition thread.
        """
        self.statusBar().showMessage(f"Error: {error_message}")
        QMessageBox.warning(self, "Acquisition Error", error_message)
        self.stop_acquisition()

    def closeEvent(self, event):
        """
        Handle window close event - cleanup resources.
        """
        if self.acquisition_thread and self.acquisition_thread.isRunning():
            self.stop_acquisition()
            self.acquisition_thread.wait(3000)  # Wait up to 3 seconds

        # Cleanup camera
        if self.cam:
            try:
                if self.cam.IsInitialized():
                    self.cam.DeInit()
            except:
                pass
            del self.cam

        # Cleanup camera list
        if self.cam_list:
            try:
                self.cam_list.Clear()
            except:
                pass

        # Cleanup system
        if self.system:
            try:
                self.system.ReleaseInstance()
            except:
                pass

        event.accept()


def main():
    """
    Main entry point.
    """
    app = QApplication(sys.argv)
    
    window = LiveViewWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()


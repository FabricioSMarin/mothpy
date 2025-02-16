import sys
import cv2
import numpy as np
import os
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, QRect, QDateTime, QPoint
from PyQt5.QtGui import QImage, QPixmap
from pypylon import pylon


class FlirCameraWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("FLIR GigE Camera Control")
        self.camera = None
        self.stream_active = False
        self.image = None
        self.recording = False
        self.save_directory = os.getcwd()

        # Default zoom region boxes
        self.zoom_regions = [QRect(100, 100, 100, 100), QRect(300, 100, 100, 100)]
        self.resizing_region = None
        self.dragging = False
        self.drag_start_pos = QPoint()

        # Tracking data for the second zoom region
        self.region_center_positions_x = []
        self.region_center_positions_y = []

        # Create UI elements
        self.initUI()

        # Timer for updating frames
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

    def initUI(self):
        """Initialize the UI layout and elements."""
        layout = QVBoxLayout()

        # Main Camera View
        self.image_label = QLabel("No Camera Feed")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMouseTracking(True)
        self.image_label.mousePressEvent = self.image_mouse_press
        self.image_label.mouseMoveEvent = self.image_mouse_move
        self.image_label.mouseReleaseEvent = self.image_mouse_release
        layout.addWidget(self.image_label)

        # Zoomed Views with XY Position Labels
        self.zoom_info_labels = [QLabel("Region 1: (X, Y)"), QLabel("Region 2: (X, Y)")]
        zoom_info_layout = QHBoxLayout()
        for lbl in self.zoom_info_labels:
            lbl.setAlignment(Qt.AlignCenter)
            zoom_info_layout.addWidget(lbl)
        layout.addLayout(zoom_info_layout)

        self.brightest_feature_label = QLabel("Tracking Feature Displacement: (ΔX, ΔY)")
        self.brightest_feature_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.brightest_feature_label)

        zoom_layout = QHBoxLayout()
        self.zoom_labels = [QLabel("Zoom Region 1"), QLabel("Zoom Region 2")]
        for lbl in self.zoom_labels:
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedSize(150, 150)
            zoom_layout.addWidget(lbl)
        layout.addLayout(zoom_layout)

        # Start/Stop Buttons
        btn_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Camera")
        self.start_button.clicked.connect(self.start_camera)
        btn_layout.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop Camera")
        self.stop_button.clicked.connect(self.stop_camera)
        btn_layout.addWidget(self.stop_button)

        self.capture_button = QPushButton("Capture Image")
        self.capture_button.clicked.connect(self.capture_image)
        btn_layout.addWidget(self.capture_button)

        self.show_graph_button = QPushButton("Show Region Center Position Graph")
        self.show_graph_button.clicked.connect(self.show_region_center_graph)
        btn_layout.addWidget(self.show_graph_button)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def start_camera(self):
        """Initialize the FLIR GigE camera and start streaming."""
        if self.stream_active:
            return

        try:
            self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
            self.camera.Open()
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            self.stream_active = True
            self.timer.start(30)
        except Exception as e:
            print(f"Error initializing camera: {e}")

    def stop_camera(self):
        """Stop the camera stream and close the connection."""
        if self.camera:
            self.timer.stop()
            self.camera.StopGrabbing()
            self.camera.Close()
            self.stream_active = False
            self.image_label.setText("No Camera Feed")

    def update_frame(self):
        """Capture frames from the FLIR GigE camera and display them."""
        if self.camera and self.camera.IsGrabbing():
            grab_result = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)

            if grab_result.GrabSucceeded():
                img = grab_result.Array
                img = cv2.cvtColor(img, cv2.COLOR_BayerBG2RGB)
                self.image = img  # Store for zoomed regions
                self.display_image(img)

                # Track the brightest feature in second zoom region and reposition box
                self.track_and_reposition_zoom_region(img)

            grab_result.Release()

    def display_image(self, img):
        """Displays the main image with zoomed regions."""
        h, w, ch = img.shape

        # Draw zoom regions
        for rect in self.zoom_regions:
            cv2.rectangle(img, (rect.x(), rect.y()), (rect.x() + rect.width(), rect.y() + rect.height()), (0, 255, 0), 2)

        # Convert to QImage for display
        bytes_per_line = ch * w
        qt_img = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(qt_img))

    def track_and_reposition_zoom_region(self, img):
        """Find the brightest feature inside the second zoom region and reposition it."""
        zoom_rect = self.zoom_regions[1]  # Second zoom region
        zoom_img = img[zoom_rect.y():zoom_rect.y()+zoom_rect.height(), zoom_rect.x():zoom_rect.x()+zoom_rect.width()]

        # Convert to grayscale
        gray = cv2.cvtColor(zoom_img, cv2.COLOR_RGB2GRAY)

        # Find the brightest pixel
        _, maxVal, _, maxLoc = cv2.minMaxLoc(gray)
        feature_x, feature_y = maxLoc

        # Compute the new position of the zoom region to center the feature
        new_x = zoom_rect.x() + feature_x - (zoom_rect.width() // 2)
        new_y = zoom_rect.y() + feature_y - (zoom_rect.height() // 2)

        # Update zoom region position
        self.zoom_regions[1].moveTo(new_x, new_y)

        # Log center position over time
        self.region_center_positions_x.append(new_x + zoom_rect.width() // 2)
        self.region_center_positions_y.append(new_y + zoom_rect.height() // 2)

    def image_mouse_press(self, event):
        """Detects if a zoom region is clicked and initiates resizing."""
        for i, rect in enumerate(self.zoom_regions):
            if QRect(rect.right() - 10, rect.bottom() - 10, 10, 10).contains(event.pos()):
                self.resizing_region = i
                self.dragging = True
                self.drag_start_pos = event.pos()
                return

    def image_mouse_move(self, event):
        """Resizes the selected zoom region box."""
        if self.resizing_region is not None and self.dragging:
            dx = event.pos().x() - self.drag_start_pos.x()
            dy = event.pos().y() - self.drag_start_pos.y()
            self.zoom_regions[self.resizing_region].setWidth(max(20, self.zoom_regions[self.resizing_region].width() + dx))
            self.zoom_regions[self.resizing_region].setHeight(max(20, self.zoom_regions[self.resizing_region].height() + dy))
            self.drag_start_pos = event.pos()
            self.display_image(self.image)

    def image_mouse_release(self, event):
        """Stops resizing."""
        self.resizing_region = None
        self.dragging = False
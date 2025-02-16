import sys
import cv2
import numpy as np
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFileDialog
)
from PyQt5.QtCore import Qt, QTimer, QRect, QDateTime, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QColor, QPen
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

        zoom_layout = QHBoxLayout()
        self.zoom_labels = [QLabel("Zoom Region 1"), QLabel("Zoom Region 2")]
        for i, lbl in enumerate(self.zoom_labels):
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedSize(150, 150)
            lbl.mousePressEvent = lambda event, idx=i: self.zoom_click_event(event, idx)
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

            grab_result.Release()

    def display_image(self, img):
        """Displays the main image with crosshairs and zoomed regions."""
        h, w, ch = img.shape

        # Draw crosshairs
        cv2.line(img, (w//2, 0), (w//2, h), (0, 0, 255), 1)
        cv2.line(img, (0, h//2), (w, h//2), (0, 0, 255), 1)

        # Draw zoom regions
        for rect in self.zoom_regions:
            cv2.rectangle(img, (rect.x(), rect.y()), (rect.x() + rect.width(), rect.y() + rect.height()), (0, 255, 0), 2)

        # Convert to QImage for display
        bytes_per_line = ch * w
        qt_img = QImage(img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(qt_img))

        # Update Zoomed Regions and XY Labels
        for i, rect in enumerate(self.zoom_regions):
            zoom_img = img[rect.y():rect.y()+rect.height(), rect.x():rect.x()+rect.width()]
            zoom_img = cv2.resize(zoom_img, (150, 150))
            bytes_per_line = 3 * 150
            qt_zoom_img = QImage(zoom_img.data, 150, 150, bytes_per_line, QImage.Format_RGB888)
            self.zoom_labels[i].setPixmap(QPixmap.fromImage(qt_zoom_img))

            # Update Region Center Position
            center_x = rect.x() + rect.width() // 2
            center_y = rect.y() + rect.height() // 2
            self.zoom_info_labels[i].setText(f"Region {i+1}: ({center_x}, {center_y})")

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

    def capture_image(self):
        """Capture a single image and save it."""
        if self.image is not None:
            timestamp = QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
            filename = os.path.join(self.save_directory, f"flir_capture_{timestamp}.png")
            cv2.imwrite(filename, cv2.cvtColor(self.image, cv2.COLOR_RGB2BGR))
            print(f"Image saved: {filename}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FlirCameraWidget()
    window.show()
    sys.exit(app.exec_())
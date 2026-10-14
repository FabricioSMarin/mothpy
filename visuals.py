import sys
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
import pyqtgraph as pg
from PyQt5 import QtCore

class CustomViewBox(pg.ViewBox):
    def __init__(self):
        pg.ViewBox.__init__(self)
        self.setMouseMode(self.RectMode)

    def mouseClickEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            pass

    def mouseDragEvent(self, ev):
        if ev.button() == QtCore.Qt.RightButton:
            ev.ignore()
        else:
            pg.ViewBox.mouseDragEvent(self, ev)
            self.autoRange()

class ImagePlotWidget(QWidget):
    def __init__(self, title="Camera 1", show_rois=True):
        super().__init__()
        self.title = title
        self.show_rois = show_rois
        self.last_mouse_pos = None  # Track last mouse position for live updates
        self.ROI1 = None
        self.ROI2 = None
        self.initUI()

    def set_title(self, title):
        self.title = title
        if self.last_mouse_pos is None:
            self.coord_label.setText(f"{self.title}: hover over image")

    def initUI(self):
        # Generate random RGB image
        self.image_data = np.random.rand(100, 100, 3)  # RGB image
        
        # Create main layout
        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Add coordinate display label at the top
        self.coord_label = QLabel(f"{self.title}: hover over image")
        self.coord_label.setStyleSheet("background-color: #2b2b2b; color: #00ff00; padding: 5px; font-family: monospace;")
        self.layout.addWidget(self.coord_label)
        
        # Create GraphicsLayoutWidget
        self.graphics_layout = pg.GraphicsLayoutWidget()
        self.graphics_layout.setSizePolicy(pg.QtWidgets.QSizePolicy.Expanding, pg.QtWidgets.QSizePolicy.Expanding)
        
        # Custom ViewBox
        custom_vb = CustomViewBox()
        
        # Add image plot with CustomViewBox
        self.image_plot = self.graphics_layout.addPlot(viewBox=custom_vb, enableMouse=False)
        self.image_item = pg.ImageItem(self.image_data)
        self.image_plot.addItem(self.image_item)
        self.image_plot.vb = custom_vb

        if self.show_rois:
            roi_pen = pg.mkPen((204, 204, 0), width=4)  # Dark yellow with thickness 4
            self.ROI1 = pg.ROI([10, 10], [10, 10], scaleSnap=True, aspectLocked=True, pen=roi_pen)
            self.ROI1.addScaleHandle(pos=(1, 1), center=(0,0))
            self.ROI1.addScaleHandle(pos=(0,0), center=(1,1))
            self.ROI1.addScaleHandle(pos=(0,1), center=(1,0))
            self.ROI1.addScaleHandle(pos=(1,0), center=(0,1))

            roi2_pen = pg.mkPen((0, 204, 204), width=4)
            self.ROI2 = pg.ROI([50, 50], [10, 10], scaleSnap=True, aspectLocked=True, pen=roi2_pen)
            self.ROI2.addScaleHandle(pos=(1, 1), center=(0,0))
            self.ROI2.addScaleHandle(pos=(0,0), center=(1,1))
            self.ROI2.addScaleHandle(pos=(0,1), center=(1,0))
            self.ROI2.addScaleHandle(pos=(1,0), center=(0,1))

            self.star_crosshair = pg.ScatterPlotItem(
                size=20,
                pen=pg.mkPen('r', width=2),
                symbol='+',
                brush=None
            )
            self.star_crosshair.setVisible(False)

            self.star2_crosshair = pg.ScatterPlotItem(
                size=20,
                pen=pg.mkPen((0, 220, 220), width=2),
                symbol='+',
                brush=None
            )
            self.star2_crosshair.setVisible(False)

            self.image_plot.addItem(self.ROI1)
            self.image_plot.addItem(self.ROI2)
            self.image_plot.addItem(self.star_crosshair)
            self.image_plot.addItem(self.star2_crosshair)

        # Remove axis labels
        self.image_plot.hideAxis('bottom')
        self.image_plot.hideAxis('left')
        
        # Connect mouse move event to show coordinates and pixel values
        self.image_plot.scene().sigMouseMoved.connect(self.on_mouse_moved)

        self.layout.addWidget(self.graphics_layout)
        self.setLayout(self.layout)
        self.setWindowTitle("PyQtGraph RGB Image Widget with Projections")

        return self.layout
    
    def update_roi_images(self):
        """Kept for callers; cropped ROI preview panes were removed."""
        return
    
    def update_star_crosshair(self, x, y, visible=True):
        """Update the position of the red crosshair showing the tracked star
        
        Args:
            x: X coordinate in image space
            y: Y coordinate in image space
            visible: Whether to show the crosshair
        """
        if getattr(self, "star_crosshair", None) is None:
            return
        if visible:
            self.star_crosshair.setData([x], [y])
            self.star_crosshair.setVisible(True)
        else:
            self.star_crosshair.setVisible(False)

    def update_star2_crosshair(self, x, y, visible=True):
        """Update the cyan crosshair on the second (ROI2) star."""
        if getattr(self, "star2_crosshair", None) is None:
            return
        if visible:
            self.star2_crosshair.setData([x], [y])
            self.star2_crosshair.setVisible(True)
        else:
            self.star2_crosshair.setVisible(False)
    
    def on_mouse_moved(self, pos):
        """Handle mouse movement over the image to show coordinates and pixel values"""
        # Store the mouse position for updates when new images arrive
        self.last_mouse_pos = pos
        self.update_pixel_info(pos)
    
    def update_pixel_info(self, pos=None):
        """Update the pixel information display at the given position"""
        if pos is None:
            pos = self.last_mouse_pos
        
        if pos is None:
            return
        
        try:
            # Check if mouse is over the image plot
            if self.image_plot.sceneBoundingRect().contains(pos):
                # Map scene position to view coordinates
                mouse_point = self.image_plot.vb.mapSceneToView(pos)
                x, y = mouse_point.x(), mouse_point.y()
                
                # Check if coordinates are within image bounds
                if self.image_data is not None:
                    # Image has been rotated 90° clockwise, so dimensions are swapped
                    # After rotation: shape[0] is the X dimension (width), shape[1] is the Y dimension (height)
                    width, height = self.image_data.shape[0], self.image_data.shape[1]
                    
                    # Round to integer pixel coordinates
                    ix, iy = int(round(x)), int(round(y))
                    
                    # Check bounds with tolerance for edge pixels
                    if 0 <= ix < width and 0 <= iy < height:
                        # Get pixel value(s)
                        # After rotation, indexing is [x, y] not [y, x]
                        if len(self.image_data.shape) == 3:  # Color image
                            pixel = self.image_data[ix, iy]
                            if self.image_data.shape[2] == 3:  # RGB/BGR
                                pixel_str = f"RGB=({pixel[0]}, {pixel[1]}, {pixel[2]})"
                            else:
                                pixel_str = f"Value={pixel}"
                        else:  # Grayscale
                            pixel = self.image_data[ix, iy]
                            pixel_str = f"Value={pixel:.0f}" if isinstance(pixel, (np.floating, float)) else f"Value={pixel}"
                        
                        # Update label with both float and integer coords
                        self.coord_label.setText(f"X={ix}, Y={iy}  |  {pixel_str}")
                    else:
                        # Show the coordinates even if outside bounds
                        self.coord_label.setText(f"X={ix}, Y={iy}  |  Outside image bounds (size: {width}x{height})")
            else:
                self.coord_label.setText(f"{self.title}: hover over image")
        except Exception as e:
            # Silently handle any errors to avoid crashing the UI
            pass
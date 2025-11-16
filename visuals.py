import sys
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
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
    def __init__(self):
        super().__init__()
        self.last_mouse_pos = None  # Track last mouse position for live updates
        self.initUI()

    def initUI(self):
        # Generate random RGB image
        self.image_data = np.random.rand(100, 100, 3)  # RGB image
        stack = np.random.rand(10, 100, 100, 3)  # Example stack for normalization
        xrange, yrange = self.image_data.shape[1], self.image_data.shape[0]
        
        # Create main layout
        self.layout = QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Add coordinate display label at the top
        self.coord_label = QLabel("Hover over image to see coordinates and pixel value")
        self.coord_label.setStyleSheet("background-color: #2b2b2b; color: #00ff00; padding: 5px; font-family: monospace;")
        self.layout.addWidget(self.coord_label)
        
        top_layout = QHBoxLayout()
        top_layout.setSpacing(0)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addLayout(top_layout)
        
        # Create GraphicsLayoutWidget
        self.graphics_layout = pg.GraphicsLayoutWidget()
        self.graphics_layout.setSizePolicy(pg.QtWidgets.QSizePolicy.Expanding, pg.QtWidgets.QSizePolicy.Expanding)
        
        # Custom ViewBox
        custom_vb = CustomViewBox()
        
        # ROI properties
        roi_pen = pg.mkPen((204, 204, 0), width=4)  # Dark yellow with thickness 4
        
        # First ROI
        self.ROI1 = pg.ROI([10, 10], [10, 10], scaleSnap=True, aspectLocked=True, pen=roi_pen)
        self.ROI1.addScaleHandle(pos=(1, 1), center=(0,0))
        self.ROI1.addScaleHandle(pos=(0,0), center=(1,1))
        self.ROI1.addScaleHandle(pos=(0,1), center=(1,0))
        self.ROI1.addScaleHandle(pos=(1,0), center=(0,1))
        
        # Second ROI
        self.ROI2 = pg.ROI([50, 50], [10, 10], scaleSnap=True, aspectLocked=True, pen=roi_pen)
        self.ROI2.addScaleHandle(pos=(1, 1), center=(0,0))
        self.ROI2.addScaleHandle(pos=(0,0), center=(1,1))
        self.ROI2.addScaleHandle(pos=(0,1), center=(1,0))
        self.ROI2.addScaleHandle(pos=(1,0), center=(0,1))
        
        # Create red crosshair for tracked star
        self.star_crosshair = pg.ScatterPlotItem(
            size=20, 
            pen=pg.mkPen('r', width=2), 
            symbol='+',
            brush=None
        )
        self.star_crosshair.setVisible(False)  # Hidden by default
        
        # Add image plot with CustomViewBox
        self.image_plot = self.graphics_layout.addPlot(viewBox=custom_vb, enableMouse=False)
        self.image_item = pg.ImageItem(self.image_data)
        self.image_plot.addItem(self.image_item)
        self.image_plot.addItem(self.ROI1)
        self.image_plot.addItem(self.ROI2)
        self.image_plot.addItem(self.star_crosshair)  # Add crosshair overlay
        self.image_plot.vb = custom_vb

        # Remove axis labels
        self.image_plot.hideAxis('bottom')
        self.image_plot.hideAxis('left')
        
        # Connect mouse move event to show coordinates and pixel values
        self.image_plot.scene().sigMouseMoved.connect(self.on_mouse_moved)
        
        # Add Histogram and Colorbar tool
        self.histogram = pg.HistogramLUTItem()
        self.histogram.setImageItem(self.image_item)
        self.histogram.setFixedWidth(100)  # Set histogram width to 100
        
        # Set default colormap to greyclip for better star visibility
        self.histogram.gradient.loadPreset('greyclip')
        
        # Create a container widget for the histogram and set fixed size policy
        histogram_container = pg.GraphicsLayoutWidget()
        histogram_container.setFixedWidth(100)
        histogram_container.addItem(self.histogram)
        
        # Add widgets to layout with correct sizing
        top_layout.addWidget(self.graphics_layout, 1)
        top_layout.addWidget(histogram_container, 0)
        
        # Create bottom layout for extracted ROI images
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(0)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addLayout(bottom_layout)
        
        # Create ImageItems for extracted ROI contents without histogram tools
        self.roi1_image_view = pg.ImageView(view=pg.PlotItem())
        self.roi2_image_view = pg.ImageView(view=pg.PlotItem())
        
        # Remove histogram, ROI, and menu buttons from the ImageView widgets
        for roi_view in [self.roi1_image_view, self.roi2_image_view]:
            roi_view.ui.histogram.hide()
            roi_view.ui.roiBtn.hide()
            roi_view.ui.menuBtn.hide()
            roi_view.getView().hideAxis('bottom')
            roi_view.getView().hideAxis('left')
        
        bottom_layout.addWidget(self.roi1_image_view, 1)
        bottom_layout.addWidget(self.roi2_image_view, 1)
        
        self.setLayout(self.layout)
        self.setWindowTitle("PyQtGraph RGB Image Widget with Projections")
        self.setGeometry(100, 100, 600, 800)
        
        # Update ROI images when moved or resized
        self.ROI1.sigRegionChanged.connect(self.update_roi_images)
        self.ROI2.sigRegionChanged.connect(self.update_roi_images)
        self.update_roi_images()

        return self.layout
    
    def update_roi_images(self):
        roi1_bounds = self.ROI1.getArraySlice(self.image_data, self.image_item)[0]
        roi2_bounds = self.ROI2.getArraySlice(self.image_data, self.image_item)[0]
        
        if roi1_bounds is not None:
            roi1_data = self.image_data[roi1_bounds]
            # Flip the ROI image vertically
            self.roi1_image_view.setImage(np.fliplr(roi1_data))
        if roi2_bounds is not None:
            roi2_data = self.image_data[roi2_bounds]
            # Flip the ROI image vertically
            self.roi2_image_view.setImage(np.fliplr(roi2_data))
    
    def update_star_crosshair(self, x, y, visible=True):
        """Update the position of the red crosshair showing the tracked star
        
        Args:
            x: X coordinate in image space
            y: Y coordinate in image space
            visible: Whether to show the crosshair
        """
        if visible:
            self.star_crosshair.setData([x], [y])
            self.star_crosshair.setVisible(True)
        else:
            self.star_crosshair.setVisible(False)
    
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
                self.coord_label.setText("Hover over image to see coordinates and pixel value")
        except Exception as e:
            # Silently handle any errors to avoid crashing the UI
            pass
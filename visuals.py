import sys
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout
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
        
        # Add image plot with CustomViewBox
        self.image_plot = self.graphics_layout.addPlot(viewBox=custom_vb, enableMouse=False)
        self.image_item = pg.ImageItem(self.image_data)
        self.image_plot.addItem(self.image_item)
        self.image_plot.addItem(self.ROI1)
        self.image_plot.addItem(self.ROI2)
        self.image_plot.vb = custom_vb

        # Remove axis labels
        self.image_plot.hideAxis('bottom')
        self.image_plot.hideAxis('left')
        
        # Add Histogram and Colorbar tool
        self.histogram = pg.HistogramLUTItem()
        self.histogram.setImageItem(self.image_item)
        self.histogram.setFixedWidth(100)  # Set histogram width to 100
        
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
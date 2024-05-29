import sys
import PyQt5
from PyQt5.QtWidgets import QStyle, QLineEdit, QGridLayout, QPushButton, QComboBox, QGraphicsView, QGraphicsScene, QLabel, QSlider, QVBoxLayout, QHBoxLayout, QFrame, QApplication, QWidget, QMainWindow, QTextEdit
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal, QSize
from PyQt5 import Qt, QtCore
from PyQt5.QtCore import *
import pyqtgraph as pg
import matplotlib.pyplot as plt
# import matplotlib.image as Image
import numpy as np
import math
import imageio
from scipy import interpolate, ndimage
from skimage.transform import resize

#TODO: connect dpad to motor functions
#TODO: import and init gigE cmaera
#TODO: connect track button to motor functions 
#TODO: enable roi draging 
#TODO: [] to resize ROI 
#TODO: mirror roi ro zoom view
#TODO: import gigE.py
#TODO: import motors.py 
#TODO: add step_size_changed
#TODO: add sld_changed 
#TODO: import registration.py 
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        sys.stdout = Stream(newText=self.onUpdateText)

        self.setStyleSheet("QMainWindow { background-color: black; }")        
        self.setWindowTitle("Drag and Drop Files")
        self.setGeometry(100, 100, 730, 730)
        self.setMinimumSize(700,700)
        self.aspect_ratio = 1

        self.view = ImageView()
        self.view.roi.sigRegionChanged.connect(self.updateRoi)
        self.controls = Contorls()
        self.logbox = QTextEdit("")
        self.logbox.setMinimumWidth(600)
        self.logbox.setFixedHeight(150)
        self.logbox.setStyleSheet("background: rgb(30,30,30); color: rgb(30,70,30)")
        self.logbox.setReadOnly(True)

        hbox = QHBoxLayout()
        hbox.addWidget(self.view)
        hbox.addWidget(self.controls)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.logbox)

        self.frame = QFrame()
        self.frame.setLayout(vbox)
        self.setCentralWidget(self.frame)

        #temporary### 
        self.load_image()
        self.show()


    def load_image(self):
        file = "/Users/marinf/Downloads/DSC08280.JPG"
        img = imageio.v3.imread(file)
        self.view.image_view.setImage(img)

    def onUpdateText(self, text):
        cursor = self.logbox.textCursor()
        cursor.insertText(text)
        self.logbox.setTextCursor(cursor)
        self.logbox.ensureCursorVisible()

    def updateRoi(self, roi):
        try:
            self.arr1 = roi.getArrayRegion(self.view.image_view.image, img=self.view.image_view)
            self.controls.zoom_view.image_view.setImage(self.arr1)
        except: 
            pass

    def resizeEvent(self, event):
        current_size = self.size()
        new_width = current_size.width()
        new_height = int(new_width / self.aspect_ratio)

        if new_height > current_size.height():
            new_height = current_size.height()
            new_width = int(new_height * self.aspect_ratio)

        self.resize(new_width, new_height)

        super().resizeEvent(event)

class Contorls(QWidget):
    def __init__(self):
        super(Contorls, self).__init__()
        self.setFixedSize(200,530)
        self.initUI()
        
    def initUI(self):
        self.dpad = DPadWidget()
        self.zoom_view = zoomView()
        self.zoom_view.setAspectLocked(True)
        self.step_size = QLineEdit()
        self.step_size.setPlaceholderText("step_size")
        self.step_size.setFixedWidth(100)

        iconsize = 40
        self.focus_near = QPushButton("\U0001f337")
        # self.focus_near.setStyleSheet("background-color: rgb(10,10,10);")
        self.focus_near.setFixedSize(iconsize,iconsize)
        self.focus_far = QPushButton("\U000026f0")
        self.focus_far.setFixedSize(iconsize,iconsize)
        self.focus_sld = QSlider(Qt.Horizontal)
        focus_box = QHBoxLayout()
        focus_box.addWidget(self.focus_near)
        focus_box.addWidget(self.focus_sld)
        focus_box.addWidget(self.focus_far)

        self.exposure_less = QPushButton("\U0000231B")
        self.exposure_less.setFixedSize(iconsize,iconsize)
        self.exposure_more = QPushButton("\U000023F3")
        self.exposure_more.setFixedSize(iconsize,iconsize)
        self.exposure_sld = QSlider(Qt.Horizontal)
        fexposure_box = QHBoxLayout()
        fexposure_box.addWidget(self.exposure_less)
        fexposure_box.addWidget(self.exposure_sld)
        fexposure_box.addWidget(self.exposure_more)

        self.gain_less = QPushButton("\U0001F505")
        self.gain_less.setFixedSize(iconsize,iconsize)
        self.gain_more = QPushButton("\U0001F506")
        self.gain_more.setFixedSize(iconsize,iconsize)
        self.gain_sld = QSlider(Qt.Horizontal)
        gain_box = QHBoxLayout()
        gain_box.addWidget(self.gain_less)
        gain_box.addWidget(self.gain_sld)
        gain_box.addWidget(self.gain_more)

        layout = QVBoxLayout()
        layout.addWidget(self.dpad, alignment=QtCore.Qt.AlignTop)
        layout.addWidget(self.step_size, alignment=QtCore.Qt.AlignCenter)
        layout.addLayout(focus_box)
        layout.addLayout(fexposure_box)
        layout.addLayout(gain_box)
        layout.addWidget(self.zoom_view)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        pass

class DPadWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("D-pad Widget")
        # self.setGeometry(100, 100, 200, 200)
        self.setFixedSize(200,200)

        # Create the layout
        layout = QGridLayout()

        # Create the buttons with arrow icons
        iconsize = 32
        up_button = QPushButton()
        up_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowUp')))
        up_button.setIconSize(QSize(iconsize, iconsize))
        
        down_button = QPushButton()
        down_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowDown')))
        down_button.setIconSize(QSize(iconsize, iconsize))
        
        left_button = QPushButton()
        left_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowLeft')))
        left_button.setIconSize(QSize(iconsize, iconsize))
        
        right_button = QPushButton()
        right_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowRight')))
        right_button.setIconSize(QSize(iconsize, iconsize))
        
        center_button = QPushButton()
        center_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_DialogYesButton')))
        center_button.setIconSize(QSize(iconsize, iconsize))

        # Set fixed size for the buttons for a consistent look
        button_size = 50
        up_button.setFixedSize(button_size, button_size)
        down_button.setFixedSize(button_size, button_size)
        left_button.setFixedSize(button_size, button_size)
        right_button.setFixedSize(button_size, button_size)
        center_button.setFixedSize(button_size, button_size)

        # Add the buttons to the layout
        layout.addWidget(up_button, 0, 1)
        layout.addWidget(left_button, 1, 0)
        layout.addWidget(center_button, 1, 1)
        layout.addWidget(right_button, 1, 2)
        layout.addWidget(down_button, 2, 1)

        # Set spacing
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)

        # Set the layout for the main widget
        self.setLayout(layout)


class zoomView(pg.GraphicsLayoutWidget):
    def __init__(self):
        super(zoomView, self).__init__()
        self.setFixedSize(200,200)
        self.setAspectLocked(True)
        self.initUI()

    def initUI(self):
        pg.setConfigOptions(imageAxisOrder='row-major')
        self.setBackground("k")
        self.arr = None
        self.last_moving_pos = None
        self.image_view = pg.ImageItem()
        
        border_pen = pg.mkPen(color=(255, 0, 0), width=2)

        self.v2 = self.addViewBox(1,0)
        self.v2.addItem(self.image_view)
        self.v2.invertY(True)
        self.v2.setAspectLocked(True)
        self.v2.setMenuEnabled(False)
        self.v2.setMouseEnabled(x=False, y=False)
        self.v2.disableAutoRange()
        self.v2.setBorder(None)
        self.v2.setBorder(border_pen)

class ImageView(pg.GraphicsLayoutWidget):
    mouseMoveSig = pyqtSignal(int,int, name= 'mouseMoveSig')
    mousePressSig =pyqtSignal(int,int,int, name= 'mousePressSig')
    def __init__(self):
        super(ImageView, self).__init__()
        self.setMinimumSize(300,300)
        self.initUI()

    def initUI(self):
        pg.setConfigOptions(imageAxisOrder='row-major')
        self.setBackground("k")
        self.arr = None
        self.last_moving_pos = None
        self.zoom_sf = 1
        self.image_view = pg.ImageItem()
        
        self.roi = pg.RectROI(pos=(10,10), size=20, pen=(255, 0, 0), handlePen=(0,255,0))
        self.roi.handleSize=1
        border_pen = pg.mkPen(color=(255, 0, 0), width=2)

        self.v2 = self.addViewBox(1,0)
        self.v2.addItem(self.image_view)
        self.v2.addItem(self.roi)
        self.v2.invertY(True)
        self.v2.setAspectLocked(True)
        self.v2.setMenuEnabled(False)
        self.v2.setCursor(Qt.CrossCursor) 
        self.v2.setMouseEnabled(x=False, y=False)
        self.v2.scene().sigMouseMoved.connect(self.mouseMoveEvent)
        self.v2.scene().sigMouseClicked.connect(self.mousePressEvent)
        self.v2.disableAutoRange()
        self.v2.setBorder(None)
        self.v2.setBorder(border_pen)
 
        self.roi.removeHandle(0)

    def setZoomLimits(self, yrange, xrange):
        self.v2.setXRange(0, xrange, padding=0)
        self.v2.setYRange(0, yrange, padding=0)
        x = int(np.floor(xrange*0.025))
        y = int(np.floor(yrange*0.025))

    def keyPressEvent(self, ev):
        if ev.key() == 45:
            self.zoom_sf=1.1
            self.zoom(self.zoom_sf)
        elif ev.key() == 61:
            self.zoom_sf=0.9
            self.zoom(self.zoom_sf)
        elif ev.key() == 91: #[
            l = self.roi.size().x()
            self.roi.setSize(l-2,l-2)
        elif ev.key() == 93: #]
            l = self.roi.size().x()
            self.roi.setSize(l-2,l-2)
        elif ev.key() == 48: #reset view
            self.reset_view()
        else:
            super().keyPressEvent(ev)

    def reset_view(self):
        self.zoom(1)
        self.setZoomLimits(self.image_view.height(), self.image_view.width())
        print(self.image_view.height(), self.image_view.height())
        self.image_view.setPos(0,0)

    def zoom(self, factor):
        try:
            self.v2.scaleBy((factor, factor), center=(self.moving_pos.x(), self.moving_pos.y()))
        except: 
            self.v2.scaleBy((factor, factor), center=(0, 0))

    def wheelEvent(self,ev):
        print(ev.angleDelta().y())
        if ev.angleDelta().y()<0:
            self.zoom_sf=1.03
            self.zoom(self.zoom_sf)
        elif ev.angleDelta().y()>0:
            self.zoom_sf=0.97
            self.zoom(self.zoom_sf)
        self.moving_pos = self.v2.mapSceneToView(ev.pos())
        print(self.v2.pos())

    def mouseMoveEvent(self, ev):
        self.v2.setCursor(Qt.CrossCursor) 
        self.moving_pos = self.v2.mapSceneToView(ev.pos())
        self.mouseMoveSig.emit(self.moving_pos.x(), self.moving_pos.y())
        # self.roi.setPos([self.moving_pos.x(), self.moving_pos.y()], finish=False)
        diff = self.moving_pos - self.start_pos
        if self.last_moving_pos is None:
            self.last_moving_pos = self.start_pos
        inc = self.moving_pos - self.last_moving_pos
        
        if ev.buttons() == Qt.LeftButton and self.start_pos !=  self.moving_pos:
            if self.image_view.width() is None: 
                return
            self.image_view.setPos(diff.x() + self.img_pos.x(), diff.y() + self.img_pos.y())

        self.last_moving_pos = self.moving_pos

    def mousePressEvent(self, ev):
        self.start_pos = self.v2.mapSceneToView(ev.pos())
        self.img_pos = self.image_view.pos()
        p = self.v2.viewRange()

        if ev.button() == 1: #left button mouse
            pos = (self.start_pos.x()+20, self.start_pos.y()+20)

        if ev.button() == 2: #right button mouse
            pos = (self.start_pos.x()+20, self.start_pos.y()+20)

            
    def mouseReleaseEvent(self, ev):
        # Clear the starting position when the mouse button is released
        self.end_pos = self.v2.mapSceneToView(ev.pos())
        print("end pos:", self.end_pos.x(), self.end_pos.y())
        if self.start_pos ==  self.end_pos:
            print("mouse clicked")
            self.move2pos(self.start_pos)
    
    def move2pos(self):
        #TODO: move motors to clicked positions
        pass

class Stream(QtCore.QObject):
    newText = pyqtSignal(str)
    
    def write(self, text):
        self.newText.emit(str(text))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

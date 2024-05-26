import sys
import PyQt5
from PyQt5.QtWidgets import QStyle, QGridLayout, QPushButton, QComboBox, QGraphicsView, QGraphicsScene, QLabel, QSlider, QVBoxLayout, QHBoxLayout, QFrame, QApplication, QWidget, QMainWindow, QTextEdit
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


#Need to fix the spot positioning after DRAGGING image
#TODO: add element dropdown
#TODO: add button to apply correction
#TODO: add 
#TODO: add function to calcaulate scale and angle offsets
#TODO: add function to scale colume 
#TODO: add function to rotate volume

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        sys.stdout = Stream(newText=self.onUpdateText)

        # self.setStyleSheet("background-color: black;")

        self.setWindowTitle("Drag and Drop Files")
        self.setGeometry(100, 100, 600, 600)

        self.view = ImageView()
        self.controls = Contorls()
        self.logbox = QTextEdit("")
        self.logbox.setFixedWidth(600)
        self.logbox.setStyleSheet("background: beige; color: black")
        self.logbox.setReadOnly(True)

        

        vbox = QVBoxLayout()
        vbox.addWidget(self.view)
        vbox.addWidget(self.logbox)
        # vbox.addWidget(self.logbox)
        # vbox.addWidget(self.controls)

        hbox = QHBoxLayout()
        hbox.addLayout(vbox)
        hbox.addWidget(self.controls)

        self.frame = QFrame()
        self.frame.setLayout(hbox)
        self.setCentralWidget(self.frame)
        self.show()

    def onUpdateText(self, text):
        cursor = self.logbox.textCursor()
        cursor.insertText(text)
        self.logbox.setTextCursor(cursor)
        self.logbox.ensureCursorVisible()

class Contorls(QWidget):
    def __init__(self):
        super(Contorls, self).__init__()
        self.setMinimumSize(200,600)
        # Remove border spacing and margins

        self.dpad = DPadWidget()
        


        layout = QVBoxLayout()
        layout.addWidget(self.dpad)

        
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.initUI()

    def initUI(self):
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
        up_button = QPushButton()
        up_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowUp')))
        up_button.setIconSize(QSize(32, 32))
        
        down_button = QPushButton()
        down_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowDown')))
        down_button.setIconSize(QSize(32, 32))
        
        left_button = QPushButton()
        left_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowLeft')))
        left_button.setIconSize(QSize(32, 32))
        
        right_button = QPushButton()
        right_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_ArrowRight')))
        right_button.setIconSize(QSize(32, 32))
        
        center_button = QPushButton()
        center_button.setIcon(self.style().standardIcon(getattr(QStyle, 'SP_DialogYesButton')))
        center_button.setIconSize(QSize(32, 32))

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
        self.zoom_view = pg.ImageItem()

        self.roi = pg.RectROI(pos=(20,20), size=40, pen=(255, 0, 0), handlePen=(0,255,0))
        self.roi.handleSize=1
        self.roi.sigRegionChanged.connect(self.updateRoi)
        border_pen = pg.mkPen(color=(255, 255, 255), width=2)

        self.v2 = self.addViewBox(1,0)
        self.v2.addItem(self.image_view)
        self.v2.addItem(self.roi)
        self.v2.invertY(True)
        self.v2.setAspectLocked(True)
        self.v2.setMenuEnabled(False)
        self.v2.setCursor(Qt.BlankCursor) 
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

    def updateRoi(self, roi):
        try:
            self.arr1 = roi.getArrayRegion(self.image_view.image, img=self.image_view)
            self.zoom_view.setImage(self.arr1)

        except: 
            pass
    def keyPressEvent(self, ev):
        if ev.key() == 45:
            self.zoom_sf=1.1
            self.zoom(self.zoom_sf)
        elif ev.key() == 61:
            self.zoom_sf=0.9
            self.zoom(self.zoom_sf)
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
        self.v2.setCursor(Qt.BlankCursor) 
        self.moving_pos = self.v2.mapSceneToView(ev.pos())
        self.mouseMoveSig.emit(self.moving_pos.x(), self.moving_pos.y())
        self.roi.setPos([self.moving_pos.x(), self.moving_pos.y()], finish=False)
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

class Stream(QtCore.QObject):
    newText = pyqtSignal(str)
    
    def write(self, text):
        self.newText.emit(str(text))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

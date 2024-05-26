import sys
import PyQt5
from PyQt5.QtWidgets import QPushButton, QListWidget, QComboBox, QGraphicsView, QGraphicsScene, QLabel, QSlider, QVBoxLayout, QHBoxLayout, QFrame, QApplication, QWidget, QMainWindow, QListWidgetItem
from PyQt5.QtCore import pyqtSignal
from PyQt5 import Qt
from PyQt5.QtCore import *
from PyQt5.QtGui import QPixmap, QTransform
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

class DragAndDropListWidget(QListWidget):
    filesAddedSig = pyqtSignal(name="fileAdded")

    def __init__(self):
        super().__init__()
        self.setMaximumHeight(200)
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls:
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            for url in mime_data.urls():
                file_path = url.toLocalFile()
                self.addItem(file_path)
        self.filesAddedSig.emit()

    def clear_list_widget(self):
        self.clear()

class FileItemWidget(QWidget):
    def __init__(self, file_path):
        super().__init__()
        layout = PyQt5.QtWidgets.QHBoxLayout()
        self.path_name = QLabel(file_path)
        layout.addWidget(self.path_name)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # self.setStyleSheet("background-color: black;")

        self.setWindowTitle("Drag and Drop Files")
        self.setGeometry(100, 100, 400, 500)

        self.stack_left = customWidget()
        self.stack_right = customWidget()

        # Create a rotated button
        self.apply = QPushButton("^^ Apply transformation ^^")
        self.apply.clicked.connect(self.apply_transform)
        scene = QGraphicsScene()
        gsw = scene.addWidget(self.apply)
        gsw.setPos(50,50)
        gsw.setRotation(90)
        gw = QGraphicsView()
        gw.setScene(scene)

        self.combined = customWidget()
        self.combined.setVisible(False)

        self.layout = QHBoxLayout()
        self.layout.addWidget(self.stack_left)
        self.layout.addWidget(self.stack_right)
        self.layout.addWidget(gw)
        self.layout.addWidget(self.combined)

        self.frame = QFrame()
        self.frame.setLayout(self.layout)
        self.setCentralWidget(self.frame)

    def apply_transform(self): 
        #TODO: if transforms valid and nothing else missing, reveal next windwo
        self.combined.setVisible(True)

class customWidget(QWidget):
    def __init__(self):
        super(customWidget, self).__init__()
        self.setMinimumSize(300,300)
        self.stack = ImageView()
        self.elements = QComboBox()
        self.elements.addItems(["Channel1"])
        self.elements.setMaximumWidth(60)
        self.sld = QSlider(Qt.Horizontal, self)
        self.sld.setObjectName("sld")
        self.sld.sliderReleased.connect(self.slider_changed)
        self.el_sl = QHBoxLayout()
        self.el_sl.addWidget(self.elements)
        self.el_sl.addWidget(self.sld)
        self.clr = QPushButton("clear file list")
        self.clr.clicked.connect(self.clear_list)
        self.files = DragAndDropListWidget()
        self.files.setObjectName("files")
        self.files.filesAddedSig.connect(self.load_files)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.stack)
        self.layout.addLayout(self.el_sl)
        self.layout.addWidget(self.clr)
        self.layout.addWidget(self.files)
        self.setLayout(self.layout)

    def slider_changed(self):
        self.stack.image_view.setImage(self.imgs[self.sld.value()])

    def clear_list(self):
        self.files.clear()
        self.stack.image_view.clear()
        self.stack.scatter.clear()
        self.elements.clear()
        self.elements.addItem("Channel1")

    def calculate_distortion(pointsA, pointsB):
        #TODO:  translation
        #Angular transform
        #scale transform
        pass
    
    def rotate_volume(self, recon, angles):
        # angles = [x_deg,y_deg,z_deg]
        if angles[0] != 0:
            axes = (0, 1)  # z,y
            recon = ndimage.rotate(recon, angles[0], axes=axes)

        if angles[1] != 0:
            axes = (1, 2)  # y,x
            recon = ndimage.rotate(recon, angles[1], axes=axes)

        if angles[2] != 0:
            axes = (0, 2)  # x,z
            recon = ndimage.rotate(recon, angles[2], axes=axes)

        return recon
    
    def resize_volume(vol, x,y,z):
        resized_array = resize(vol, (x,y,z), mode='constant', anti_aliasing=True)
        return resized_array

    def load_files(self):
        #get files list from sender. 
        listwidget = self.sender()
        files = [listwidget.item(x).text() for x in range(listwidget.count())]
        try: 
            img = imageio.v3.imread(files[0])
        except Exception as e: 
            print(e)
            return
        if len(files) ==1: 
            canvas = imageio.v3.imread(files[0])
        else: 
            shp = (len(files),*img.shape)
            canvas = np.zeros(shp)
            for i in range(len(files)):
                canvas[i] = imageio.v3.imread(files[i])

        self.imgs = canvas
        self.sld.setRange(0,canvas.shape[0]-1)
        self.stack.image_view.setImage(canvas[0])
        self.stack.reset_view()
        # self.adjust_widget()

    # def adjust_widget(self):
    #     h = self.stack.image_view.height()
    #     w = self.stack.image_view.width()

    #     ow = self.stack.width()
    #     oh = self.stack.height()

    #     nw = int(ow*(w/h))  # #200 # stretches horizontally
    #     # nh = int(oh*(h/nw)) # 50 # squished         
    #     self.stack.setFixedSize(oh,nw)


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
        self.spots_data = []
        self.spots_pos = [None, None, None]   
        self.last_moving_pos = None
        self.zoom_sf = 1
        self.image_view = pg.ImageItem()
        self.zoom_view = pg.ImageItem()

        self.scatter = pg.ScatterPlotItem(size=10, brush=pg.mkBrush(255, 255, 255, 120))
        self.roi = pg.CircleROI(pos=(20,20), size=40, pen=(255, 0, 0), handlePen=(0,255,0))
        self.roi.handleSize=1
        self.roi.sigRegionChanged.connect(self.updateRoi)
        border_pen = pg.mkPen(color=(255, 255, 255), width=2)

        self.v2 = self.addViewBox(1,0)
        self.v2.addItem(self.image_view)
        self.v2.addItem(self.scatter)
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
            self.scatter.moveBy(inc.x(), inc.y())

        self.last_moving_pos = self.moving_pos

    def mousePressEvent(self, ev):
        self.start_pos = self.v2.mapSceneToView(ev.pos())
        self.img_pos = self.image_view.pos()
        p = self.v2.viewRange()

        if ev.button() == 1:
            pos = (self.start_pos.x()+20, self.start_pos.y()+20)
            if self.spots_pos[0] is None:
                self.spots_pos[0] = np.array(pos)
                self.spots_data.append({'pos': pos, 'brush': 'red', 'pen': 'red'})
            elif self.spots_pos[1] is None:
                self.spots_pos[1] = np.array(pos)
                self.spots_data.append({'pos': pos, 'brush': 'green', 'pen': 'green'})
            elif self.spots_pos[2] is None:
                self.spots_pos[2] = np.array(pos)
                self.spots_data.append({'pos': pos, 'brush': 'blue', 'pen': 'blue'})
            else: 
                return
            self.scatter.setData(self.spots_data)
            print(self.spots_pos)

        if ev.button() == 2:
            pos = (self.start_pos.x()+20, self.start_pos.y()+20)
            print(pos)
            print(self.spots_pos)
            diffs = []
            for i in self.spots_pos:
                if i is None:
                    diffs.append(np.inf)
                else:
                    diffs.append(math.dist(pos, i))
    
            if np.array(diffs).any() is not None: 
                if any(np.array(diffs)<100):
                    minpos = diffs.index(min(diffs))
                    self.spots_pos[minpos] = None
                else:
                    return
                self.spots_data = []
                if self.spots_pos[0] is not None:
                    self.spots_data.append({'pos': self.spots_pos[0], 'brush': 'red', 'pen': 'red'})
                if self.spots_pos[1] is not None:
                    self.spots_data.append({'pos': self.spots_pos[1], 'brush': 'green', 'pen': 'green'})
                if self.spots_pos[2] is not None:
                    self.spots_data.append({'pos': self.spots_pos[2], 'brush': 'blue', 'pen': 'blue'})
                self.scatter.clear()
                self.scatter.setData(self.spots_data)
            else:
                return
            
    def mouseReleaseEvent(self, ev):
        # Clear the starting position when the mouse button is released
        self.end_pos = self.v2.mapSceneToView(ev.pos())
        print("end pos:", self.end_pos.x(), self.end_pos.y())
        if self.start_pos ==  self.end_pos:
            print("mouse clicked")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

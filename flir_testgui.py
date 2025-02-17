import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QStackedWidget
from GigEv2 import FlirCameraWidget  # Import your custom widget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PyQt5 Custom Widget Loader")
        self.setGeometry(100, 100, 1024, 768)

        # Create a stacked widget to hold multiple widgets
        self.stacked_widget = QStackedWidget(self)
        self.setCentralWidget(self.stacked_widget)

        # Load custom widget (e.g., FLIR Camera Widget)
        self.flir_camera_widget = FlirCameraWidget()
        self.stacked_widget.addWidget(self.flir_camera_widget)

        # Add menu for switching widgets
        self.init_menu()

    def init_menu(self):
        """Create a menu bar for switching between widgets."""
        menu_bar = self.menuBar()
        widget_menu = menu_bar.addMenu("Widgets")

        # Action to show the FLIR Camera Widget
        flir_action = QAction("FLIR Camera Widget", self)
        flir_action.triggered.connect(lambda: self.stacked_widget.setCurrentWidget(self.flir_camera_widget))
        widget_menu.addAction(flir_action)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
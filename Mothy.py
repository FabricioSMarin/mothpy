from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QSizePolicy, QLineEdit, QScrollArea, QFrame, QComboBox, QSplitter, QTabWidget
from PyQt5.QtCore import Qt, QSettings, pyqtSignal, QTimer, QThread, QObject, pyqtSlot
from PyQt5 import QtCore
import sys
import os
import time
import csv
import json
from datetime import datetime
import numpy as np
import imageio
from scipy.optimize import curve_fit
from scipy.ndimage import shift as ndi_shift, gaussian_filter, affine_transform
from scipy.signal import correlate2d

# Suppress Teledyne DALSA CORMEM.SYS popup by clearing GenTL paths
os.environ['GENICAM_GENTL64_PATH'] = ''
os.environ['SPINNAKER_GENTL64_CTI'] = ''

# Also try setting to Spinnaker-only path (adjust if your Spinnaker is installed elsewhere)
spinnaker_gentl = r"C:\Program Files\FLIR Systems\Spinnaker\cti64\vs2015"
if os.path.exists(spinnaker_gentl):
    os.environ['GENICAM_GENTL64_PATH'] = spinnaker_gentl

# On Windows, suppress error dialogs for missing drivers
if sys.platform == 'win32':
    import ctypes
    # SEM_FAILCRITICALERRORS = 0x0001 - Suppress critical error dialog boxes
    SEM_FAILCRITICALERRORS = 0x0001
    ctypes.windll.kernel32.SetErrorMode(SEM_FAILCRITICALERRORS)

import PySpin
from PIL import Image  # Only used for resizing if needed
import serial
from serial.tools import list_ports

from motor import MotorSettings
from cam import Controls
from dpad import DPad
from visuals import ImagePlotWidget


def _prepare_pyspin_acquisition(cam, params):
    """Apply exposure/gain and start streaming. Must run off the Qt GUI thread."""
    is_continuous = bool(params.get("is_continuous", False))
    verbose = bool(params.get("verbose", not is_continuous))
    exposure_time = float(params.get("exposure_time", 10000))
    gain = float(params.get("gain", 1.0))

    nodemap = cam.GetNodeMap()
    try:
        try:
            frame_rate_enable = PySpin.CBooleanPtr(nodemap.GetNode('AcquisitionFrameRateEnable'))
            if PySpin.IsAvailable(frame_rate_enable) and PySpin.IsWritable(frame_rate_enable):
                frame_rate_enable.SetValue(False)
                if verbose:
                    print("Disabled frame rate control to allow long exposures")
        except Exception:
            try:
                frame_rate_auto = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionFrameRateAuto'))
                if PySpin.IsAvailable(frame_rate_auto) and PySpin.IsWritable(frame_rate_auto):
                    frame_rate_auto.SetIntValue(frame_rate_auto.GetEntryByName('Off').GetValue())
                    if verbose:
                        print("Set frame rate auto to Off")
            except Exception:
                pass

        try:
            trigger_mode = PySpin.CEnumerationPtr(nodemap.GetNode('TriggerMode'))
            if PySpin.IsAvailable(trigger_mode) and PySpin.IsWritable(trigger_mode):
                trigger_mode.SetIntValue(trigger_mode.GetEntryByName('Off').GetValue())
                if verbose:
                    print("Set trigger mode to Off")
        except Exception:
            pass

        exposure_auto = PySpin.CEnumerationPtr(nodemap.GetNode('ExposureAuto'))
        if PySpin.IsAvailable(exposure_auto) and PySpin.IsWritable(exposure_auto):
            exposure_auto.SetIntValue(exposure_auto.GetEntryByName('Off').GetValue())

        exposure_mode = PySpin.CEnumerationPtr(nodemap.GetNode('ExposureMode'))
        if PySpin.IsAvailable(exposure_mode) and PySpin.IsWritable(exposure_mode):
            exposure_mode.SetIntValue(exposure_mode.GetEntryByName('Timed').GetValue())

        exposure_node = PySpin.CFloatPtr(nodemap.GetNode("ExposureTime"))
        if PySpin.IsAvailable(exposure_node) and PySpin.IsWritable(exposure_node):
            exposure_min = exposure_node.GetMin()
            exposure_max = exposure_node.GetMax()
            requested_exposure = exposure_time
            was_clamped = False
            if exposure_time > exposure_max:
                exposure_time = exposure_max
                was_clamped = True
                if verbose:
                    print(f"WARNING: Requested exposure {requested_exposure} µs exceeds camera maximum!")
                    print(f"         Setting to maximum: {exposure_max} µs ({exposure_max/1000:.3f} ms)")
            elif exposure_time < exposure_min:
                exposure_time = exposure_min
                was_clamped = True
                if verbose:
                    print(f"WARNING: Requested exposure {requested_exposure} µs below camera minimum!")
                    print(f"         Setting to minimum: {exposure_min} µs")

            exposure_node.SetValue(exposure_time)
            actual_exposure = exposure_node.GetValue()
            if verbose and not was_clamped:
                print(f"Exposure set to: {actual_exposure} µs ({actual_exposure/1000:.3f} ms)")
                print(f"Camera range: {exposure_min/1000:.1f} - {exposure_max/1000:.1f} ms")
        elif verbose:
            print("Exposure time node not available/writable")
    except Exception as e:
        if verbose:
            print("Could not set exposure time:", e)

    try:
        gain_auto = PySpin.CEnumerationPtr(nodemap.GetNode('GainAuto'))
        if PySpin.IsAvailable(gain_auto) and PySpin.IsWritable(gain_auto):
            gain_auto.SetIntValue(gain_auto.GetEntryByName('Off').GetValue())

        gain_node = PySpin.CFloatPtr(nodemap.GetNode("Gain"))
        if PySpin.IsAvailable(gain_node) and PySpin.IsWritable(gain_node):
            gain_min = gain_node.GetMin()
            gain_max = gain_node.GetMax()
            gain = max(min(gain, gain_max), gain_min)
            gain_node.SetValue(gain)
            if verbose:
                print(f"Set gain to {gain} dB")
        elif verbose:
            print("Gain node not available/writable")
    except Exception as e:
        if verbose:
            print("Could not set gain:", e)

    try:
        acquisition_mode_node = PySpin.CEnumerationPtr(nodemap.GetNode("AcquisitionMode"))
        if PySpin.IsAvailable(acquisition_mode_node) and PySpin.IsWritable(acquisition_mode_node):
            if is_continuous:
                acquisition_mode_node.SetIntValue(PySpin.AcquisitionMode_Continuous)
            else:
                acquisition_mode_node.SetIntValue(PySpin.AcquisitionMode_SingleFrame)
    except Exception as e:
        if verbose:
            print("Could not set acquisition mode:", e)

    if not is_continuous or not cam.IsStreaming():
        if cam.IsStreaming():
            cam.EndAcquisition()
            time.sleep(0.1)
        if not is_continuous:
            cam.DeInit()
            time.sleep(0.2)
            cam.Init()
            time.sleep(0.3)
        cam.BeginAcquisition()
        time.sleep(0.1)
        if verbose:
            print("Acquisition started, waiting for image...")

    if exposure_time > 1000000:
        timeout_ms = int(exposure_time / 1000 * 2) + 5000
    else:
        timeout_ms = max(3000, int(exposure_time / 1000) + 3000)

    if verbose and exposure_time >= 500000:
        if exposure_time >= 1000000:
            print(f"Long exposure: {exposure_time/1000000:.1f} seconds. Please wait...")
            print(f"Using {timeout_ms/1000:.1f} second timeout")
        else:
            print(f"Long exposure: {exposure_time/1000:.0f} ms. Please wait...")
    return timeout_ms


def _retrieve_pyspin_frame(cam, params, timeout_ms):
    """Blocking GetNextImage + convert. Must run off the Qt GUI thread."""
    is_continuous = bool(params.get("is_continuous", False))
    display_mode = params.get("display_mode", "Color")
    image_processor = PySpin.ImageProcessor()
    image_result = cam.GetNextImage(timeout_ms)
    image_np = None
    try:
        if image_result.IsIncomplete():
            print("Image incomplete with status %d" % image_result.GetImageStatus())
        elif display_mode == "Color":
            try:
                converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_RGB8)
                image_np = converted_image.GetNDArray()
            except Exception:
                converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                image_np = converted_image.GetNDArray()[..., ::-1].copy()
        elif display_mode == "Grayscale":
            try:
                converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_RGB8)
                image_color = converted_image.GetNDArray()
            except Exception:
                converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_BGR8)
                image_color = converted_image.GetNDArray()[..., ::-1].copy()
            if len(image_color.shape) == 3:
                image_np = np.dot(image_color[..., :3], [0.299, 0.587, 0.114]).astype(np.uint8)
            else:
                image_np = image_color
        else:
            try:
                converted_image = image_processor.Convert(image_result, PySpin.PixelFormat_Mono8)
                image_np = converted_image.GetNDArray()
            except Exception:
                image_np = image_result.GetNDArray()
        if image_np is not None:
            image_np = np.array(image_np, copy=True)
    finally:
        image_result.Release()

    if not is_continuous:
        cam.EndAcquisition()
    return image_np


def _shift_frame_to_lock(frame, offset_x, offset_y):
    """Shift a raw frame so the ROI1 star lands on the ROI center."""
    frame_f = frame.astype(np.float32, copy=False)
    if abs(offset_x) < 0.01 and abs(offset_y) < 0.01:
        return np.array(frame_f, copy=True)
    if frame_f.ndim == 3:
        shift_vec = (-offset_x, -offset_y, 0.0)
    else:
        shift_vec = (-offset_x, -offset_y)
    return ndi_shift(frame_f, shift=shift_vec, order=1, mode="constant", cval=0.0)


def _rotate_frame_around_point(frame, cx, cy, angle_rad):
    """Rotate image content counterclockwise around (cx, cy) in [x, y] axes."""
    if abs(angle_rad) < 1e-6:
        return np.array(frame, dtype=np.float32, copy=True)
    cos_a = float(np.cos(angle_rad))
    sin_a = float(np.sin(angle_rad))
    matrix = np.array([[cos_a, sin_a], [-sin_a, cos_a]], dtype=np.float64)
    center = np.array([cx, cy], dtype=np.float64)
    offset = center - matrix @ center
    frame_f = np.asarray(frame, dtype=np.float32)
    if frame_f.ndim == 2:
        return affine_transform(
            frame_f, matrix, offset=offset, order=1, mode="constant", cval=0.0
        )
    out = np.empty_like(frame_f)
    for channel in range(frame_f.shape[2]):
        out[:, :, channel] = affine_transform(
            frame_f[:, :, channel], matrix, offset=offset, order=1, mode="constant", cval=0.0
        )
    return out


def _align_frame_pixels(frame, cx, cy, angle_rad, offset_x, offset_y):
    aligned = frame
    if abs(angle_rad) >= 1e-6:
        aligned = _rotate_frame_around_point(aligned, cx, cy, angle_rad)
    return _shift_frame_to_lock(aligned, offset_x, offset_y)


def _refine_alignment_cross_correlation(frame, reference, max_shift=10):
    """
    Refine alignment using phase/cross-correlation between frame and reference.
    Returns refined (dx, dy) offset in pixels.
    
    Args:
        frame: Frame to align (already roughly aligned)
        reference: Reference image (current stack mean)
        max_shift: Maximum pixels to search for refinement
    
    Returns:
        (refined_dx, refined_dy): Sub-pixel shift to apply for best alignment
    """
    if reference is None or frame.shape != reference.shape:
        return 0.0, 0.0
    
    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        frame_gray = np.mean(frame, axis=2).astype(np.float32)
    else:
        frame_gray = frame.astype(np.float32)
    
    if len(reference.shape) == 3:
        ref_gray = np.mean(reference, axis=2).astype(np.float32)
    else:
        ref_gray = reference.astype(np.float32)
    
    # Work on a central region to speed up computation
    h, w = frame_gray.shape
    crop_size = min(h, w, 512)  # Use central 512x512 region
    y_start = (h - crop_size) // 2
    x_start = (w - crop_size) // 2
    
    frame_crop = frame_gray[y_start:y_start+crop_size, x_start:x_start+crop_size]
    ref_crop = ref_gray[y_start:y_start+crop_size, x_start:x_start+crop_size]
    
    # Normalize to reduce brightness variations
    frame_crop = frame_crop - np.mean(frame_crop)
    ref_crop = ref_crop - np.mean(ref_crop)
    
    # Compute cross-correlation (this is the compute-intensive part)
    # Only search within max_shift radius
    search_size = max_shift * 2 + 1
    y_center = crop_size // 2
    x_center = crop_size // 2
    
    frame_search = frame_crop[y_center-max_shift:y_center+max_shift+1,
                              x_center-max_shift:x_center+max_shift+1]
    ref_search = ref_crop[y_center-max_shift:y_center+max_shift+1,
                          x_center-max_shift:x_center+max_shift+1]
    
    # Cross-correlation
    corr = correlate2d(ref_search, frame_search, mode='same')
    
    # Find peak
    peak_y, peak_x = np.unravel_index(np.argmax(corr), corr.shape)
    
    # Convert to offset (relative to center)
    dy = peak_y - max_shift
    dx = peak_x - max_shift
    
    # Sub-pixel refinement using parabolic fit around peak
    if 0 < peak_y < search_size-1 and 0 < peak_x < search_size-1:
        # Parabolic fit in Y
        c1 = corr[peak_y-1, peak_x]
        c2 = corr[peak_y, peak_x]
        c3 = corr[peak_y+1, peak_x]
        if c1 != c3:  # Avoid division by zero
            dy_sub = 0.5 * (c1 - c3) / (c1 - 2*c2 + c3)
            dy += dy_sub
        
        # Parabolic fit in X
        c1 = corr[peak_y, peak_x-1]
        c2 = corr[peak_y, peak_x]
        c3 = corr[peak_y, peak_x+1]
        if c1 != c3:
            dx_sub = 0.5 * (c1 - c3) / (c1 - 2*c2 + c3)
            dx += dx_sub
    
    return float(dx), float(dy)


class CaptureWorker(QObject):
    """Runs blocking camera grabs and stack alignment off the Qt GUI thread."""
    image_ready = pyqtSignal(object)
    aligned_ready = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    @pyqtSlot(object, dict)
    def grab(self, cams, params):
        cam_list = list(cams) if isinstance(cams, (list, tuple)) else [cams]
        frames = [None] * len(cam_list)
        try:
            timeouts = []
            for i, cam in enumerate(cam_list):
                if cam is None:
                    timeouts.append(None)
                    continue
                cam_params = dict(params)
                cam_params["verbose"] = (i == 0 and not params.get("is_continuous", False))
                timeouts.append(_prepare_pyspin_acquisition(cam, cam_params))
            for i, cam in enumerate(cam_list):
                if cam is None:
                    continue
                try:
                    frames[i] = _retrieve_pyspin_frame(cam, params, timeouts[i])
                except Exception as cam_error:
                    self.error.emit(f"Camera {i + 1} grab failed: {cam_error}")
            self.image_ready.emit(frames)
        except Exception as e:
            self.error.emit(str(e))
            for cam in cam_list:
                if cam is None:
                    continue
                try:
                    if cam.IsStreaming():
                        cam.EndAcquisition()
                    cam.DeInit()
                    time.sleep(0.5)
                    cam.Init()
                except Exception as recovery_error:
                    self.error.emit(f"Error during recovery: {recovery_error}")
        finally:
            self.finished.emit()

    @pyqtSlot(object)
    def align_stack(self, job):
        try:
            # Initial alignment using centroid-based transform
            aligned = _align_frame_pixels(
                job["frame"], job["cx"], job["cy"], job["delta"],
                job["offset_x"], job["offset_y"],
            )
            
            # Secondary refinement using cross-correlation if reference exists
            reference = job.get("reference", None)
            if reference is not None:
                dx, dy = _refine_alignment_cross_correlation(aligned, reference, max_shift=10)
                
                # Apply refined shift if significant (> 0.1 pixels)
                if abs(dx) > 0.1 or abs(dy) > 0.1:
                    # Shift is in [x, y] coordinates, but ndi_shift needs [y, x] for 2D
                    if aligned.ndim == 3:
                        shift_vec = (-dy, -dx, 0.0)  # [y, x, channel]
                    else:
                        shift_vec = (-dy, -dx)  # [y, x]
                    aligned = ndi_shift(aligned.astype(np.float32), shift=shift_vec, 
                                       order=1, mode='constant', cval=0.0)
                    
                    # Print debug info directly (not an error)
                    print(f"  Cross-corr refine: dx={dx:.2f}px, dy={dy:.2f}px")
            
            self.aligned_ready.emit(aligned)
        except Exception as e:
            self.error.emit(f"Stack align error: {e}")
            self.aligned_ready.emit(None)


class StackWorker(QObject):
    """Computes expensive stacking operations (median, sigma-clip) in background."""
    stack_ready = pyqtSignal(object)  # Emits the computed stack image
    batch_median_ready = pyqtSignal(object)  # Emits the computed batch median (float64)
    
    @pyqtSlot(list, str)
    def compute_stack(self, frames, mode):
        """Compute stack using the specified mode.
        
        Args:
            frames: List of aligned frames (uint8)
            mode: "Mean", "Median", or "Sigma-clip"
        """
        try:
            if not frames:
                self.stack_ready.emit(None)
                return
            
            if mode == "Median":
                result = self._compute_median(frames)
            elif mode == "Sigma-clip":
                result = self._compute_sigma_clip(frames)
            else:  # Mean
                result = self._compute_mean(frames)
            
            self.stack_ready.emit(result)
        except Exception as e:
            print(f"Stack worker error: {e}")
            self.stack_ready.emit(None)
    
    def _compute_mean(self, frames):
        stack = np.array(frames, dtype=np.float32)
        mean = np.mean(stack, axis=0)
        return np.clip(mean, 0, 255).astype(np.uint8)
    
    def _compute_median(self, frames):
        stack = np.array(frames, dtype=np.uint8)
        median = np.median(stack, axis=0)
        return median.astype(np.uint8)
    
    def _compute_sigma_clip(self, frames, sigma=3.0):
        if len(frames) < 3:
            return self._compute_mean(frames)
        
        stack = np.array(frames, dtype=np.float32)
        mean = np.mean(stack, axis=0)
        std = np.std(stack, axis=0)
        
        lower_bound = mean - sigma * std
        upper_bound = mean + sigma * std
        
        mask = (stack >= lower_bound[np.newaxis, :, :]) & (stack <= upper_bound[np.newaxis, :, :])
        masked_stack = np.where(mask, stack, np.nan)
        
        with np.errstate(invalid='ignore'):
            result = np.nanmean(masked_stack, axis=0)
        result = np.where(np.isnan(result), mean, result)
        
        return np.clip(result, 0, 255).astype(np.uint8)
    
    @pyqtSlot(list)
    def compute_batch_median(self, frames):
        """Compute median of a batch for Mean-of-Medians mode.
        
        Args:
            frames: List of aligned frames (uint8) from current batch
        """
        try:
            if not frames:
                self.batch_median_ready.emit(None)
                return
            
            stack = np.array(frames, dtype=np.uint8)
            batch_median = np.median(stack, axis=0).astype(np.float64)
            self.batch_median_ready.emit(batch_median)
        except Exception as e:
            print(f"Batch median worker error: {e}")
            self.batch_median_ready.emit(None)


class MainWindow(QMainWindow):
    _request_grab = pyqtSignal(object, dict)
    _request_align = pyqtSignal(object)
    _request_stack = pyqtSignal(list, str)  # (frames, mode)
    _request_batch_median = pyqtSignal(list)  # (frames)

    def __init__(self):
        super().__init__()
        self.set_dark_theme()

        self.original_stdout = sys.__stdout__  # Use sys.__stdout__ instead of sys.stdout
        self.stdout_stream = Stream(newText=self.onUpdateText)
        sys.stdout = self.stdout_stream
        self.settings = QSettings("Auranox", "Mothpy")  # Unique organization/app name
        self.trajectory = np.zeros((3,10000))
        self.tracked_points = 0
        
        # Setup continuous capture timer
        self.capture_timer = QTimer()
        self.capture_timer.timeout.connect(self.capture_single_frame)
        self.is_capturing = False
        self._grab_inflight = False
        self._init_capture_thread()
        self._init_stack_thread()
        
        # Setup tracking timer
        self.tracking_timer = QTimer()
        self.tracking_timer.timeout.connect(self.perform_tracking_update)
        self.is_tracking = False
        self.tracking_interval = 6000  # 6 seconds in milliseconds
        self.live_capture_interval = 100  # ms, preview-only loop
        # Star lock from the first successful tracking acquisition (image coords).
        # Later frames are compared against this fixed position to avoid walk-off.
        self.tracking_ref_x = None
        self.tracking_ref_y = None
        self.latest_frame = None  # last raw camera frame (after rotation)
        self.latest_frame_id = 0
        self.tracking_ingested_id = -1
        
        # Stacking system: Hybrid approach for different use cases
        # RING BUFFER: For median/sigma-clip (keeps recent N frames)
        self.tracking_stack_frames = []  # List of aligned frames (uint8) for stacking
        self.tracking_stack_max_frames = 100  # Maximum frames to keep in buffer
        
        # ACCUMULATOR: For deep space mean stacking (unlimited, memory efficient)
        self.tracking_accumulator = None  # float64 running sum (never discarded)
        self.tracking_accumulator_count = 0  # Total frames accumulated
        self.tracking_weight_map = None  # Tracks how many frames contributed to each pixel
        
        # BATCH MEDIAN MODE: Compute median every N frames, then mean those medians
        self.tracking_batch_frames = []  # Current batch for median computation
        self.tracking_batch_size = 100  # Frames per batch
        self.tracking_median_accumulator = None  # Mean of batch medians
        self.tracking_median_batch_count = 0  # Number of batches processed
        
        # Display update throttling
        self.tracking_stack_display_counter = 0  # Counter for expensive stack updates
        self.tracking_stack_display_interval = 100  # Update median/sigma every N frames
        self.tracking_stack_cached_image = None  # Cached result of last expensive stack
        self._stack_computation_pending = False  # Flag to prevent duplicate requests
        self._batch_median_pending = False  # Flag to prevent duplicate batch median requests
        
        self.tracking_debug_dir = None
        self.tracking_csv_path = None
        self.tracking_frame_index = 0
        self.last_track_offset_x = None
        self.last_track_offset_y = None
        self.last_roi_width = None
        self.last_roi_height = None
        self.last_steps_x = 0
        self.last_steps_y = 0
        self.tracking_motor_frame_id = -1
        self.tracking_pixel_deadband = 1.5  # px; ignore jitter smaller than this
        self.tracking_ref_angle = None  # ROI1→ROI2 angle on first stacked frame
        self.last_stack_angle_deg = 0.0
        
        # USB serial link to ESP32 (replaces WiFi HTTP)
        self.esp32 = None
        self.esp32_baud = 115200
        self.is_closing = False  # Flag to prevent new requests during shutdown
        self.settings_send_timer = QTimer(self)
        self.settings_send_timer.setSingleShot(True)
        self.settings_send_timer.timeout.connect(self.send_motor_settings_to_esp32)
        
        # Hotspot calibration
        self.hotspot_mask = None  # Will store the hot pixel values to subtract for camera 1
        self.hotspot_mask2 = None  # Will store the hot pixel values to subtract for camera 2
        self.calibration_frames = []  # Buffer for collecting calibration frames (camera 1)
        self.calibration_frames2 = []  # Buffer for collecting calibration frames (camera 2)
        self.is_calibrating = False  # Flag for calibration mode
        self.dark_frame_path = "dark_frame_cam1.npy"  # Path to save/load dark frame for camera 1
        self.dark_frame_path2 = "dark_frame_cam2.npy"  # Path to save/load dark frame for camera 2
        self.cam = None
        self.cam2 = None
        self.cameras = []
        
        self.initUI()
        self.loadSettings()
        self.update_settings()
        self.load_dark_frame()  # Load dark frame if available
        self.connect_camera()


    def initUI(self):
        central_widget = QWidget()
        self.main_layout = QVBoxLayout()
        self.main_layout.setSpacing(4)
        self.main_layout.setContentsMargins(4, 4, 4, 4)

        self.logbox = QTextEdit("")
        self.logbox.setMinimumHeight(60)
        self.logbox.setMaximumHeight(120)
        self.logbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.logbox.setStyleSheet("background: rgb(30,30,30); color: rgb(30,70,30)")
        self.logbox.setReadOnly(True)

        # Add ESP32 USB serial port controls
        self.esp32_port_combo = QComboBox()
        self.esp32_port_combo.setMinimumWidth(120)
        self.esp32_refresh_btn = QPushButton("Refresh")
        self.esp32_connect_btn = QPushButton("Connect")
        self.esp32_connect_btn.setCheckable(True)
        self.esp32_status = QLabel("Disconnected")
        self.esp32_status.setStyleSheet("color: #ff6666;")
        self.dpad = DPad()
        self.motor1 = MotorSettings("Alt", self)
        self.motor2 = MotorSettings("Azi", self)
        self.motor3 = MotorSettings("Focus", self)
        self.camera_controls = Controls()
        self.camera_controls.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        
        # Camera 1: Live and Stacked views in tabs
        self.imgplot = ImagePlotWidget(title="Camera 1 - Live", show_rois=True)
        self.imgplot_stacked = ImagePlotWidget(title="Camera 1 - Stacked", show_rois=False)
        
        self.cam1_tabs = QTabWidget()
        self.cam1_tabs.addTab(self.imgplot, "Live")
        self.cam1_tabs.addTab(self.imgplot_stacked, "Stacked")
        
        # Camera 2: Single view (no stacking)
        self.imgplot2 = ImagePlotWidget(title="Camera 2", show_rois=False)
        
        # Initially hide camera panes until cameras are connected
        self.imgplot2.hide()
        
        # Camera live views expand to fill upper portion
        self.imgplot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.imgplot2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dpad.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        
        # ESP32 serial port row
        esp32_port_layout = QHBoxLayout()
        esp32_port_layout.addWidget(QLabel("ESP32 Port:"))
        esp32_port_layout.addWidget(self.esp32_port_combo, stretch=1)
        esp32_port_layout.addWidget(self.esp32_refresh_btn)
        esp32_port_layout.addWidget(self.esp32_connect_btn)
        esp32_port_layout.addWidget(self.esp32_status)
        
        # Arrow key hint label
        self.arrow_key_hint = QLabel("⌨️ Arrow Keys: ↑↓ = Alt | ←→ = Azi | [ ] = Steps")
        self.arrow_key_hint.setStyleSheet("color: #888888; font-size: 10px; padding: 5px;")
        self.arrow_key_hint.setAlignment(Qt.AlignCenter)

        # Motors stacked vertically under the dpad
        motors_col = QVBoxLayout()
        motors_col.setSpacing(4)
        motors_col.addWidget(self.motor1)
        motors_col.addWidget(self.motor2)
        motors_col.addWidget(self.motor3)
        
        # Controls below the camera views (dpad, motors, camera/color correction)
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(4)
        controls_layout.setContentsMargins(8, 4, 8, 4)
        controls_layout.addLayout(esp32_port_layout)
        controls_layout.addWidget(self.arrow_key_hint)
        controls_layout.addWidget(self.dpad)
        controls_layout.addLayout(motors_col)
        controls_layout.addWidget(self.camera_controls)
        controls_layout.setAlignment(Qt.AlignTop)

        controls_widget = QWidget()
        controls_widget.setLayout(controls_layout)
        controls_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        controls_scroll.setWidget(controls_widget)
        controls_scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        controls_scroll.setMinimumWidth(350)
        controls_scroll.setMaximumWidth(450)
        controls_scroll.setFrameShape(QFrame.NoFrame)

        # Landscape layout: Left side (cameras + log) | Right side (controls)
        # Left side: vertical layout with cameras above and log below
        self.cam_splitter = QSplitter(Qt.Vertical)
        self.cam_splitter.addWidget(self.cam1_tabs)
        self.cam_splitter.addWidget(self.imgplot2)
        self.cam_splitter.setChildrenCollapsible(True)
        self.cam_splitter.setStretchFactor(0, 1)
        self.cam_splitter.setStretchFactor(1, 1)
        
        left_layout = QVBoxLayout()
        left_layout.setSpacing(4)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.cam_splitter, stretch=4)
        left_layout.addWidget(self.logbox, stretch=1)
        
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        
        # Main horizontal splitter: cameras/log on left, controls on right
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(controls_scroll)
        main_splitter.setStretchFactor(0, 3)  # Left side gets more space
        main_splitter.setStretchFactor(1, 1)  # Right side (controls) is narrower
        
        self.main_layout.addWidget(main_splitter)

        central_widget.setLayout(self.main_layout)
        self.setCentralWidget(central_widget)
        self.setWindowTitle("Mothpy")

        # Prefer a wide landscape window within available screen space
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(1600, available.width())
            height = min(900, available.height())
            self.resize(width, height)
            self.move(
                available.x() + (available.width() - width) // 2,
                available.y() + (available.height() - height) // 2,
            )

        self.dpad.up_button.clicked.connect(self.up_clicked)
        self.dpad.down_button.clicked.connect(self.down_clicked)
        self.dpad.left_button.clicked.connect(self.left_clicked)
        self.dpad.right_button.clicked.connect(self.right_clicked)
        self.dpad.near_button.clicked.connect(self.near_clicked)
        self.dpad.far_button.clicked.connect(self.far_clicked)
        self.dpad.track_button.clicked.connect(self.track_clicked)
        self.dpad.stack_mode_combo.currentIndexChanged.connect(self.on_stack_mode_changed)
        self.cam1_tabs.currentChanged.connect(self.on_cam1_tab_changed)
        self.camera_controls.connect_camera.clicked.connect(self.connect_camera)
        self.camera_controls.rm_hotspots_button.clicked.connect(self.calibrate_hotspots)
        self.camera_controls.capture_button.clicked.connect(self.capture_image)
        self.camera_controls.capture_mode_combobox.currentIndexChanged.connect(self.on_capture_mode_changed)
        self.camera_controls.red_slider.valueChanged.connect(self.update_color_correction)
        self.camera_controls.green_slider.valueChanged.connect(self.update_color_correction)
        self.camera_controls.blue_slider.valueChanged.connect(self.update_color_correction)
        self.motor1.settingsChanged.connect(self.schedule_motor_settings_send)
        self.motor2.settingsChanged.connect(self.schedule_motor_settings_send)
        self.motor3.settingsChanged.connect(self.schedule_motor_settings_send)
        self.motor1.settingsChanged.connect(self.update_dpad_angle_labels)
        self.motor2.settingsChanged.connect(self.update_dpad_angle_labels)
        self.motor3.settingsChanged.connect(self.update_dpad_angle_labels)
        self.dpad.ud_lineedit.textChanged.connect(self.update_dpad_angle_labels)
        self.dpad.lr_lineedit.textChanged.connect(self.update_dpad_angle_labels)
        self.dpad.nf_lineedit.textChanged.connect(self.update_dpad_angle_labels)
        self.motor1.fields["Resolution"].textChanged.connect(self.update_dpad_angle_labels)
        self.motor2.fields["Resolution"].textChanged.connect(self.update_dpad_angle_labels)
        self.motor3.fields["Resolution"].textChanged.connect(self.update_dpad_angle_labels)
        self.esp32_refresh_btn.clicked.connect(self.refresh_serial_ports)
        self.esp32_connect_btn.clicked.connect(self.toggle_esp32_serial)
        QTimer.singleShot(0, self.update_dpad_angle_labels)
        QTimer.singleShot(0, self.refresh_serial_ports)
        QTimer.singleShot(500, self.auto_connect_esp32_serial)
        
        # Set initial camera visibility (no cameras connected yet)
        QTimer.singleShot(0, self._update_camera2_visibility)

    def _init_capture_thread(self):
        self.capture_thread = QThread(self)
        self.capture_worker = CaptureWorker()
        self.capture_worker.moveToThread(self.capture_thread)
        self._request_grab.connect(self.capture_worker.grab, Qt.QueuedConnection)
        self._request_align.connect(self.capture_worker.align_stack, Qt.QueuedConnection)
        self.capture_worker.image_ready.connect(self._on_captured_frame, Qt.QueuedConnection)
        self.capture_worker.aligned_ready.connect(self._on_aligned_frame, Qt.QueuedConnection)
        self.capture_worker.error.connect(self._on_capture_error, Qt.QueuedConnection)
        self.capture_worker.finished.connect(self._on_grab_finished, Qt.QueuedConnection)
        self.capture_thread.start()
    
    def _init_stack_thread(self):
        self.stack_thread = QThread(self)
        self.stack_worker = StackWorker()
        self.stack_worker.moveToThread(self.stack_thread)
        self._request_stack.connect(self.stack_worker.compute_stack, Qt.QueuedConnection)
        self._request_batch_median.connect(self.stack_worker.compute_batch_median, Qt.QueuedConnection)
        self.stack_worker.stack_ready.connect(self._on_stack_ready, Qt.QueuedConnection)
        self.stack_worker.batch_median_ready.connect(self._on_batch_median_ready, Qt.QueuedConnection)
        self.stack_thread.start()

    def _grab_timeout_s(self):
        try:
            exposure_time = float(self.camera_controls.exposure_edit.text())
        except (ValueError, AttributeError):
            exposure_time = 10000.0
        if exposure_time > 1000000:
            return exposure_time / 1000.0 * 2.0 + 8.0
        return max(5.0, exposure_time / 1000.0 + 5.0)

    def _wait_for_grab_idle(self, timeout_s=None):
        """Wait until the worker finishes GetNextImage. Keep the GUI pumping."""
        if not self._grab_inflight:
            return
        if timeout_s is None:
            timeout_s = self._grab_timeout_s()
        deadline = time.monotonic() + timeout_s
        while self._grab_inflight and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.02)

    def _shutdown_capture_thread(self):
        self.is_capturing = False
        if hasattr(self, "capture_timer"):
            self.capture_timer.stop()
        self._wait_for_grab_idle()
        if hasattr(self, "capture_thread") and self.capture_thread.isRunning():
            self.capture_thread.quit()
            if not self.capture_thread.wait(5000):
                print("Capture thread did not stop cleanly")
        

    def set_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QPushButton {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #4b4b4b;
            }
            QPushButton:pressed {
                background-color: #2b2b2b;
            }
            QLineEdit {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                padding: 3px;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QComboBox {
                background-color: #3b3b3b;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 3px;
                color: #ffffff;
            }
            QComboBox:drop-down {
                border: 0px;
            }
            QComboBox:down-arrow {
                background-color: #3b3b3b;
            }
            QComboBox QAbstractItemView {
                background-color: #3b3b3b;
                color: #ffffff;
                selection-background-color: #4b4b4b;
            }
        """)

    def onUpdateText(self, text):
        # Check if user has scrolled away from bottom BEFORE making changes
        scrollbar = self.logbox.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10  # Within 10px of bottom
        
        # Save current scroll position in case user is reading
        saved_scroll_position = scrollbar.value()
        
        # Move cursor to end and insert new text
        cursor = self.logbox.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        
        # Only auto-scroll if user was already at the bottom
        # Otherwise, restore their scroll position so they can keep reading
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(saved_scroll_position)

    def keyPressEvent(self, event):
        """Handle arrow key presses for motor control and bracket keys for step adjustment"""
        key = event.key()
        
        # Arrow Up = Motor 1 (Alt) Forward
        if key == Qt.Key_Up:
            self.up_clicked()
        # Arrow Down = Motor 1 (Alt) Backward
        elif key == Qt.Key_Down:
            self.down_clicked()
        # Arrow Left = Motor 2 (Azi) Forward
        elif key == Qt.Key_Left:
            self.left_clicked()
        # Arrow Right = Motor 2 (Azi) Backward
        elif key == Qt.Key_Right:
            self.right_clicked()
        # ] = Increase step size
        elif key == Qt.Key_BracketRight:
            self.adjust_step_size(100)
        # [ = Decrease step size
        elif key == Qt.Key_BracketLeft:
            self.adjust_step_size(-100)
        else:
            # Pass other keys to parent handler
            super().keyPressEvent(event)
    
    def adjust_step_size(self, delta):
        """Adjust step size for all motors by delta amount"""
        # Get current step value from U/D field
        try:
            current = int(self.dpad.ud_lineedit.text())
        except ValueError:
            current = 100  # Default if empty or invalid
        
        # Calculate new value (minimum 1 step)
        new_value = max(1, current + delta)
        new_text = str(new_value)
        
        # Update all step size fields
        self.dpad.ud_lineedit.setText(new_text)
        self.dpad.lr_lineedit.setText(new_text)
        self.dpad.nf_lineedit.setText(new_text)
        
        print(f"Step size adjusted to: {new_value} steps")

    def closeEvent(self, event):
        """ Triggered when the window is closed, used to save settings. """
        # Set closing flag to prevent new requests
        self.is_closing = True

        # Stop tracking if running
        if hasattr(self, 'is_tracking') and self.is_tracking:
            self._save_final_tracking_stack()
            self.is_tracking = False
            self.tracking_timer.stop()

        # Wait out any in-flight GetNextImage before touching the camera
        if self.is_capturing:
            self.stop_continuous_capture()
        else:
            self._wait_for_grab_idle()
        self._shutdown_capture_thread()
        
        sys.stdout = self.original_stdout
        self.stdout_stream.newText.disconnect()  
        self.saveSettings()
        
        # Close ESP32 serial connection
        self.disconnect_esp32_serial()
        
        self.disconnec_camera()
        event.accept()

    def saveSettings(self):
        """ Save the QLineEdit contents to QSettings """
        self.settings.setValue("ud_text", self.dpad.ud_lineedit.text())
        self.settings.setValue("lr_text", self.dpad.lr_lineedit.text())
        self.settings.setValue("nf_text", self.dpad.nf_lineedit.text())
        self.settings.setValue("stack_while_tracking", self.dpad.stack_checkbox.isChecked())

        self.settings.setValue("m1_visibility", self.motor1.toggle_button.isChecked())
        self.settings.setValue("m1_res", self.motor1.fields["Resolution"].text())
        self.settings.setValue("m1_velo", self.motor1.fields["Velocity"].text())
        self.settings.setValue("m1_acc", self.motor1.fields["Acceleration"].text())
        self.settings.setValue("m1_back", self.motor1.fields["Backlash"].text())
        self.settings.setValue("m1_invert", self.motor1.invert_checkbox.isChecked())

        self.settings.setValue("m2_visibility", self.motor2.toggle_button.isChecked())
        self.settings.setValue("m2_res", self.motor2.fields["Resolution"].text())
        self.settings.setValue("m2_velo", self.motor2.fields["Velocity"].text())
        self.settings.setValue("m2_acc", self.motor2.fields["Acceleration"].text())
        self.settings.setValue("m2_back", self.motor2.fields["Backlash"].text())
        self.settings.setValue("m2_invert", self.motor2.invert_checkbox.isChecked())

        self.settings.setValue("m3_visibility", self.motor3.toggle_button.isChecked())
        self.settings.setValue("m3_res", self.motor3.fields["Resolution"].text())
        self.settings.setValue("m3_velo", self.motor3.fields["Velocity"].text())
        self.settings.setValue("m3_acc", self.motor3.fields["Acceleration"].text())
        self.settings.setValue("m3_back", self.motor3.fields["Backlash"].text())
        self.settings.setValue("m3_invert", self.motor3.invert_checkbox.isChecked())

        self.settings.setValue("exposure", self.camera_controls.exposure_edit.text())
        self.settings.setValue("gain", self.camera_controls.gain_edit.text())
        self.settings.setValue("mode", self.camera_controls.color_mode_combobox.currentIndex())
        
        # Save ESP32 serial port
        self.settings.setValue("esp32_port", self.esp32_port_combo.currentText())
        self.settings.sync()  # Force settings to be written to disk

    def loadSettings(self):
        """ Load the QLineEdit contents from QSettings """
        try:
            self.dpad.ud_lineedit.setText(self.settings.value("ud_text", ""))
            self.dpad.lr_lineedit.setText(self.settings.value("lr_text", ""))
            self.dpad.nf_lineedit.setText(self.settings.value("nf_text", ""))
            stack_val = self.settings.value("stack_while_tracking", False)
            if isinstance(stack_val, str):
                stack_val = stack_val.lower() == "true"
            self.dpad.stack_checkbox.setChecked(bool(stack_val))


            val = self.settings.value("m1_visibility", True)
            self.motor1.toggle_button.setChecked(val.lower()=="true" if isinstance(val,str) else val)
            self.motor1.fields["Resolution"].setText(self.settings.value("m1_res", ""))
            self.motor1.fields["Velocity"].setText(self.settings.value("m1_velo", ""))
            self.motor1.fields["Acceleration"].setText(self.settings.value("m1_acc", ""))
            self.motor1.fields["Backlash"].setText(self.settings.value("m1_back", ""))
            invert_val = self.settings.value("m1_invert", False)
            self.motor1.invert_checkbox.setChecked(invert_val if isinstance(invert_val, bool) else invert_val.lower() == "true")

            val = self.settings.value("m2_visibility", True)
            self.motor2.toggle_button.setChecked(val.lower()=="true" if isinstance(val,str) else val)
            self.motor2.fields["Resolution"].setText(self.settings.value("m2_res", ""))
            self.motor2.fields["Velocity"].setText(self.settings.value("m2_velo", ""))
            self.motor2.fields["Acceleration"].setText(self.settings.value("m2_acc", ""))
            self.motor2.fields["Backlash"].setText(self.settings.value("m2_back", ""))
            invert_val = self.settings.value("m2_invert", False)
            self.motor2.invert_checkbox.setChecked(invert_val if isinstance(invert_val, bool) else invert_val.lower() == "true")

            val = self.settings.value("m3_visibility", True)
            self.motor3.toggle_button.setChecked(val.lower()=="true" if isinstance(val,str) else val)
            self.motor3.fields["Resolution"].setText(self.settings.value("m3_res", ""))
            self.motor3.fields["Velocity"].setText(self.settings.value("m3_velo", ""))
            self.motor3.fields["Acceleration"].setText(self.settings.value("m3_acc", ""))
            self.motor3.fields["Backlash"].setText(self.settings.value("m3_back", ""))
            invert_val = self.settings.value("m3_invert", False)
            self.motor3.invert_checkbox.setChecked(invert_val if isinstance(invert_val, bool) else invert_val.lower() == "true")

            self.camera_controls.exposure_edit.setText(self.settings.value("exposure", ""))
            self.camera_controls.gain_edit.setText(self.settings.value("gain", ""))
            
            # Load color mode (default to 0 = Color)
            color_mode_index = self.settings.value("mode", 0)
            if isinstance(color_mode_index, str):
                color_mode_index = int(color_mode_index) if color_mode_index.isdigit() else 0
            self.camera_controls.color_mode_combobox.setCurrentIndex(color_mode_index)
            
            # Load ESP32 serial port (applied after refresh_serial_ports)
            self._saved_esp32_port = self.settings.value("esp32_port", "COM3")
        except Exception as e:
            print(f"Error loading settings: {e}")
            self._saved_esp32_port = "COM3"

    def update_settings(self): 
        attrs = {"res":"Resolution","velo":"Velocity","acc":"Acceleration","bac":"Backlash"}
        for motor in [self.motor1, self.motor2, self.motor3]:
            for attr in attrs.keys():
                try:
                    setattr(motor, attr, eval(motor.fields[attrs[attr]].text()))
                except:
                    setattr(motor, attr, None)
         
    def _steps_to_angle_text(self, steps_text, motor):
        try:
            steps = float(steps_text)
            res = getattr(motor, "res", None)
            if res is None:
                res = float(motor.fields["Resolution"].text())
            if res <= 0:
                return "—"
            degrees = steps / res * 360.0
            # Keep enough digits for small d-pad moves (e.g. 10 steps at
            # 121728 steps/rev is 0.0296 deg, which used to round to 0).
            if abs(degrees) >= 100:
                return f"{degrees:.2f} degrees"
            if abs(degrees) >= 1:
                return f"{degrees:.4f} degrees"
            return f"{degrees:.6f} degrees"
        except (TypeError, ValueError, ZeroDivisionError):
            return "—"

    def update_dpad_angle_labels(self, *args):
        self.dpad.ud_angle_label.setText(self._steps_to_angle_text(self.dpad.ud_lineedit.text(), self.motor1))
        self.dpad.lr_angle_label.setText(self._steps_to_angle_text(self.dpad.lr_lineedit.text(), self.motor2))
        self.dpad.nf_angle_label.setText(self._steps_to_angle_text(self.dpad.nf_lineedit.text(), self.motor3))

    def refresh_serial_ports(self):
        """Populate COM port dropdown from currently attached serial devices."""
        current = self.esp32_port_combo.currentText()
        saved = getattr(self, "_saved_esp32_port", current)
        ports = [p.device for p in list_ports.comports()]
        self.esp32_port_combo.blockSignals(True)
        self.esp32_port_combo.clear()
        if ports:
            self.esp32_port_combo.addItems(ports)
        else:
            self.esp32_port_combo.addItem("COM3")
        prefer = current or saved or "COM3"
        idx = self.esp32_port_combo.findText(prefer)
        if idx >= 0:
            self.esp32_port_combo.setCurrentIndex(idx)
        self.esp32_port_combo.blockSignals(False)

    def auto_connect_esp32_serial(self):
        """Try connecting on startup if a matching port is present."""
        if self.esp32_port_combo.count() == 0:
            return
        port = self.esp32_port_combo.currentText()
        if port and self.connect_esp32_serial(port):
            self.esp32_connect_btn.setChecked(True)
            self.send_motor_settings_to_esp32()

    def toggle_esp32_serial(self, checked):
        if checked:
            port = self.esp32_port_combo.currentText().strip()
            if not self.connect_esp32_serial(port):
                self.esp32_connect_btn.setChecked(False)
            else:
                self.send_motor_settings_to_esp32()
        else:
            self.disconnect_esp32_serial()

    def connect_esp32_serial(self, port):
        """Open USB serial connection to the ESP32."""
        if not port:
            print("No serial port selected")
            return False
        self.disconnect_esp32_serial()
        try:
            self.esp32 = serial.Serial(
                port=port,
                baudrate=self.esp32_baud,
                timeout=0.3,
                write_timeout=1.0,
            )
            # USB-UART often resets the ESP32 on open; wait for boot + optional WiFi timeout.
            time.sleep(2.5)
            self.esp32.reset_input_buffer()

            got_ready = False
            for attempt in range(8):
                self.esp32.write(b"Hello\n")
                self.esp32.flush()
                deadline = time.time() + 1.0
                while time.time() < deadline:
                    line = self.esp32.readline().decode(errors="ignore").strip()
                    if not line:
                        continue
                    print(f"ESP32: {line}")
                    if line == "Hi" or line == "READY":
                        got_ready = True
                        break
                if got_ready:
                    break
                time.sleep(0.25)

            if not got_ready:
                print("ESP32 serial opened, but no Hello/READY response yet.")
                print("If dpad does nothing, reflash inoesp32.ino (WiFi no longer blocks serial).")
                self.esp32_status.setText(f"Port open? ({port})")
                self.esp32_status.setStyleSheet("color: #ffaa66;")
            else:
                print(f"ESP32 serial connected on {port}")
                self.esp32_status.setText(f"Connected ({port})")
                self.esp32_status.setStyleSheet("color: #66ff66;")

            self.esp32_connect_btn.setText("Disconnect")
            return True
        except serial.SerialException as e:
            print(f"ESP32 serial error: {e}")
            self.esp32 = None
            self.esp32_status.setText("Disconnected")
            self.esp32_status.setStyleSheet("color: #ff6666;")
            self.esp32_connect_btn.setText("Connect")
            return False

    def disconnect_esp32_serial(self):
        if self.esp32 is not None:
            try:
                if self.esp32.is_open:
                    self.esp32.close()
            except Exception:
                pass
            self.esp32 = None
            print("ESP32 serial disconnected")
        self.esp32_status.setText("Disconnected")
        self.esp32_status.setStyleSheet("color: #ff6666;")
        self.esp32_connect_btn.setText("Connect")
        self.esp32_connect_btn.setChecked(False)

    def send_esp32_command(self, command):
        """Send one newline-terminated command over USB serial."""
        if self.is_closing:
            return False
        if self.esp32 is None or not self.esp32.is_open:
            print("ESP32 serial not connected — click Connect on the Port controls")
            return False
        line = command.strip()
        if not line:
            print("Empty ESP32 command ignored")
            return False
        # Guard against empty step fields producing "move:1,B,"
        if line.startswith("move:"):
            parts = line[5:].split(",")
            if len(parts) != 3 or not parts[2].strip():
                print(f"Invalid move command (check U/D L/R N/F step fields): {line}")
                return False
            try:
                if int(float(parts[2])) < 1:
                    print(f"Step count must be >= 1: {line}")
                    return False
            except ValueError:
                print(f"Invalid step count: {line}")
                return False
        payload = (line + "\n").encode("utf-8")
        try:
            written = self.esp32.write(payload)
            self.esp32.flush()
            print(f"Serial TX ({written} bytes): {line}")
            return True
        except serial.SerialException as e:
            print(f"ESP32 serial write error: {e}")
            self.disconnect_esp32_serial()
            return False

    def schedule_motor_settings_send(self):
        """Coalesce rapid field edits into one settings burst."""
        self.settings_send_timer.start(250)
            
    def send_motor_settings_to_esp32(self):
        """Send motor settings to ESP32 over serial (call when settings change)"""
        motors_to_send = [
            (1, self.motor1, "degrees"),  # Motor 1 = Alt
            (2, self.motor2, "degrees"),  # Motor 2 = Azi
            (3, self.motor3, "mm"),       # Motor 3 = Focus
        ]
        
        for motor_num, motor, unit in motors_to_send:
            if getattr(motor, "res", None) is not None:
                if self.send_esp32_command(f"set_resolution:{motor_num},{motor.res}"):
                    print(f"Motor {motor_num} resolution -> {motor.res} {unit}")
            
            if getattr(motor, "velo", None) is not None:
                if self.send_esp32_command(f"set_velocity:{motor_num},{int(motor.velo)}"):
                    print(f"Motor {motor_num} velocity -> {int(motor.velo)} steps/sec")
            
            if getattr(motor, "acc", None) is not None:
                if self.send_esp32_command(f"set_acceleration:{motor_num},{motor.acc}"):
                    print(f"Motor {motor_num} acceleration -> {motor.acc} s")
            
            if getattr(motor, "bac", None) is not None:
                if self.send_esp32_command(f"set_backlash:{motor_num},{int(motor.bac)}"):
                    print(f"Motor {motor_num} backlash -> {int(motor.bac)} steps")

    def _log_move(self, name, steps_text, motor):
        try:
            steps = int(float(steps_text))
            res = getattr(motor, "res", None)
            if res:
                print(f"Moving {name}: {steps} steps ({steps / float(res):.6f} rev, res={res})")
            else:
                print(f"Moving {name}: {steps} steps")
        except (TypeError, ValueError):
            print(f"Moving {name}: {steps_text} steps")

    def _get_direction(self, motor, direction):
        """Get the actual direction to send to ESP32, accounting for inversion"""
        if motor.inverted:
            return 'B' if direction == 'F' else 'F'
        return direction

    def up_clicked(self):
        """Move Motor 1 (Alt) up"""
        steps = self.dpad.ud_lineedit.text()
        direction = self._get_direction(self.motor1, 'F')
        command = f"move:1,{direction},{steps}"
        self.send_esp32_command(command)
        self._log_move("Alt up", steps, self.motor1)

    def down_clicked(self):
        """Move Motor 1 (Alt) down"""
        steps = self.dpad.ud_lineedit.text()
        direction = self._get_direction(self.motor1, 'B')
        command = f"move:1,{direction},{steps}"
        self.send_esp32_command(command)
        self._log_move("Alt down", steps, self.motor1)

    def left_clicked(self):
        """Move Motor 2 (Azi) left"""
        steps = self.dpad.lr_lineedit.text()
        direction = self._get_direction(self.motor2, 'B')
        command = f"move:2,{direction},{steps}"
        self.send_esp32_command(command)
        self._log_move("Azi left", steps, self.motor2)

    def right_clicked(self):
        """Move Motor 2 (Azi) right"""
        steps = self.dpad.lr_lineedit.text()
        direction = self._get_direction(self.motor2, 'F')
        command = f"move:2,{direction},{steps}"
        self.send_esp32_command(command)
        self._log_move("Azi right", steps, self.motor2)

    def near_clicked(self):
        """Move Motor 3 (Focus) near"""
        steps = self.dpad.nf_lineedit.text()
        direction = self._get_direction(self.motor3, 'F')
        command = f"move:3,{direction},{steps}"
        self.send_esp32_command(command)
        self._log_move("Focus near", steps, self.motor3)

    def far_clicked(self):
        """Move Motor 3 (Focus) far"""
        steps = self.dpad.nf_lineedit.text()
        direction = self._get_direction(self.motor3, 'B')
        command = f"move:3,{direction},{steps}"
        self.send_esp32_command(command)
        self._log_move("Focus far", steps, self.motor3)

    def track_clicked(self):
        """Toggle star tracking on/off"""
        if self.dpad.track_button.isChecked():
            self.is_tracking = True
            self._reset_tracking_session()
            capture_interval = self._capture_interval_ms()
            print("=" * 60)
            print("STAR TRACKING STARTED")
            print(f"Motor update interval: {self.tracking_interval/1000:.1f} seconds")
            print(f"Stack/capture interval: {capture_interval/1000:.1f} seconds "
                  f"({1000.0/capture_interval:.2f} fps)")
            print(f"Max U/D steps (d-pad): {self.dpad.ud_lineedit.text()}")
            print(f"Max L/R steps (d-pad): {self.dpad.lr_lineedit.text()}")
            stacking = "ON" if self._stacking_enabled() else "OFF"
            print(f"Image stacking: {stacking}")
            if self._stacking_enabled():
                mode = self.dpad.stack_mode_combo.currentText()
                deep_space = self.dpad.deep_space_checkbox.isChecked()
                print(f"  Mode: {mode}")
                if deep_space:
                    print(f"  Deep Space: ENABLED (unlimited accumulation)")
                else:
                    print(f"  Deep Space: DISABLED (ring buffer, last {self.tracking_stack_max_frames} frames)")
            print("")
            print("PHASE 1: Analyzing trajectory (first 5 frames)")
            print("  - No motor corrections during analysis")
            print("  - Measuring star drift rate")
            print("")
            print("PHASE 2: Active tracking (after analysis)")
            print("  - Motor corrections will center the star in ROI")
            print("  - Drift compensation applied")
            print("")
            print("Right (cyan) ROI follows a second star for registration logging.")
            print("=" * 60)

            if not self.is_capturing:
                print("Starting continuous capture for tracking...")
                self.camera_controls.capture_mode_combobox.setCurrentText("Continuous")
                self.start_continuous_capture()
            else:
                self.capture_timer.start(capture_interval)
                print(f"Capture interval set to {capture_interval} ms for stacking")

            self.perform_tracking_update()
            self.tracking_timer.start(self.tracking_interval)
        else:
            self._stop_tracking_session()

    def _exposure_ms(self):
        try:
            return max(0.0, float(self.camera_controls.exposure_edit.text()) / 1000.0)
        except ValueError:
            return 10.0

    def _recommended_tracking_capture_interval_ms(self):
        """Exposure + time to centroid, shift-add, save ROI debug, and refresh the view."""
        processing_ms = 1500
        return int(max(2000, self._exposure_ms() + processing_ms))

    def _capture_interval_ms(self):
        if self.is_tracking:
            return self._recommended_tracking_capture_interval_ms()
        return self.live_capture_interval

    def _stacking_enabled(self):
        return bool(self.dpad.stack_checkbox.isChecked())

    def _analyze_trajectory(self):
        """Analyze the first 5 frames to calculate drift rate (pixels per second)"""
        if len(self.tracking_trajectory_buffer) < 2:
            self.tracking_drift_x = 0.0
            self.tracking_drift_y = 0.0
            return
        
        # Calculate drift using linear regression over time
        times = np.array([t for t, x, y in self.tracking_trajectory_buffer])
        x_positions = np.array([x for t, x, y in self.tracking_trajectory_buffer])
        y_positions = np.array([y for t, x, y in self.tracking_trajectory_buffer])
        
        # Normalize time to seconds from first frame
        times = times - times[0]
        
        # Linear fit: position = drift_rate * time + offset
        if len(times) > 1 and times[-1] > 0:
            # Calculate drift rate (slope of linear fit)
            x_drift = (x_positions[-1] - x_positions[0]) / times[-1] if times[-1] > 0 else 0.0
            y_drift = (y_positions[-1] - y_positions[0]) / times[-1] if times[-1] > 0 else 0.0
            
            self.tracking_drift_x = x_drift
            self.tracking_drift_y = y_drift
            
            print(f"  Analysis period: {times[-1]:.1f} seconds")
            print(f"  Total drift: X={x_positions[-1] - x_positions[0]:.1f}px, Y={y_positions[-1] - y_positions[0]:.1f}px")
        else:
            self.tracking_drift_x = 0.0
            self.tracking_drift_y = 0.0
    
    def _reset_tracking_session(self):
        self.tracking_ref_x = None
        self.tracking_ref_y = None
        self.tracking_stack_frames = []
        self.tracking_accumulator = None
        self.tracking_accumulator_count = 0
        self.tracking_weight_map = None
        self.tracking_batch_frames = []
        self.tracking_median_accumulator = None
        self.tracking_median_batch_count = 0
        self.tracking_stack_cached_image = None
        self.tracking_stack_display_counter = 0
        self._stack_computation_pending = False
        self._batch_median_pending = False
        self.tracking_ingested_id = -1
        self.tracking_frame_index = 0
        self.last_track_offset_x = None
        self.last_track_offset_y = None
        self.last_roi_width = None
        self.last_roi_height = None
        self.last_steps_x = 0
        self.last_steps_y = 0
        self.tracking_motor_frame_id = -1
        self.tracking_ref_angle = None
        self.last_stack_angle_deg = 0.0
        
        # Trajectory analysis for first 5 frames
        self.tracking_trajectory_buffer = []  # Store (timestamp, x, y) tuples
        self.tracking_drift_x = 0.0  # pixels per second drift in X
        self.tracking_drift_y = 0.0  # pixels per second drift in Y
        self.tracking_analysis_complete = False
        
        if self.latest_frame is None and getattr(self.imgplot, "image_data", None) is not None:
            self.latest_frame = np.array(self.imgplot.image_data, copy=True)
        self._start_tracking_debug_session()

    def _stop_tracking_session(self):
        self.is_tracking = False
        self.tracking_timer.stop()
        self._save_final_tracking_stack()
        self.tracking_ref_x = None
        self.tracking_ref_y = None
        self.tracking_stack_frames = []
        self.tracking_accumulator = None
        self.tracking_accumulator_count = 0
        self.tracking_weight_map = None
        self.tracking_batch_frames = []
        self.tracking_median_accumulator = None
        self.tracking_median_batch_count = 0
        self.tracking_stack_cached_image = None
        self._stack_computation_pending = False
        self._batch_median_pending = False
        self.last_track_offset_x = None
        self.last_track_offset_y = None
        self.imgplot.update_star_crosshair(0, 0, visible=False)
        self.imgplot.update_star2_crosshair(0, 0, visible=False)
        if self.is_capturing:
            self.capture_timer.start(self.live_capture_interval)
        if self.latest_frame is not None:
            self._show_image_array(self.latest_frame)
        print("=" * 60)
        print("STAR TRACKING STOPPED")
        print("=" * 60)

    def _start_tracking_debug_session(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracking_debug")
        self.tracking_debug_dir = os.path.join(base_dir, stamp)
        os.makedirs(self.tracking_debug_dir, exist_ok=True)
        self.tracking_csv_path = os.path.join(self.tracking_debug_dir, "tracking_log.csv")
        print(f"Tracking debug folder: {self.tracking_debug_dir}")

    def _save_final_tracking_stack(self):
        if not self.tracking_debug_dir:
            return
        if not self.tracking_stack_frames and self.tracking_accumulator is None and self.tracking_median_accumulator is None:
            return
        
        mode = self.dpad.stack_mode_combo.currentText()
        
        # For final save, compute directly (not async) to ensure we save the actual result
        if mode == "Mean":
            stacked = self._stack_mean_uint8()
        elif mode == "Median":
            stacked = self._stack_median_uint8()
        elif mode == "Sigma-clip":
            stacked = self._stack_sigma_clip_uint8()
        elif mode == "Mean-of-Medians":
            stacked = self._stack_mean_of_medians_uint8()
        else:
            stacked = self._stack_mean_uint8()
        
        if stacked is None:
            return
        
        path = os.path.join(self.tracking_debug_dir, f"stack_{mode.lower().replace('-', '_')}.png")
        
        # Determine frame count for save message
        if mode == "Mean-of-Medians" and self.tracking_median_batch_count > 0:
            total_frames = self.tracking_median_batch_count * self.tracking_batch_size + len(self.tracking_batch_frames)
            count_msg = f"{self.tracking_median_batch_count} batches ({total_frames} total frames)"
        elif mode == "Mean" and self.dpad.deep_space_checkbox.isChecked() and self.tracking_accumulator_count > 0:
            frame_count = self.tracking_accumulator_count
            count_msg = f"{frame_count} total frames"
        else:
            frame_count = len(self.tracking_stack_frames)
            count_msg = f"{frame_count} frames (ring buffer)"
        
        try:
            imageio.imwrite(path, stacked)
            print(f"Saved stacked image ({count_msg}, {mode}): {path}")
        except Exception as e:
            print(f"Could not save stacked image: {e}")

    def _get_stacked_image(self, force_compute=False):
        """Get stacked image using the selected mode.
        
        For expensive modes (median, sigma-clip), only recompute every Nth frame
        to avoid GUI freezing. Use cached result in between.
        """
        if not self.tracking_stack_frames and self.tracking_median_accumulator is None:
            return None
        
        mode = self.dpad.stack_mode_combo.currentText()
        
        # Mean and Mean-of-Medians are fast, always compute on main thread
        if mode == "Mean":
            return self._stack_mean_uint8()
        elif mode == "Mean-of-Medians":
            return self._stack_mean_of_medians_uint8()
        
        # For expensive modes, use background worker with caching
        self.tracking_stack_display_counter += 1
        should_update = (
            force_compute or 
            self.tracking_stack_cached_image is None or
            self.tracking_stack_display_counter >= self.tracking_stack_display_interval
        )
        
        if should_update and not self._stack_computation_pending:
            self.tracking_stack_display_counter = 0
            self._stack_computation_pending = True
            # Send copy of frame list to worker thread
            frames_copy = [f.copy() for f in self.tracking_stack_frames]
            self._request_stack.emit(frames_copy, mode)
            # Will be updated via _on_stack_ready callback
        
        # Return cached result or fallback to mean
        return self.tracking_stack_cached_image if self.tracking_stack_cached_image is not None else self._stack_mean_uint8()
    
    def _on_stack_ready(self, stacked_image):
        """Called when background stack computation completes."""
        self._stack_computation_pending = False
        if stacked_image is not None:
            self.tracking_stack_cached_image = stacked_image
            mode = self.dpad.stack_mode_combo.currentText()
            print(f"  [{mode}] Updated stack display ({len(self.tracking_stack_frames)} frames)")
            # Refresh the stacked view ONLY if that tab is visible (saves bandwidth on remote desktop)
            if self.is_tracking and self._stacking_enabled() and self.cam1_tabs.currentIndex() == 1:
                self._show_image_array(stacked_image, plot=self.imgplot_stacked)
    
    def _on_batch_median_ready(self, batch_median):
        """Called when background batch median computation completes."""
        self._batch_median_pending = False
        if batch_median is not None:
            # Add to median accumulator
            if self.tracking_median_accumulator is None:
                self.tracking_median_accumulator = batch_median
                self.tracking_median_batch_count = 1
            else:
                self.tracking_median_accumulator += batch_median
                self.tracking_median_batch_count += 1
            
            print(f"  Batch {self.tracking_median_batch_count} completed: median accumulated")
            print(f"  Total: {self.tracking_median_batch_count * self.tracking_batch_size} frames processed")
            
            # Update stacked view if visible
            if self.cam1_tabs.currentIndex() == 1:
                stacked = self._get_stacked_image()
                if stacked is not None:
                    self._show_image_array(stacked, plot=self.imgplot_stacked)

    def _stack_mean_uint8(self):
        """Compute mean of all frames with proper weighting for rotated frames.
        
        Uses accumulator + weight map if deep space mode is enabled (unlimited frames),
        otherwise uses ring buffer (last 100 frames).
        """
        # Deep space mode: use accumulator with weight map (all frames)
        if self.dpad.deep_space_checkbox.isChecked() and self.tracking_accumulator is not None:
            if self.tracking_accumulator_count <= 0:
                return None
            
            # Use weight map if available (handles rotation edge effects)
            if self.tracking_weight_map is not None:
                # Avoid divide by zero - set minimum weight to 1
                safe_weights = np.maximum(self.tracking_weight_map, 1.0)
                mean = self.tracking_accumulator / safe_weights
            else:
                # Fallback to uniform weighting
                mean = self.tracking_accumulator / float(self.tracking_accumulator_count)
            
            return np.clip(mean, 0, 255).astype(np.uint8)
        
        # Regular mode: use ring buffer (recent frames only)
        if not self.tracking_stack_frames:
            return None
        stack = np.array(self.tracking_stack_frames, dtype=np.float32)
        mean = np.mean(stack, axis=0)
        return np.clip(mean, 0, 255).astype(np.uint8)
    
    def _stack_mean_of_medians_uint8(self):
        """Compute mean of batch medians (best for deep space with outlier rejection)."""
        if self.tracking_median_accumulator is None or self.tracking_median_batch_count <= 0:
            return None
        mean_of_medians = self.tracking_median_accumulator / float(self.tracking_median_batch_count)
        return np.clip(mean_of_medians, 0, 255).astype(np.uint8)
    
    def _stack_median_uint8(self):
        """Compute median of all frames in buffer."""
        if not self.tracking_stack_frames:
            return None
        stack = np.array(self.tracking_stack_frames, dtype=np.uint8)
        median = np.median(stack, axis=0)
        return median.astype(np.uint8)
    
    def _stack_sigma_clip_uint8(self, sigma=3.0):
        """Compute mean after sigma-clipping outliers."""
        if not self.tracking_stack_frames:
            return None
        if len(self.tracking_stack_frames) < 3:
            # Not enough frames for meaningful sigma clipping
            return self._stack_mean_uint8()
        
        stack = np.array(self.tracking_stack_frames, dtype=np.float32)
        mean = np.mean(stack, axis=0)
        std = np.std(stack, axis=0)
        
        # Mask outliers beyond sigma threshold
        lower_bound = mean - sigma * std
        upper_bound = mean + sigma * std
        
        # Create mask for each frame
        mask = (stack >= lower_bound[np.newaxis, :, :]) & (stack <= upper_bound[np.newaxis, :, :])
        
        # Compute masked mean (use mean value where all pixels rejected)
        masked_stack = np.where(mask, stack, np.nan)
        with np.errstate(invalid='ignore'):
            result = np.nanmean(masked_stack, axis=0)
        result = np.where(np.isnan(result), mean, result)
        
        return np.clip(result, 0, 255).astype(np.uint8)
    
    def _get_total_frame_count(self):
        """Get total frame count based on current stacking mode."""
        mode = self.dpad.stack_mode_combo.currentText()
        
        if mode == "Mean-of-Medians":
            # Count completed batches + frames in current batch
            return self.tracking_median_batch_count * self.tracking_batch_size + len(self.tracking_batch_frames)
        elif mode == "Mean" and self.dpad.deep_space_checkbox.isChecked():
            # Deep space mean uses accumulator count
            return self.tracking_accumulator_count
        else:
            # Other modes use ring buffer
            return len(self.tracking_stack_frames)

    def _show_image_array(self, image_np, plot=None):
        if image_np is None:
            return
        plot = plot or self.imgplot
        plot.image_data = image_np
        if len(image_np.shape) == 3:
            self.apply_color_correction(plot)
        else:
            plot.image_item.setImage(image_np)
        plot.update_pixel_info()
        plot.update_projections()  # Update the projection plots
        if plot is self.imgplot:
            if not hasattr(self, "rois_initialized"):
                self.resize_rois(image_np)
                self.rois_initialized = True

    def _show_camera2_array(self, image_np):
        if image_np is None:
            return
        image_np = np.rot90(image_np, k=-1)
        self._show_image_array(image_np, plot=self.imgplot2)

    def _raw_tracking_frame(self):
        if self.latest_frame is not None:
            return self.latest_frame
        return getattr(self.imgplot, "image_data", None)

    def _extract_star_in_roi(self, image_data, roi_item=None, label="ROI1"):
        """Return star/ROI measurements from a raw frame, or None if no valid star.

        image_data is pyqtgraph col-major: indexed [x, y], matching ImageItem plot axes.
        """
        if roi_item is None:
            roi_item = self.imgplot.ROI1
        roi_slice, _roi_transform = roi_item.getArraySlice(image_data, self.imgplot.image_item)
        if roi_slice is None:
            print(f"{label} is outside image bounds")
            return None

        roi_img = image_data[roi_slice]
        if roi_img.size == 0:
            print(f"{label} is outside image bounds")
            return None

        x0 = roi_slice[0].start if isinstance(roi_slice[0], slice) and roi_slice[0].start is not None else 0
        y0 = roi_slice[1].start if isinstance(roi_slice[1], slice) and roi_slice[1].start is not None else 0

        if len(roi_img.shape) == 3:
            gray = np.dot(roi_img[..., :3], [0.299, 0.587, 0.114])
        else:
            gray = roi_img.astype(np.float32, copy=False)

        # Smooth so a single hot pixel cannot beat a real star, then lock
        # the centroid to a window around the brightest peak.
        smooth = gaussian_filter(np.asarray(gray, dtype=np.float32), sigma=1.0)
        peak_x, peak_y = np.unravel_index(np.argmax(smooth), smooth.shape)
        peak_val = float(smooth[peak_x, peak_y])
        print(f"  {label} peak brightness: {peak_val:.0f} at local ({peak_x}, {peak_y})")

        radius = 12
        x_lo = max(0, int(peak_x) - radius)
        x_hi = min(gray.shape[0], int(peak_x) + radius + 1)
        y_lo = max(0, int(peak_y) - radius)
        y_hi = min(gray.shape[1], int(peak_y) + radius + 1)
        patch = np.asarray(gray[x_lo:x_hi, y_lo:y_hi], dtype=np.float32)
        threshold = peak_val * 0.5
        bright_mask = patch >= threshold
        if not np.any(bright_mask):
            print(f"  {label}: no bright object found (all pixels below threshold)")
            return None

        xs, ys = np.where(bright_mask)
        weights = patch[bright_mask]
        diameter = max(int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1))
        if diameter < 3 or int(np.sum(bright_mask)) < 5:
            print(f"  {label}: object too small ({diameter} pixels), likely noise. Need at least 5 pixels.")
            return None

        star_x = x_lo + np.average(xs, weights=weights)
        star_y = y_lo + np.average(ys, weights=weights)
        roi_width, roi_height = gray.shape[0], gray.shape[1]
        star_x_img = x0 + star_x
        star_y_img = y0 + star_y
        num_bright_pixels = int(np.sum(bright_mask))

        print(f"  {label}: {num_bright_pixels} bright pixels (diameter: {diameter}px)")
        print(f"  {label} origin: ({x0}, {y0}), size: ({roi_width}, {roi_height})")
        print(f"  {label} star centroid image: ({star_x_img:.1f}, {star_y_img:.1f})")

        return {
            "roi_img": roi_img,
            "roi_x": x0,
            "roi_y": y0,
            "roi_width": roi_width,
            "roi_height": roi_height,
            "star_x": star_x,
            "star_y": star_y,
            "star_x_img": star_x_img,
            "star_y_img": star_y_img,
        }

    def _follow_star_with_roi2(self, frame):
        """Keep ROI2 centered on its brightest star and return registration fields."""
        star = self._extract_star_in_roi(frame, roi_item=self.imgplot.ROI2, label="ROI2")
        if star is None:
            return None

        size = self.imgplot.ROI2.size()
        width, height = float(size[0]), float(size[1])
        new_x = star["star_x_img"] - width / 2.0
        new_y = star["star_y_img"] - height / 2.0
        img_w, img_h = frame.shape[0], frame.shape[1]
        new_x = float(np.clip(new_x, 0.0, max(0.0, img_w - width)))
        new_y = float(np.clip(new_y, 0.0, max(0.0, img_h - height)))

        self.imgplot.ROI2.blockSignals(True)
        self.imgplot.ROI2.setPos([new_x, new_y])
        self.imgplot.ROI2.blockSignals(False)
        self.imgplot.update_roi_images()
        # Crosshair disabled for cleaner view
        # self.imgplot.update_star2_crosshair(star["star_x_img"], star["star_y_img"], visible=True)

        center_x = new_x + width / 2.0
        center_y = new_y + height / 2.0
        print(f"  ROI2 recentered to ({new_x:.1f}, {new_y:.1f}); "
              f"center=({center_x:.1f}, {center_y:.1f})")
        return {
            "roi2_x": new_x,
            "roi2_y": new_y,
            "roi2_width": width,
            "roi2_height": height,
            "roi2_center_x": center_x,
            "roi2_center_y": center_y,
            "star2_x": float(star["star_x_img"]),
            "star2_y": float(star["star_y_img"]),
        }

    def _align_frame_to_lock(self, frame, offset_x, offset_y):
        """Shift a raw frame so the ROI1 star lands on the ROI center."""
        return _shift_frame_to_lock(frame, offset_x, offset_y)

    def _rotate_around_point(self, frame, cx, cy, angle_rad):
        """Rotate image content counterclockwise around (cx, cy) in [x, y] axes."""
        return _rotate_frame_around_point(frame, cx, cy, angle_rad)

    def _stack_rotation_delta(self, star, roi2):
        """Angle to rotate so the current ROI1→ROI2 vector matches the first frame."""
        self.last_stack_angle_deg = 0.0
        if roi2 is None:
            return 0.0
        dx = float(roi2["star2_x"] - star["star_x_img"])
        dy = float(roi2["star2_y"] - star["star_y_img"])
        separation = float(np.hypot(dx, dy))
        if separation < 5.0:
            print(f"  ROI1→ROI2 baseline too short ({separation:.1f}px); skip rotation")
            return 0.0
        angle = float(np.arctan2(dy, dx))
        if self.tracking_ref_angle is None:
            self.tracking_ref_angle = angle
            print(f"  Stack rotation reference angle: {np.degrees(angle):.3f} deg")
            return 0.0
        delta = self.tracking_ref_angle - angle
        delta = (delta + np.pi) % (2.0 * np.pi) - np.pi
        self.last_stack_angle_deg = float(np.degrees(delta))
        return delta

    def _align_frame_for_stack(self, frame, star, offset_x, offset_y, roi2):
        """Rotate around the ROI1 star using ROI2's angle, then shift to ROI1 center."""
        delta = self._stack_rotation_delta(star, roi2)
        aligned = frame
        if abs(delta) >= 1e-6:
            aligned = self._rotate_around_point(
                aligned, star["star_x_img"], star["star_y_img"], delta
            )
            print(f"  Rotated {self.last_stack_angle_deg:.3f} deg around ROI1 star "
                  f"({star['star_x_img']:.1f}, {star['star_y_img']:.1f})")
        return self._align_frame_to_lock(aligned, offset_x, offset_y)

    def _save_tracking_debug(self, star, offset_x, offset_y, is_lock, roi2=None):
        if not self.tracking_debug_dir:
            return
        frame_i = self.tracking_frame_index
        roi_name = f"roi_{frame_i:04d}.png"
        roi_path = os.path.join(self.tracking_debug_dir, roi_name)
        meta_path = os.path.join(self.tracking_debug_dir, f"roi_{frame_i:04d}.json")
        roi_img = star["roi_img"]
        save_img = roi_img
        if save_img.dtype != np.uint8:
            finite = np.asarray(save_img, dtype=np.float32)
            lo, hi = np.min(finite), np.max(finite)
            if hi > lo:
                save_img = np.clip(255.0 * (finite - lo) / (hi - lo), 0, 255).astype(np.uint8)
            else:
                save_img = np.zeros(finite.shape, dtype=np.uint8)
        try:
            imageio.imwrite(roi_path, save_img)
        except Exception as e:
            print(f"  Could not save ROI image: {e}")
            roi_name = ""

        meta = {
            "frame": frame_i,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "is_lock_frame": is_lock,
            "centroid_x": float(star["star_x_img"]),
            "centroid_y": float(star["star_y_img"]),
            "centroid_x_roi": float(star["star_x"]),
            "centroid_y_roi": float(star["star_y"]),
            "ref_x": None if self.tracking_ref_x is None else float(self.tracking_ref_x),
            "ref_y": None if self.tracking_ref_y is None else float(self.tracking_ref_y),
            "roi_center_x": float(star["roi_width"]) / 2.0,
            "roi_center_y": float(star["roi_height"]) / 2.0,
            "offset_x": float(offset_x),
            "offset_y": float(offset_y),
            "roi_x": int(star["roi_x"]),
            "roi_y": int(star["roi_y"]),
            "roi_width": int(star["roi_width"]),
            "roi_height": int(star["roi_height"]),
            "stack_buffer_count": len(self.tracking_stack_frames),
            "stack_total_count": self._get_total_frame_count(),
            "stack_median_batches": self.tracking_median_batch_count if self.dpad.stack_mode_combo.currentText() == "Mean-of-Medians" else 0,
            "stacking_enabled": self._stacking_enabled(),
            "steps_x": int(self.last_steps_x),
            "steps_y": int(self.last_steps_y),
            "roi2_x": None if roi2 is None else float(roi2["roi2_x"]),
            "roi2_y": None if roi2 is None else float(roi2["roi2_y"]),
            "roi2_width": None if roi2 is None else float(roi2["roi2_width"]),
            "roi2_height": None if roi2 is None else float(roi2["roi2_height"]),
            "roi2_center_x": None if roi2 is None else float(roi2["roi2_center_x"]),
            "roi2_center_y": None if roi2 is None else float(roi2["roi2_center_y"]),
            "star2_x": None if roi2 is None else float(roi2["star2_x"]),
            "star2_y": None if roi2 is None else float(roi2["star2_y"]),
            "rel_x": None if roi2 is None else float(roi2["star2_x"] - star["star_x_img"]),
            "rel_y": None if roi2 is None else float(roi2["star2_y"] - star["star_y_img"]),
            "stack_angle_deg": float(self.last_stack_angle_deg),
            "stack_ref_angle_deg": (
                None if self.tracking_ref_angle is None
                else float(np.degrees(self.tracking_ref_angle))
            ),
            "roi_file": roi_name,
        }
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception as e:
            print(f"  Could not save ROI metadata: {e}")

        fieldnames = list(meta.keys())
        write_header = not os.path.exists(self.tracking_csv_path) or os.path.getsize(self.tracking_csv_path) == 0
        try:
            with open(self.tracking_csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                writer.writerow(meta)
        except Exception as e:
            print(f"  Could not append tracking CSV: {e}")

        if is_lock:
            lock_path = os.path.join(self.tracking_debug_dir, "lock.json")
            try:
                with open(lock_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
            except Exception as e:
                print(f"  Could not save lock.json: {e}")

        print(f"  Saved debug ROI: {roi_path}")

    def _ingest_tracking_frame(self, frame):
        """Centroid the raw frame vs the first lock; optionally align-and-stack."""
        if frame is None:
            print("No image available for tracking")
            return None
        if self.tracking_ingested_id == self.latest_frame_id:
            if self._stacking_enabled():
                return self._get_stacked_image()
            return frame

        try:
            star = self._extract_star_in_roi(frame)
            if star is None:
                if self._stacking_enabled():
                    return self._get_stacked_image()
                return None

            is_lock = self.tracking_ref_x is None or self.tracking_ref_y is None
            if is_lock:
                self.tracking_ref_x = star["star_x_img"]
                self.tracking_ref_y = star["star_y_img"]
                print(f"  Crosshair lock: X={self.tracking_ref_x:.1f}, Y={self.tracking_ref_y:.1f}")

            # Collect trajectory data for first 5 frames
            if not self.tracking_analysis_complete:
                timestamp = time.time()
                self.tracking_trajectory_buffer.append((timestamp, star["star_x_img"], star["star_y_img"]))
                
                if len(self.tracking_trajectory_buffer) >= 5:
                    self._analyze_trajectory()
                    self.tracking_analysis_complete = True
                    print("=" * 60)
                    print("TRAJECTORY ANALYSIS COMPLETE")
                    print(f"Drift rate: X={self.tracking_drift_x:.3f} px/s, Y={self.tracking_drift_y:.3f} px/s")
                    print("Beginning active tracking corrections...")
                    print("=" * 60)
                else:
                    print(f"\n{'='*50}")
                    print(f"TRAJECTORY ANALYSIS: Frame {len(self.tracking_trajectory_buffer)}/5")
                    print(f"  Star position: ({star['star_x_img']:.1f}, {star['star_y_img']:.1f})")
                    # Crosshair disabled for cleaner view
                    # self.imgplot.update_star_crosshair(star["star_x_img"], star["star_y_img"], visible=True)
                    self.tracking_ingested_id = self.latest_frame_id
                    return frame  # Don't process further during analysis phase

            # Drive the locked star toward the geometric center of the ROI.
            center_x = star["roi_width"] / 2.0
            center_y = star["roi_height"] / 2.0
            offset_x = star["star_x"] - center_x  # + = right of center
            offset_y = star["star_y"] - center_y  # + = above center (plot y)

            print(f"\n{'='*50}")
            print("TRACKING UPDATE")
            print(f"  ROI center: ({center_x:.1f}, {center_y:.1f})")
            print(f"  Offset from ROI center: X={offset_x:.1f}px, Y={offset_y:.1f}px")

            self.last_track_offset_x = offset_x
            self.last_track_offset_y = offset_y
            self.last_roi_width = star["roi_width"]
            self.last_roi_height = star["roi_height"]
            self.last_steps_x, self.last_steps_y = self._compute_tracking_steps(
                offset_x, offset_y, star["roi_width"], star["roi_height"]
            )

            roi2 = self._follow_star_with_roi2(frame)
            if roi2 is not None:
                print(f"  Relative star2-star1: dx={roi2['star2_x'] - star['star_x_img']:.1f}px, "
                      f"dy={roi2['star2_y'] - star['star_y_img']:.1f}px")

            if self._stacking_enabled():
                delta = self._stack_rotation_delta(star, roi2)
                if abs(delta) >= 1e-6:
                    print(f"  Rotated {self.last_stack_angle_deg:.3f} deg around ROI1 star "
                          f"({star['star_x_img']:.1f}, {star['star_y_img']:.1f})")
                
                # Get current stack mean as reference for cross-correlation refinement
                reference = self._get_stacked_image() if len(self.tracking_stack_frames) > 0 else None
                
                self._request_align.emit({
                    "frame": np.array(frame, copy=True),
                    "cx": float(star["star_x_img"]),
                    "cy": float(star["star_y_img"]),
                    "delta": float(delta),
                    "offset_x": float(offset_x),
                    "offset_y": float(offset_y),
                    "reference": reference,  # Pass stack mean for cross-correlation refinement
                })

            self.tracking_ingested_id = self.latest_frame_id
            self._save_tracking_debug(star, offset_x, offset_y, is_lock, roi2=roi2)
            self.tracking_frame_index += 1

            # Crosshair disabled for cleaner view
            # self.imgplot.update_star_crosshair(star["star_x_img"], star["star_y_img"], visible=True)
            if self._stacking_enabled():
                return self._get_stacked_image()
            return frame
        except Exception as e:
            print(f"Tracking error: {e}")
            if self._stacking_enabled():
                return self._get_stacked_image()
            return None

    def _compute_tracking_steps(self, offset_x, offset_y, roi_width, roi_height):
        """Map pixel error from the ROI center into motor steps.

        Scaling calibration (measured):
        - Vertical (altitude): 26 steps to traverse full ROI height
        - Horizontal (azimuth): 900 steps to traverse full ROI width
        
        This computes proportional correction steps based on pixel offset.
        """
        try:
            max_ud_steps = int(float(self.dpad.ud_lineedit.text()))
            max_lr_steps = int(float(self.dpad.lr_lineedit.text()))
        except ValueError:
            print("  Error: Invalid step size in U/D or L/R fields")
            return 0, 0

        if roi_width < 2 or roi_height < 2 or max_ud_steps < 1 or max_lr_steps < 1:
            return 0, 0

        # Calibrated scaling: steps needed to traverse full ROI
        VERTICAL_STEPS_PER_ROI = 26.0
        HORIZONTAL_STEPS_PER_ROI = 900.0

        # Calculate steps per pixel
        steps_per_px_y = VERTICAL_STEPS_PER_ROI / roi_height
        steps_per_px_x = HORIZONTAL_STEPS_PER_ROI / roi_width

        # Apply deadband (ignore small jitter)
        if abs(offset_x) <= self.tracking_pixel_deadband:
            steps_x = 0
        else:
            steps_x = int(round(offset_x * steps_per_px_x))
            # Clamp to max steps
            steps_x = max(min(steps_x, max_lr_steps), -max_lr_steps)
            # Ensure at least 1 step if offset exceeds deadband
            if steps_x == 0:
                steps_x = 1 if offset_x > 0 else -1

        if abs(offset_y) <= self.tracking_pixel_deadband:
            steps_y = 0
        else:
            steps_y = int(round(offset_y * steps_per_px_y))
            # Clamp to max steps
            steps_y = max(min(steps_y, max_ud_steps), -max_ud_steps)
            # Ensure at least 1 step if offset exceeds deadband
            if steps_y == 0:
                steps_y = 1 if offset_y > 0 else -1

        return steps_x, steps_y

    def _issue_tracking_motor_correction(self):
        """Issue motor corrections to center the star, accounting for drift"""
        if self.last_track_offset_x is None:
            return
        if self.tracking_motor_frame_id == self.tracking_ingested_id:
            return
        
        # Don't issue corrections during trajectory analysis phase
        if not self.tracking_analysis_complete:
            print(f"  Analyzing trajectory... no motor corrections yet")
            return
        
        self.tracking_motor_frame_id = self.tracking_ingested_id

        steps_x = int(self.last_steps_x)
        steps_y = int(self.last_steps_y)

        # DEBUG: Print the logic so we can verify it
        print(f"\n  DEBUG TRACKING CORRECTION:")
        print(f"    Offset X: {self.last_track_offset_x:.1f}px (+ = star RIGHT of center)")
        print(f"    Offset Y: {self.last_track_offset_y:.1f}px (+ = star TOP/ABOVE center)")
        print(f"    Steps  X: {steps_x} (sign matches offset)")
        print(f"    Steps  Y: {steps_y} (sign matches offset)")
        
        # Tracking correction logic (does NOT use invert checkboxes):
        # Based on manual D-pad observations:
        # - DOWN button sends move:1,B,10 → moves star DOWN
        # - RIGHT button sends move:2,B,10 → moves star RIGHT
        # Therefore:
        #   Motor 1: 'B' = DOWN, 'F' = UP
        #   Motor 2: 'B' = RIGHT, 'F' = LEFT
        #
        # To center the star, move it opposite to its offset:
        # - Star at TOP (positive offset_y) → need to move DOWN → send 'B'
        # - Star at BOTTOM (negative offset_y) → need to move UP → send 'F'
        # - Star at RIGHT (positive offset_x) → need to move LEFT → send 'F'
        # - Star at LEFT (negative offset_x) → need to move RIGHT → send 'B'
        
        if steps_y != 0:
            direction_ud = "B" if steps_y > 0 else "F"  # B=DOWN, F=UP
            move_name = "DOWN" if direction_ud == "B" else "UP"
            print(f"    Y Correction: Send '{direction_ud}' to Motor 1 → moves star {move_name}")
            command = f"move:1,{direction_ud},{abs(steps_y)}"
            print(f"  Altitude correction: {abs(steps_y)} steps {move_name}")
            self.send_esp32_command(command)
        else:
            print(f"  Altitude: on ROI center")

        if steps_x != 0:
            # FIX: Flip the logic - negative offset needs B (RIGHT), positive needs F (LEFT)
            direction_lr = "B" if steps_x < 0 else "F"  # B=RIGHT (for negative/LEFT offset), F=LEFT (for positive/RIGHT offset)
            move_name = "RIGHT" if direction_lr == "B" else "LEFT"
            print(f"    X Correction: Send '{direction_lr}' to Motor 2 → moves star {move_name}")
            command = f"move:2,{direction_lr},{abs(steps_x)}"
            print(f"  Azimuth correction: {abs(steps_x)} steps {move_name}")
            self.send_esp32_command(command)
        else:
            print(f"  Azimuth: on ROI center")

    def _display_tracking_result(self, frame, result):
        """Update only the currently visible tab to reduce remote desktop bandwidth.
        
        Live view (tab 0) shows the raw camera frame.
        Stacked view (tab 1) shows the accumulated stack result.
        """
        # Only update the currently visible tab to save bandwidth/performance
        current_tab = self.cam1_tabs.currentIndex()
        
        if current_tab == 0:
            # Live tab is visible - update with raw frame
            if frame is not None:
                self._show_image_array(frame, plot=self.imgplot)
        else:
            # Stacked tab is visible - update with stack result
            if self._stacking_enabled() and result is not None:
                self._show_image_array(result, plot=self.imgplot_stacked)

    def perform_tracking_update(self):
        """Centroid the latest raw frame and issue correction commands."""
        if not self.is_tracking:
            return
        frame = self._raw_tracking_frame()
        result = self._ingest_tracking_frame(frame)
        self._display_tracking_result(frame, result)
        self._issue_tracking_motor_correction()

    def _camera_list(self):
        cams = []
        if getattr(self, "cam", None) is not None:
            cams.append(self.cam)
        if getattr(self, "cam2", None) is not None:
            cams.append(self.cam2)
        return cams

    def _camera_display_name(self, cam):
        try:
            nodemap = cam.GetTLDeviceNodeMap()
            model = PySpin.CStringPtr(nodemap.GetNode("DeviceModelName"))
            serial = PySpin.CStringPtr(nodemap.GetNode("DeviceSerialNumber"))
            parts = []
            if PySpin.IsReadable(model):
                parts.append(model.GetValue())
            if PySpin.IsReadable(serial):
                parts.append(serial.GetValue())
            return " ".join(parts) if parts else "FLIR"
        except Exception:
            return "FLIR"

    def _configure_flir_camera(self, cam, label):
        """Stream and exposure-friendly defaults used at connect time."""
        try:
            nodemap = cam.GetNodeMap()
            s_nodemap = cam.GetTLStreamNodeMap()
            try:
                stream_buffer_count_mode = PySpin.CEnumerationPtr(s_nodemap.GetNode('StreamBufferCountMode'))
                if PySpin.IsAvailable(stream_buffer_count_mode) and PySpin.IsWritable(stream_buffer_count_mode):
                    stream_buffer_count_mode.SetIntValue(stream_buffer_count_mode.GetEntryByName('Manual').GetValue())
                    print(f"{label}: stream buffer count mode set to Manual")

                stream_buffer_count = PySpin.CIntegerPtr(s_nodemap.GetNode('StreamBufferCountManual'))
                if PySpin.IsAvailable(stream_buffer_count) and PySpin.IsWritable(stream_buffer_count):
                    stream_buffer_count.SetValue(10)
                    print(f"{label}: stream buffer count set to 10")

                stream_buffer_handling = PySpin.CEnumerationPtr(s_nodemap.GetNode('StreamBufferHandlingMode'))
                if PySpin.IsAvailable(stream_buffer_handling) and PySpin.IsWritable(stream_buffer_handling):
                    stream_buffer_handling.SetIntValue(stream_buffer_handling.GetEntryByName('NewestOnly').GetValue())
                    print(f"{label}: stream buffer handling mode set to NewestOnly")
            except Exception as stream_error:
                print(f"{label}: could not configure stream settings: {stream_error}")

            try:
                frame_rate_enable = PySpin.CBooleanPtr(nodemap.GetNode('AcquisitionFrameRateEnable'))
                if PySpin.IsAvailable(frame_rate_enable) and PySpin.IsWritable(frame_rate_enable):
                    frame_rate_enable.SetValue(False)
                    print(f"{label}: frame rate control disabled - long exposures enabled")
            except Exception:
                try:
                    frame_rate_auto = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionFrameRateAuto'))
                    if PySpin.IsAvailable(frame_rate_auto) and PySpin.IsWritable(frame_rate_auto):
                        frame_rate_auto.SetIntValue(frame_rate_auto.GetEntryByName('Off').GetValue())
                        print(f"{label}: frame rate auto set to Off - long exposures enabled")
                except Exception:
                    print(f"{label}: could not disable frame rate control (may not be available)")

            try:
                frame_rate = PySpin.CFloatPtr(nodemap.GetNode('AcquisitionFrameRate'))
                if PySpin.IsAvailable(frame_rate) and PySpin.IsWritable(frame_rate):
                    frame_rate_min = frame_rate.GetMin()
                    frame_rate.SetValue(frame_rate_min)
                    print(f"{label}: frame rate set to minimum: {frame_rate_min} fps")
            except Exception as fr_error:
                print(f"{label}: could not set frame rate: {fr_error}")

            try:
                trigger_mode = PySpin.CEnumerationPtr(nodemap.GetNode('TriggerMode'))
                if PySpin.IsAvailable(trigger_mode) and PySpin.IsWritable(trigger_mode):
                    trigger_mode.SetIntValue(trigger_mode.GetEntryByName('Off').GetValue())
                    print(f"{label}: trigger mode disabled")
            except Exception:
                pass
        except Exception as config_error:
            print(f"{label}: could not fully configure camera: {config_error}")

    def _update_camera2_visibility(self):
        """Update visibility of camera panes based on number of connected cameras."""
        num_cameras = len([c for c in [getattr(self, "cam", None), getattr(self, "cam2", None)] if c is not None])
        
        if num_cameras == 0:
            # No cameras: hide all camera stuff, show only motor controls
            self.cam_splitter.hide()
            self.camera_controls.hide()
        elif num_cameras == 1:
            # One camera: show only first camera pane (with tabs)
            self.cam_splitter.show()
            self.camera_controls.show()
            self.cam1_tabs.show()
            self.imgplot2.hide()
            self.cam_splitter.setSizes([1, 0])
        else:
            # Two cameras: show both panes
            self.cam_splitter.show()
            self.camera_controls.show()
            self.cam1_tabs.show()
            self.imgplot2.show()
            total = max(200, self.cam_splitter.height())
            self.cam_splitter.setSizes([total // 2, total // 2])

    def connect_camera(self):
        self._wait_for_grab_idle()
        if getattr(self, "cam", None) is not None or getattr(self, "camList", None) is not None:
            self.disconnec_camera()
        try:
            self.system = PySpin.System.GetInstance()
            self.camList = self.system.GetCameras()
            n_cams = int(self.camList.GetSize())
            if n_cams == 0:
                print("No cameras detected!")
                self.camera_controls.connect_status.setText("Disconnected")
                self.camList.Clear()
                self.system.ReleaseInstance()
                self.cam = None
                self.cam2 = None
                self.cameras = []
                self._update_camera2_visibility()
                return

            self.cameras = []
            limit = min(n_cams, 2)
            if n_cams > 2:
                print(f"Detected {n_cams} cameras; live view uses the first two")
            for i in range(limit):
                cam = self.camList[i]
                label = f"Camera {i + 1}"
                try:
                    cam.Init()
                    name = self._camera_display_name(cam)
                    print(f"{label} connected: {name}")
                    self._configure_flir_camera(cam, label)
                    self.cameras.append(cam)
                    if i == 0:
                        self.imgplot.set_title(f"{label} — {name}")
                    else:
                        self.imgplot2.set_title(f"{label} — {name}")
                except Exception as init_error:
                    print(f"{label} failed to initialize: {init_error}")

            if not self.cameras:
                raise RuntimeError("No cameras could be initialized")

            self.cam = self.cameras[0]
            self.cam2 = self.cameras[1] if len(self.cameras) > 1 else None
            self._update_camera2_visibility()
            QTimer.singleShot(0, self._update_camera2_visibility)

            if self.cam2 is not None:
                self.camera_controls.connect_status.setText("Connected (2 cameras)")
            else:
                self.camera_controls.connect_status.setText("Connected")
            self.camera_controls.rm_hotspots_button.setEnabled(True)
            print(f"{len(self.cameras)} camera(s) connected and initialized")
        except Exception as e:
            print(f"Error connecting camera: {e}")
            self.camera_controls.connect_status.setText("Disconnected")
            self.camera_controls.rm_hotspots_button.setEnabled(False)
            self.cam = None
            self.cam2 = None
            self.cameras = []
            self._update_camera2_visibility()

    def load_dark_frame(self):
        """Load dark frames from disk if available"""
        # Load dark frame for camera 1
        try:
            if os.path.exists(self.dark_frame_path):
                self.hotspot_mask = np.load(self.dark_frame_path)
                print("=" * 60)
                print("CAMERA 1 DARK FRAME LOADED")
                print(f"File: {self.dark_frame_path}")
                mean_value = np.mean(self.hotspot_mask)
                max_value = np.max(self.hotspot_mask)
                print(f"Dark frame stats: Mean={mean_value:.1f}, Max={max_value:.1f}")
                print("Dark frame will be subtracted from Camera 1 images")
                print("=" * 60)
            else:
                print(f"No saved Camera 1 dark frame found at {self.dark_frame_path}")
        except Exception as e:
            print(f"Error loading Camera 1 dark frame: {e}")
            self.hotspot_mask = None
        
        # Load dark frame for camera 2
        try:
            if os.path.exists(self.dark_frame_path2):
                self.hotspot_mask2 = np.load(self.dark_frame_path2)
                print("=" * 60)
                print("CAMERA 2 DARK FRAME LOADED")
                print(f"File: {self.dark_frame_path2}")
                mean_value = np.mean(self.hotspot_mask2)
                max_value = np.max(self.hotspot_mask2)
                print(f"Dark frame stats: Mean={mean_value:.1f}, Max={max_value:.1f}")
                print("Dark frame will be subtracted from Camera 2 images")
                print("=" * 60)
            else:
                print(f"No saved Camera 2 dark frame found at {self.dark_frame_path2}")
        except Exception as e:
            print(f"Error loading Camera 2 dark frame: {e}")
            self.hotspot_mask2 = None
    
    def save_dark_frame(self):
        """Save dark frames to disk"""
        try:
            if self.hotspot_mask is not None:
                np.save(self.dark_frame_path, self.hotspot_mask)
                print(f"Camera 1 dark frame saved to {self.dark_frame_path}")
        except Exception as e:
            print(f"Error saving Camera 1 dark frame: {e}")
        
        try:
            if self.hotspot_mask2 is not None:
                np.save(self.dark_frame_path2, self.hotspot_mask2)
                print(f"Camera 2 dark frame saved to {self.dark_frame_path2}")
        except Exception as e:
            print(f"Error saving Camera 2 dark frame: {e}")
    
    def calibrate_hotspots(self):
        """Start dark frame calibration using 10 frames (lens cap on)"""
        num_cameras = len(self._camera_list())
        if num_cameras == 0:
            print("ERROR: No cameras connected. Connect cameras before calibrating.")
            return
        
        print("=" * 60)
        print("DARK FRAME CALIBRATION STARTED")
        print(f"Calibrating {num_cameras} camera(s)")
        print("*** PUT LENS CAP(S) ON NOW ***")
        print("Collecting 10 frames to create dark frame...")
        print("=" * 60)
        
        # Reset calibration data
        self.calibration_frames = []
        self.calibration_frames2 = []
        self.is_calibrating = True
        self.hotspot_mask = None
        self.hotspot_mask2 = None
        
        # Set button text to show calibration is in progress
        self.camera_controls.rm_hotspots_button.setText("Calibrating...")
        self.camera_controls.rm_hotspots_button.setEnabled(False)
        
        # Start continuous capture if not already running
        was_capturing = self.is_capturing
        if not was_capturing:
            self.camera_controls.capture_mode_combobox.setCurrentText("Continuous")
            self.start_continuous_capture()
        
        # Timer will automatically stop after 10 frames are collected
        # (handled in capture_single_frame)
    
    def finish_hotspot_calibration(self):
        """Process collected frames to create dark frame (average of all frames)"""
        cam1_ready = len(self.calibration_frames) >= 10
        cam2_ready = len(self.calibration_frames2) >= 10
        
        if not cam1_ready and not cam2_ready:
            print(f"Error: Not enough frames collected (Cam1: {len(self.calibration_frames)}, Cam2: {len(self.calibration_frames2)})")
            self.is_calibrating = False
            self.camera_controls.rm_hotspots_button.setText("Dark Frame")
            self.camera_controls.rm_hotspots_button.setEnabled(True)
            return
        
        print("Creating dark frame(s) from collected images...")
        
        # Process Camera 1 dark frame
        if cam1_ready:
            frames = np.array(self.calibration_frames)  # Shape: (10, height, width, [channels])
            self.hotspot_mask = np.mean(frames, axis=0).astype(np.float32)
            mean_value = np.mean(self.hotspot_mask)
            max_value = np.max(self.hotspot_mask)
            print(f"Camera 1: Dark frame created from {len(self.calibration_frames)} frames")
            print(f"  Stats: Mean={mean_value:.1f}, Max={max_value:.1f}")
        
        # Process Camera 2 dark frame
        if cam2_ready:
            frames2 = np.array(self.calibration_frames2)
            self.hotspot_mask2 = np.mean(frames2, axis=0).astype(np.float32)
            mean_value2 = np.mean(self.hotspot_mask2)
            max_value2 = np.max(self.hotspot_mask2)
            print(f"Camera 2: Dark frame created from {len(self.calibration_frames2)} frames")
            print(f"  Stats: Mean={mean_value2:.1f}, Max={max_value2:.1f}")
        
        print("=" * 60)
        print(f"DARK FRAME CALIBRATION COMPLETE")
        print(f"Dark frame(s) will be subtracted from all subsequent images")
        print("*** YOU CAN REMOVE THE LENS CAP(S) NOW ***")
        print("=" * 60)
        
        # Save dark frames to disk
        self.save_dark_frame()
        
        # Clean up
        self.calibration_frames = []
        self.calibration_frames2 = []
        self.is_calibrating = False
        self.camera_controls.rm_hotspots_button.setText("Dark Frame")
        self.camera_controls.rm_hotspots_button.setEnabled(True)
    
    def on_capture_mode_changed(self):
        """Handle mode change - stop continuous capture if switching away from it"""
        if self.is_capturing:
            self.stop_continuous_capture()
        
        # Update button text based on mode
        capture_mode = self.camera_controls.capture_mode_combobox.currentText()
        if capture_mode == "Single":
            self.camera_controls.capture_button.setText("Capture")
        else:
            self.camera_controls.capture_button.setText("Start")
    
    def on_stack_mode_changed(self):
        """Handle stack mode change - refresh display with new stacking method"""
        if self.is_tracking and self._stacking_enabled() and self.tracking_stack_frames:
            # Reset cache and force recomputation for new mode
            self.tracking_stack_cached_image = None
            self.tracking_stack_display_counter = 0
            self._stack_computation_pending = False  # Reset pending flag for new mode
            # Trigger recomputation with new mode
            self._get_stacked_image(force_compute=True)
            mode = self.dpad.stack_mode_combo.currentText()
            print(f"Stack display mode changed to: {mode}")
    
    def on_cam1_tab_changed(self, index):
        """Handle Camera 1 tab change - refresh the newly visible view"""
        if index == 0:
            # Switched to Live tab - show latest raw frame
            if self.latest_frame is not None:
                self._show_image_array(self.latest_frame, plot=self.imgplot)
        elif index == 1:
            # Switched to Stacked tab - show latest stack result
            if self._stacking_enabled() and self.tracking_stack_frames:
                stacked = self._get_stacked_image()
                if stacked is not None:
                    self._show_image_array(stacked, plot=self.imgplot_stacked)

    def capture_image(self):
        """Main capture function that handles both single and continuous modes"""
        capture_mode = self.camera_controls.capture_mode_combobox.currentText()
        
        if capture_mode == "Single":
            # Single shot mode
            self.capture_single_frame()
            self.camera_controls.capture_button.setChecked(False)
        else:
            # Continuous mode - toggle on/off
            if self.is_capturing:
                # Stop continuous capture
                self.stop_continuous_capture()
            else:
                # Start continuous capture
                self.start_continuous_capture()
    
    def start_continuous_capture(self):
        """Start continuous image capture"""
        self.is_capturing = True
        self.camera_controls.capture_button.setText("Stop")
        interval = self._capture_interval_ms()
        self.capture_timer.start(interval)
        self.capture_single_frame()
        print(f"Started continuous capture mode ({interval} ms interval)")
    
    def stop_continuous_capture(self):
        """Stop continuous image capture"""
        self.is_capturing = False
        self.capture_timer.stop()
        
        # Update button based on current mode
        capture_mode = self.camera_controls.capture_mode_combobox.currentText()
        if capture_mode == "Continuous":
            self.camera_controls.capture_button.setText("Start")
        else:
            self.camera_controls.capture_button.setText("Capture")
        self.camera_controls.capture_button.setChecked(False)

        # Do not EndAcquisition while GetNextImage is still blocking on the worker
        self._wait_for_grab_idle()
        for cam in self._camera_list():
            try:
                if cam.IsStreaming():
                    cam.EndAcquisition()
            except Exception:
                pass
        print("Stopped continuous capture mode")

    def capture_single_frame(self):
        """Queue a camera grab on the capture worker (does not block the GUI)."""
        if self.is_closing or self._grab_inflight:
            return
        cams = self._camera_list()
        if not cams:
            return

        try:
            exposure_time = float(self.camera_controls.exposure_edit.text())
        except ValueError:
            exposure_time = 10000

        try:
            gain = float(self.camera_controls.gain_edit.text())
        except ValueError:
            gain = 1.0

        params = {
            "is_continuous": self.is_capturing,
            "exposure_time": exposure_time,
            "gain": gain,
            "display_mode": self.camera_controls.color_mode_combobox.currentText(),
        }
        self._grab_inflight = True
        self._request_grab.emit(cams, params)

    def _on_capture_error(self, message):
        print(f"Error capturing image: {message}")

    def _on_grab_finished(self):
        self._grab_inflight = False

    def _on_aligned_frame(self, aligned):
        """Add a worker-aligned frame to the tracking stack and refresh the view."""
        if self.is_closing or aligned is None:
            return
        if not self.is_tracking or not self._stacking_enabled():
            return
        
        mode = self.dpad.stack_mode_combo.currentText()
        
        # Always maintain ring buffer for median/sigma-clip (last N frames)
        self.tracking_stack_frames.append(aligned.copy())
        if len(self.tracking_stack_frames) > self.tracking_stack_max_frames:
            self.tracking_stack_frames.pop(0)  # Remove oldest frame
        
        # Handle different stacking modes
        if mode == "Mean-of-Medians":
            # Batch median mode: collect frames, send batch to worker when full
            self.tracking_batch_frames.append(aligned.copy())
            
            if len(self.tracking_batch_frames) >= self.tracking_batch_size:
                if not self._batch_median_pending:
                    # Send batch to worker for median computation (non-blocking)
                    self._batch_median_pending = True
                    frames_copy = [f.copy() for f in self.tracking_batch_frames]
                    self._request_batch_median.emit(frames_copy)
                    print(f"  Batch {self.tracking_median_batch_count + 1}: Computing median of {self.tracking_batch_size} frames in background...")
                    
                    # Clear batch for next round
                    self.tracking_batch_frames = []
            else:
                # Show both current batch progress AND total frames processed
                total_so_far = self.tracking_median_batch_count * self.tracking_batch_size + len(self.tracking_batch_frames)
                print(f"  Batch progress: {len(self.tracking_batch_frames)}/{self.tracking_batch_size} frames (total: {total_so_far} frames processed)")
        
        elif self.dpad.deep_space_checkbox.isChecked() and mode == "Mean":
            # Deep space mean mode: unlimited accumulator with weight map
            if self.tracking_accumulator is None or self.tracking_accumulator.shape != aligned.shape:
                self.tracking_accumulator = np.array(aligned, dtype=np.float64, copy=True)
                self.tracking_accumulator_count = 1
                # Initialize weight map - tracks non-zero pixel contributions
                self.tracking_weight_map = np.ones_like(aligned, dtype=np.float64)
                self.tracking_weight_map[aligned == 0] = 0.0
            else:
                self.tracking_accumulator += aligned.astype(np.float64)
                self.tracking_accumulator_count += 1
                # Update weight map: increment where frame has non-zero data
                self.tracking_weight_map += (aligned > 0).astype(np.float64)
            
            print(f"  Stack: {len(self.tracking_stack_frames)} in buffer, {self.tracking_accumulator_count} total accumulated")
        else:
            print(f"  Stack depth: {len(self.tracking_stack_frames)} frame(s)")
        
        # Update stacked view ONLY if that tab is visible (critical for remote desktop performance)
        if self.cam1_tabs.currentIndex() == 1:
            self._show_image_array(self._get_stacked_image(), plot=self.imgplot_stacked)

    def _on_captured_frame(self, frames):
        """Dark-subtract and display frames that arrived from the capture worker."""
        if self.is_closing or frames is None:
            return
        if isinstance(frames, np.ndarray):
            frames = [frames]
        image_np = frames[0] if len(frames) > 0 else None
        image2_np = frames[1] if len(frames) > 1 else None
        if image_np is None and image2_np is None:
            return

        # Collect calibration frames
        if self.is_calibrating:
            if image_np is not None and len(self.calibration_frames) < 10:
                self.calibration_frames.append(image_np.copy())
                print(f"Camera 1 dark frame {len(self.calibration_frames)}/10 collected")
            
            if image2_np is not None and len(self.calibration_frames2) < 10:
                self.calibration_frames2.append(image2_np.copy())
                print(f"Camera 2 dark frame {len(self.calibration_frames2)}/10 collected")
            
            # Check if both cameras (if present) have enough frames
            cam1_done = image_np is None or len(self.calibration_frames) >= 10
            cam2_done = image2_np is None or len(self.calibration_frames2) >= 10
            
            if cam1_done and cam2_done:
                self.stop_continuous_capture()
                self.finish_hotspot_calibration()
                return

        # Apply dark frame subtraction for Camera 1
        if image_np is not None and self.hotspot_mask is not None and not self.is_calibrating:
            if len(image_np.shape) == 3 and len(self.hotspot_mask.shape) == 2:
                image_np = image_np.astype(np.float32)
                for i in range(image_np.shape[2]):
                    image_np[:, :, i] = np.clip(image_np[:, :, i] - self.hotspot_mask, 0, 255)
                image_np = image_np.astype(np.uint8)
            elif image_np.shape == self.hotspot_mask.shape:
                image_np = np.clip(image_np.astype(np.float32) - self.hotspot_mask, 0, 255).astype(np.uint8)
            else:
                print(f"Warning: Camera 1 dark frame shape {self.hotspot_mask.shape} doesn't match image shape {image_np.shape}. Skipping subtraction.")

        # Apply dark frame subtraction for Camera 2
        if image2_np is not None and self.hotspot_mask2 is not None and not self.is_calibrating:
            if len(image2_np.shape) == 3 and len(self.hotspot_mask2.shape) == 2:
                image2_np = image2_np.astype(np.float32)
                for i in range(image2_np.shape[2]):
                    image2_np[:, :, i] = np.clip(image2_np[:, :, i] - self.hotspot_mask2, 0, 255)
                image2_np = image2_np.astype(np.uint8)
            elif image2_np.shape == self.hotspot_mask2.shape:
                image2_np = np.clip(image2_np.astype(np.float32) - self.hotspot_mask2, 0, 255).astype(np.uint8)
            else:
                print(f"Warning: Camera 2 dark frame shape {self.hotspot_mask2.shape} doesn't match image shape {image2_np.shape}. Skipping subtraction.")

        if image_np is not None:
            self.display_image(image_np)
        if image2_np is not None:
            self._show_camera2_array(image2_np)

    def update_color_correction(self):
        """Update color correction labels and apply to current image"""
        # Update labels
        self.camera_controls.red_label.setText(f"Red: {self.camera_controls.red_slider.value()/100:.1f}x")
        self.camera_controls.green_label.setText(f"Green: {self.camera_controls.green_slider.value()/100:.1f}x")
        self.camera_controls.blue_label.setText(f"Blue: {self.camera_controls.blue_slider.value()/100:.1f}x")
        
        # If we have an image, apply color correction
        if hasattr(self.imgplot, 'image_data') and self.imgplot.image_data is not None:
            self.apply_color_correction(self.imgplot)
        if hasattr(self, "imgplot2") and self.imgplot2.image_data is not None:
            self.apply_color_correction(self.imgplot2)


    def apply_color_correction(self, plot=None):
        """Apply RGB gain correction to the current image for display."""
        plot = plot or self.imgplot
        if plot.image_data is None or len(plot.image_data.shape) != 3:
            return  # Skip if image is not RGB
            
        # Get correction factors
        r_factor = self.camera_controls.red_slider.value() / 100.0
        g_factor = self.camera_controls.green_slider.value() / 100.0
        b_factor = self.camera_controls.blue_slider.value() / 100.0
        
        # Work in float, keep original image_data untouched
        corrected_image = plot.image_data.astype(np.float32, copy=True)
        
        # image_data is RGB: channel 0=R, 1=G, 2=B
        corrected_image[:, :, 0] = np.clip(corrected_image[:, :, 0] * r_factor, 0, 255)
        corrected_image[:, :, 1] = np.clip(corrected_image[:, :, 1] * g_factor, 0, 255)
        corrected_image[:, :, 2] = np.clip(corrected_image[:, :, 2] * b_factor, 0, 255)
        
        # Update the display
        plot.image_item.setImage(corrected_image.astype(np.uint8))
        
        # Update pixel info display if mouse is hovering
        plot.update_pixel_info()
        
        # Update projection plots
        plot.update_projections()


    def display_image(self, image_np):
        """
        Store and display a captured image (color images are RGB).
        While tracking, centroid the raw frame, align it to the first lock,
        and show the running mean stack instead of the latest frame.
        """
        # Safety check: make sure we have a valid image
        if image_np is None:
            print("Warning: Cannot display None image")
            return
        
        if not isinstance(image_np, np.ndarray) or image_np.size == 0:
            print("Warning: Invalid image data")
            return
        
        image_np = np.rot90(image_np, k=-1)  # k=-1 rotates 90 degrees clockwise
        self.latest_frame = image_np
        self.latest_frame_id += 1

        if self.is_tracking:
            result = self._ingest_tracking_frame(image_np)
            self._display_tracking_result(image_np, result)
            self._issue_tracking_motor_correction()
        else:
            self._show_image_array(image_np)

    def resize_rois(self, image_np):
        """Resize ROIs to 10% of the smallest image dimension"""
        if image_np is None:
            return
            
        # Get image dimensions
        if len(image_np.shape) == 2:
            height, width = image_np.shape
        else:
            height, width, _ = image_np.shape
            
        # Calculate size for ROI (10% of smallest dimension)
        roi_size = min(width, height) * 0.1
        
        # Set ROI1 position (top left quarter)
        x1 = width * 0.25 - roi_size/2
        y1 = height * 0.25 - roi_size/2
        self.imgplot.ROI1.setPos([x1, y1])
        self.imgplot.ROI1.setSize([roi_size, roi_size])
        
        # Set ROI2 position (bottom right quarter)
        x2 = width * 0.75 - roi_size/2
        y2 = height * 0.75 - roi_size/2
        self.imgplot.ROI2.setPos([x2, y2])
        self.imgplot.ROI2.setSize([roi_size, roi_size])


    def disconnec_camera(self):
        # Properly deinitialize and release the camera in correct order.
        # Order matters: camera -> camList -> system
        self._wait_for_grab_idle()
        try:
            # Step 1: Stop streaming and deinitialize every camera
            for i, cam in enumerate(self._camera_list()):
                try:
                    if cam.IsStreaming():
                        cam.EndAcquisition()
                    cam.DeInit()
                except Exception as e:
                    print(f"Error deinitializing camera {i + 1}: {e}")
            self.cam = None
            self.cam2 = None
            self.cameras = []
            if hasattr(self, "imgplot2"):
                self._update_camera2_visibility()
            
            # Step 2: Clear the camera list (releases camera references)
            if hasattr(self, 'camList') and self.camList is not None:
                try:
                    self.camList.Clear()
                    # Small delay to ensure references are released
                    time.sleep(0.1)
                except Exception as e:
                    print(f"Error clearing camera list: {e}")
                # Delete the camera list reference
                del self.camList
                self.camList = None
            
            # Step 3: Release the system instance (must be last)
            if hasattr(self, 'system') and self.system is not None:
                try:
                    self.system.ReleaseInstance()
                except Exception as e:
                    print(f"Error releasing system: {e}")
                # Don't delete system - ReleaseInstance handles it
                
            print("Camera disconnected successfully")
        except Exception as e:
            print(f"Unexpected error disconnecting camera: {e}")

    def best_fit_curve(x, y, t, degree=2):
        """
        Create a best fit curve function given arrays of x positions, y positions, and time t.

        Parameters:
            x (array-like): Array of x positions.
            y (array-like): Array of y positions.
            t (array-like): Time array corresponding to x and y positions.
            degree (int): Degree of the polynomial fit (default is 2 for quadratic).

        Returns:
            tuple: Two functions (fx, fy) that predict x and y positions given time.
        """
        # Fit polynomial to x(t) and y(t)
        x_coeffs = np.polyfit(t, x, degree)
        y_coeffs = np.polyfit(t, y, degree)

        # Create polynomial functions
        fx = np.poly1d(x_coeffs)
        fy = np.poly1d(y_coeffs)


        # fx, fy = best_fit_curve(x_data, y_data, t_data)

        # # Predict positions at t=2.5
        # t_test = 2.5
        # print("Predicted x:", fx(t_test))
        # print("Predicted y:", fy(t_test))

        return fx, fy
            



    def track_and_reposition_zoom_region(self, img):
        """Keep the second ROI centered on its brightest star (no motor moves)."""
        self._follow_star_with_roi2(img)

    def check_idle(self, period=600):
        #TODO: if no motion command has been issued in the last 10 minutes, disable motors
        pass

    def image_to_ascii(self, image_path):
        ASCII_CHARS = "@%#*+=-:. "
        
        # Load image using imageio
        image = imageio.imread(image_path)
        
        if image is None:
            raise ValueError("Could not load image. Check the path.")

        # Convert to grayscale if it's RGB
        if len(image.shape) == 3:  # Check if image has multiple channels (RGB)
            gray_image = np.dot(image[..., :3], [0.2989, 0.587, 0.114])  # Grayscale conversion
        else:
            gray_image = image  # Image is already grayscale

        # Resize to 30x30
        resized_image = np.array(Image.fromarray(gray_image).resize((30, 30), resample=Image.LANCZOS))

        # Normalize pixel values to the range of ASCII characters
        ascii_str = ""
        for row in resized_image:
            for pixel in row:
                ascii_str += ASCII_CHARS[int(pixel) // 32]  # Map grayscale value to ASCII character
            ascii_str += "\n"

        return ascii_str

class Stream(QtCore.QObject):
    newText = pyqtSignal(str)
    
    def __init__(self, newText=None):
        super().__init__()
        if newText:
            self.newText.connect(newText)
    
    def write(self, text):
        self.newText.emit(str(text))
    
    def flush(self):
        pass  # Need this for file-like object compatibility

    def __del__(self):
        # Disconnect all signals before deletion
        try:
            self.newText.disconnect()
        except:
            pass
        # Restore original stdout if this is the current stdout
        if sys.stdout is self:
            sys.stdout = sys.__stdout__


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
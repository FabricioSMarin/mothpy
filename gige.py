import PySpin
import cv2
import numpy as np
import threading

class CameraThread(threading.Thread):
    def __init__(self, cam):
        threading.Thread.__init__(self)
        self.cam = cam
        self.running = True

    def run(self):
        try:
            self.cam.BeginAcquisition()

            while self.running:
                image_result = self.cam.GetNextImage()

                if image_result.IsIncomplete():
                    print(f'Image incomplete with image status {image_result.GetImageStatus()}')
                else:
                    # Convert image to OpenCV format
                    image_data = image_result.GetNDArray()
                    image_result.Release()

                    # Display image using OpenCV
                    cv2.imshow('FLIR GigE Camera', image_data)

                    # Exit loop on 'q' key press
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.running = False
                        break

            self.cam.EndAcquisition()

        except PySpin.SpinnakerException as ex:
            print(f'Error: {ex}')

        finally:
            self.cam.DeInit()

def configure_camera(cam):
    """
    This function configures the camera settings.
    """
    cam.Init()

    # Retrieve GenICam nodemap
    nodemap = cam.GetNodeMap()

    # Set acquisition mode to continuous
    node_acquisition_mode = PySpin.CEnumerationPtr(nodemap.GetNode('AcquisitionMode'))
    node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
    acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()
    node_acquisition_mode.SetIntValue(acquisition_mode_continuous)

    print('Camera configured to continuous acquisition mode.')

def main():
    # Initialize system and camera
    system = PySpin.System.GetInstance()
    cam_list = system.GetCameras()
    num_cameras = cam_list.GetSize()

    if num_cameras == 0:
        cam_list.Clear()
        system.ReleaseInstance()
        print('No cameras detected.')
        return

    cam = cam_list.GetByIndex(0)
    configure_camera(cam)

    cam_thread = CameraThread(cam)
    cam_thread.start()

    try:
        # Wait for the thread to finish
        cam_thread.join()
    except KeyboardInterrupt:
        # Handle keyboard interrupt to stop the thread gracefully
        cam_thread.running = False
        cam_thread.join()

    finally:
        del cam
        cam_list.Clear()
        system.ReleaseInstance()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

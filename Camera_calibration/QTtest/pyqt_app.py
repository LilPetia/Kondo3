from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout, QMainWindow
from PyQt5.QtGui import QPixmap
import sys
import cv2
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread
import numpy as np

import arducam_mipicamera as arducam
import v4l2 #sudo pip install v4l2
import time
import numpy as np
import cv2 #sudo apt-get install python-opencv
import os
import yaml

def set_controls(camera):
    try:
        #print("Enable Auto Exposure...")
        #camera.software_auto_exposure(enable = True)
        camera.set_control(v4l2.V4L2_CID_EXPOSURE, 800)  # 0 < 65535
        camera.set_control(v4l2.V4L2_CID_GAIN, 255)     # 0 < 255
        camera.set_control(v4l2.V4L2_CID_VFLIP, 1)
        print('exposure:', camera.get_control(v4l2.V4L2_CID_EXPOSURE), 'gain: ', camera.get_control(v4l2.V4L2_CID_GAIN))
        #print("Enable Auto White Balance...")
        #camera.software_auto_white_balance(enable = True)
    except Exception as e:
        print(e)

class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        self._run_flag = True

    def run(self):
        # capture from web cam
        #cap = cv2.VideoCapture(0)
        camera = arducam.mipi_camera()
        print("Open camera...")
        camera.init_camera()
        camera.set_mode(6) # chose a camera mode which yields raw10 pixel format, see output of list_format utility
        fmt = camera.get_format()
        width = fmt.get("width")
        height = fmt.get("height")
        print("Current resolution is {w}x{h}".format(w=width, h=height))
        set_controls(camera)
        with open("/home/pi/MIPI_Camera_old/RPI/python/Camera_calibration/calibration_matrix.yaml", "r")as f:
            data = yaml.load(f, yaml.Loader)
        camera_matrix = np.asarray(data['camera_matrix'])
        dist_coeff = np.asarray(data['dist_coeff'])
        newcameramtx, roi=cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeff , (width,height), 1, (width,height))
        roi_x, roi_y, roi_w, roi_h = roi
        map1, map2 = cv2.initUndistortRectifyMap(camera_matrix, dist_coeff, None, newcameramtx, (width,height), cv2.CV_16SC2)
        time.sleep(0.5)
        timer = time.perf_counter()
        while self._run_flag:
            image = camera.capture(encoding = 'raw')
            image = arducam.remove_padding(image.data, width, height, 10)
            image = arducam.unpack_mipi_raw10(image)
            image = image.reshape(height, width) << 6
            #print(image.size, image.dtype, image.shape)
            image = cv2.cvtColor(image, cv2.COLOR_BayerRG2BGR)
            #image = cv2.remap(image, map1, map2, cv2.INTER_LINEAR)
            cv2_image = image[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]
            cv_img= cv2.resize(cv2_image, (480,360), interpolation= cv2.INTER_LINEAR)
            #cv2.imshow("Arducam", cv_img)
            #cv2.waitKey(10)
            #cv2_image = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
            #cv2.imshow("Arducam", cv2_image)
            #cv2.waitKey(10)
            print('FPS:', 1/(time.perf_counter() - timer))
            timer = time.perf_counter()
            #ret, cv_img = cap.read()
            self.change_pixmap_signal.emit(cv_img)
        # shut down capture system
        cap.release()

    def stop(self):
        """Sets run flag to False and waits for thread to finish"""
        self._run_flag = False
        self.wait()


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Qt live label demo")
        self.disply_width = 480
        self.display_height = 360
        # create the label that holds the image
        self.image_label = QLabel(self)
        self.image_label.resize(self.disply_width, self.display_height)
        # create a text label
        self.textLabel = QLabel('Webcam')
        self.resize(self.disply_width+100, self.display_height + 100 )

        # create a vertical box layout and add the two labels
        vbox = QVBoxLayout()
        vbox.addWidget(self.image_label)
        vbox.addWidget(self.textLabel)
        # set the vbox layout as the widgets layout
        self.setLayout(vbox)

        # create the video capture thread
        self.thread = VideoThread()
        # connect its signal to the update_image slot
        self.thread.change_pixmap_signal.connect(self.update_image)
        # start the thread
        self.thread.start()

    def closeEvent(self, event):
        self.thread.stop()
        event.accept()



    @pyqtSlot(np.ndarray)
    def update_image(self, cv_img):
        """Updates the image_label with a new opencv image"""
        qt_img = self.convert_cv_qt(cv_img)
        self.image_label.setPixmap(qt_img)
    
    def convert_cv_qt(self, cv_img):
        """Convert from an opencv image to QPixmap"""
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB, cv2.CV_8UC3)
        #rgb_image = rgb_image.astype(np.uint16)
        rgb_image = rgb_image/256
        rgb_image = rgb_image.astype(np.uint8)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        #print('bytes_per_line:', bytes_per_line)
        convert_to_Qt_format = QtGui.QImage(rgb_image, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        p = convert_to_Qt_format.scaled(self.disply_width, self.display_height, Qt.KeepAspectRatio)
        return QPixmap.fromImage(p)
    
if __name__=="__main__":
    app = QApplication(sys.argv)
    a = App()
    a.show()
    sys.exit(app.exec_())
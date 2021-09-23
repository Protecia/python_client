import time
import requests
import cv2
import numpy as np
from threading import Thread, Lock
import settings
import os
import darknet as dn
from log import Logger
import secrets
import concurrent.futures


class ProcessCamera(object):
    """Thread used to grab camera images and process the image with darknet"""

    def __init__(self, cam, q_result, q_img, q_img_real, tlock, camera_state, e_state):
        Thread.__init__(self)
        self.cam = cam
        self.running = False
        self.running_rtsp = False
        self.pos_sensivity = cam['pos_sensivity']
        self.request_OK = False
        self.lock = Lock()
        self.tlock = tlock
        self.black_list = [i.encode() for i in settings.DARKNET_CONF['all']['RESTRICT']]
        self.logger = Logger('process_camera_thread__'+str(self.cam["id"])+'--'+self.cam["name"],
                             level=settings.PROCESS_CAMERA_LOG).run()
        self.Q_img = q_img
        self.Q_result = q_result
        self.result_DB = []
        self.Q_img_real = q_img_real
        self.force_remove = {}
        self.image_correction = [False, 0]
        self.vcap = None
        self.frame = None
        self.thread_rtsp = None
        self.camera_state = camera_state
        self.e_state = e_state

# -*- coding: utf-8 -*-
"""
Created on Tue Dec  3 15:06:16 2019

@author: julien
"""
import logging

LOG = logging.ERROR
MAIN_LOG = logging.ERROR
VIDEO_LOG = logging.ERROR
UPLOAD_LOG = logging.ERROR
SCAN_LOG = logging.ERROR
PROCESS_CAMERA_LOG = logging.ERROR
SOCKET_LOG = logging.ERROR


#  Darknet conf
DARKNET_PATH = '/NNvision/darknet'

DARKNET_CONF = {
        'all': {
                'CFG': 'cfg/yolov3.cfg',
                'WEIGHTS': '../weights/yolov3.weights',
                'DATA':'/NNvision/python_client/coco_docker.data',
                'RESTRICT':('pottedplant', 'oven', 'bowl',)},
        # 'car': {
        #         'CFG': '../weights/protecia.cfg',
        #         'WEIGHTS':  '../weights/car.weights',
        #         'DATA': '/NNvision/weights/car_docker.data'},
        # 'person': {
        #         'CFG': '../weights/protecia.cfg',
        #         'WEIGHTS': '../weights/person.weights',
        #         'DATA': '/NNvision/weights/person_docker.data'},
        }

# hardware conf
INSTALL_PATH = '/NNvision/python_client'
FFMPEG = '/usr/local/bin/ffmpeg'
HARDWARE = 'nano'
UUID = '/proc/device-tree/chosen/uuid'  # on nano
# UUID = '/proc/device-tree/chosen/ecid' on xavier

# python conf
PYTHON = 'python3'
THREATED_REQUESTS = True
SERVER = 'https://dev.protecia.com/'
SERVER_WS = 'ws://dev.protecia.com/'
VIDEO_REC_TIME = 10
VIDEO_SPACE = 30  # Go
QUEUE_SIZE = 10  # number of images to queue at max
SCAN_INTERVAL = 60  # seconds between each scan of the network to find onvif camera

# client conf
INIT_PASS = 'jznsjoa3z54d'

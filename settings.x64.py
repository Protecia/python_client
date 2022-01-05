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
PING_LOG = logging.ERROR
CAMERA_LOG = logging.ERROR

# Darknet conf
DARKNET_PATH = '/NNvision/darknet'

DARKNET_CONF = {
        'all': {
                'CFG': 'cfg/yolov4.cfg',
                'WEIGHTS': '../weights/yolov4.weights',
                'DATA': '/NNvision/coco_docker.data',
                'RESTRICT': ('pottedplant', 'oven', 'bowl', 'car', 'person')},
        'car': {
                'CFG': '../weights/protecia.cfg',
                'WEIGHTS':  '../weights/car.weights',
                'DATA': '/NNvision/weights/car_docker.data'},
        'person': {
                'CFG': '../weights/protecia.cfg',
                'WEIGHTS': '../weights/person.weights',
                'DATA': '/NNvision/weights/person_docker.data'},
        }

# hardware conf
INSTALL_PATH = '/NNvision'
FFMPEG = '/usr/local/bin/ffmpeg'
HARDWARE = 'x64'
UUID = '/sys/class/dmi/id/product_uuid'

# python conf
PYTHON = 'python3'
THREATED_REQUESTS = True
SERVER = 'https://client.protecia.com/'
SERVER_WS = 'wss://client.protecia.com'
VIDEO_REC_TIME = 10
VIDEO_SPACE = 30  # Go
QUEUE_SIZE = 10  # number of images to queue at max
SCAN_INTERVAL = 60  # seconds between each scan of the network to find onvif camera
RECORDED_DELAY = 2  # nb of days to store on backup video
WSDIR = '/usr/local/lib/python3.8/site-packages/wsdl/'

# remote conf
SSH_SERVER_PORT = 2222
SSH_USER = 'tunnel'

# client conf
INIT_PASS = 'jznsjoa3z54d'

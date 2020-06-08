# -*- coding: utf-8 -*-
"""
Created on Tue Dec  3 15:06:16 2019

@author: julien
"""
import logging

LOG = logging.ERROR
VIDEO_LOG = logging.ERROR
UPLOAD_LOG = logging.ERROR
SCAN_LOG = logging.ERROR
PROCESS_CAMERA_LOG = logging.ERROR

#Darknet conf
DARKNET_PATH='/home/protecia/darknet'

DARKNET_CONF={
        'all':{'CFG' :'cfg/yolov4.cfg', 'WEIGHTS' : 'yolov4.weight', 'DATA' :'/home/protecia/NNvision/python_client/coco_nano.data'},
        'car':{'CFG' :'cfg/yolov4.cfg', 'WEIGHTS' : 'yolov4.weight', 'DATA' :'/home/protecia/NNvision/python_client/coco_nano.data'},
        'person':{'CFG' :'cfg/yolov4.cfg', 'WEIGHTS' : 'yolov4.weight', 'DATA' :'/home/protecia/NNvision/python_client/coco_nano.data'},
        }

# hardware conf
INSTALL_PATH = '/home/protecia/NNvision/python_client'
FFMPEG = '/usr/local/bin/ffmpeg'
HARDWARE = 'nano' # nano or x64

# python conf
PYTHON = 'python3'
THREATED_REQUESTS=True
SERVER = 'https://client.protecia.com/'
VIDEO_REC_TIME = 10
VIDEO_SPACE = 30 #Go
QUEUE_SIZE = 100 # number of images to queue at max

# client conf
KEY = 'e40872239e1c0f4a56dc2636cd98d2b668d4260c10f4a9718433369333a2c54f'
TUNNEL_PORT = 40002


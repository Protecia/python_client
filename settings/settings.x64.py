# -*- coding: utf-8 -*-
"""
Created on Tue Dec  3 15:06:16 2019

@author: julien
"""
import logging

LOG = logging.ERROR
VIDEO_LOG = logging.INFO
UPLOAD_LOG = logging.INFO
SCAN_LOG = logging.INFO
PROCESS_CAMERA_LOG = logging.ERROR

#Darknet conf
DARKNET_PATH='/NNvision/darknet'

DARKNET_CONF={
        'all':{'CFG' :'cfg/yolov4.cfg', 'WEIGHTS' : 'yolov4.weight', 'DATA' :'/home/protecia/NNvision/python_client/coco_nano.data'},
        'car':{'CFG' :'cfg/protecia_car.cfg', 'WEIGHTS' : 'protecai_car.weight', 'DATA' :'/home/protecia/NNvision/python_client/car_nano.data'},
        'person':{'CFG' :'cfg/yolov4.cfg', 'WEIGHTS' : 'yolov4.weight', 'DATA' :'/home/protecia/NNvision/python_client/coco_nano.data'},
        }

# hardware conf
INSTALL_PATH = '/NNvision'
FFMPEG = '/usr/local/bin/ffmpeg'

# python conf
PYTHON = 'python3'
THREATED_REQUESTS=True
SERVER = 'https://client.protecia.com/'
VIDEO_REC_TIME = 10
VIDEO_SPACE = 30 #Go
QUEUE_SIZE = 100 # number of images to queue at max

# client conf
KEY = '1e2e0df0c8616c1bcd5e90721ac2393a70240814100b26b568c75e46972e82a0'
TUNNEL_PORT = 39000


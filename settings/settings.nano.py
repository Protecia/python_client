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
        'all':{
                'CFG' :'cfg/yolov4.cfg',
                'WEIGHTS' : '../weights/yolov4.weights',
                'DATA' :'/home/protecia/NNvision/python_client/coco_nano.data',
                'RESTRICT':('pottedplant','oven','bowl','car','person')},
        'car':{
                'CFG' :'../weights/protecia.cfg',
                'WEIGHTS' : '../weights/car.weights',
                'DATA' :'/NNvision/weights/car_docker.data'},
        'person':{
                'CFG' :'../weights/protecia.cfg',
                'WEIGHTS' : '../weights/person.weights',
                'DATA' :'/NNvision/weights/person_docker.data'},
        }

# hardware conf
INSTALL_PATH = '/home/protecia/NNvision/python_client'
FFMPEG = '/usr/local/bin/ffmpeg'
HARDWARE = 'nano'

# python conf
PYTHON = 'python3'
THREATED_REQUESTS=True
SERVER = 'https://client.protecia.com/'
VIDEO_REC_TIME = 10
VIDEO_SPACE = 30 #Go
QUEUE_SIZE = 10 # number of images to queue at max

# client conf
KEY = ''
TUNNEL_PORT = 39000


# -*- coding: utf-8 -*-
"""
Created on Tue Dec  3 15:06:16 2019

@author: julien
"""
import logging
import json


class Conf(object):
    def __init__(self):
        try:
            with open(INSTALL_PATH + '/settings/conf.json', 'r') as conf_json:
                data = json.load(conf_json)
            self.key = data["key"]
            self.data = data
        except KeyError:
            pass

    def get_conf(self, value):
        return self.data[value]


LOG = logging.ERROR
MAIN_LOG = logging.ERROR
VIDEO_LOG = logging.ERROR
UPLOAD_LOG = logging.ERROR
SCAN_LOG = logging.ERROR
PROCESS_CAMERA_LOG = logging.ERROR
PING_LOG = logging.ERROR
CAMERA_LOG = logging.ERROR

# Darknet conf
DARKNET_PATH='/NNvision/darknet'

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

# client conf
TUNNEL_IP = 'my.protecia.com'
TUNNEL_USER = 'cez542de@client.protecia.com'
SSH_SERVER = 2222
INIT_PASS = 'jznsjoa3z54d'

CONF = Conf()


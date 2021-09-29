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
import asyncio
from process_camera_grab import grab_http, rtsp_reader, grab_rtsp


class ProcessCamera(Thread):

    def __init__(self, cam, tlock):
        Thread.__init__(self)
        self.a = []
        self.cam = cam
        self.running = False
        self.loop = asyncio.new_event_loop()
        self.logger = Logger('process_camera_thread__' + str(self.cam["id"]) + '--' + self.cam["name"],
                             level=settings.PROCESS_CAMERA_LOG).run()
        self.frame = None
        self.vcap = None

    def run(self):
        self.logger.info('running Thread')
        self.running = True
        asyncio.set_event_loop(self.loop)
        if self.cam['stream']:
            rtsp = self.cam['rtsp']
            rtsp_login = 'rtsp://' + self.cam['username'] + ':' + self.cam['password'] + '@' + rtsp.split('//')[1]
            self.vcap = cv2.VideoCapture(rtsp_login)
        self.loop.run_until_complete(asyncio.gather(self.task1(), self.task2()))

    async def task1(self):
        while self.running:
            self.frame = await grab_http(self.cam, self.logger)
            self.frame = await grab_rtsp(self.vcap, self.loop, self.logger)

    async def task2(self):
        while self.running:
            await rtsp_reader(self.vcap, self.loop, self.logger)

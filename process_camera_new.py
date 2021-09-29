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
from process_camera_grab import grab_http


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

    def run(self):
        self.logger.info('running Thread')
        self.running = True
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(asyncio.gather(self.task1(self.a), self.task2(self.a)))

    async def task1(self, a):
        while self.running:
            self.frame = await grab_http(self.cam, self.logger)
            self.a.append('toto')
            self.logger.info(a)
            await asyncio.sleep(1)

    async def task2(self, a):
        while self.running:
            await asyncio.sleep(1)

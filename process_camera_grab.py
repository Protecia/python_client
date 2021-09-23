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


# bufferless VideoCapture
class VideoCapture:

    def __init__(self, name):
        self.cap = cv2.VideoCapture(name)
        self.t = Thread(target=self._reader)
        self.t.daemon = True
        self.t.start()

    # grab frames as soon as they are available
    def _reader(self):
        while True:
            ret = self.cap.grab()
            if not ret:
                break

    # retrieve latest frame
    def read(self):
        ret, frame = self.cap.retrieve()
        if ret and len(frame) > 100:
            return frame


def grab_http(cam, logger):
    if cam['auth_type'] == 'B':
        auth = requests.auth.HTTPBasicAuth(cam['username'], cam['password'])
    if cam['auth_type'] == 'D':
        auth = requests.auth.HTTPDigestAuth(cam['username'], cam['password'])
    try:
        t = time.time()
        r = requests.get(cam['http'], auth=auth, stream=True, timeout=10)
        logger.info(f'get http image {cam["http"]} in  {time.time() - t}s')
        if r.status_code == 200 and len(r.content) > 11000:
            logger.info(f'content of request is len  {len(r.content)}')
            imgb = bytearray(r.content)
            logger.debug(f'bytes0  {imgb}')
            imgb = np.asarray(imgb, dtype="uint8")
            logger.debug(f'bytes1  {imgb}')
            imgb = cv2.imdecode(imgb, 1)
            frame = imgb
            logger.info(f'frame with a len of {len(frame) if frame else "None"}')
            if not frame:
                logger.warning('bad camera download frame is None on {} \n'.format(cam['name']))
                return False
        else:
            logger.warning('bad camera download on {} \n'.format(cam['name']))
            return False
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout, requests.exceptions.MissingSchema):
        logger.warning('network error on {} \n'.format(cam['name']))
        return False

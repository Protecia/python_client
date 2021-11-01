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
from process_camera_utils import Result
import websockets
import json
from utils import get_conf
import queue

path = settings.DARKNET_PATH
net = {}
meta = {}
width = {}
height = {}
class_names = {}

for key, values in settings.DARKNET_CONF.items():
    cfg = os.path.join(path, values['CFG']).encode()
    weights = os.path.join(path, values['WEIGHTS']).encode()
    data = os.path.join(path, values['DATA']).encode()
    net[key] = dn.load_net_custom(cfg, weights, 0, 1)
    meta[key] = dn.load_meta(data)
    class_names[key] = [meta[key].names[i].decode() for i in range(meta[key].classes)]
    width[key] = dn.network_width(net[key])
    height[key] = dn.network_height(net[key])


async def detect_thread(my_net, my_class_names, frame, my_width, my_height, thresh):
    frame_resized = cv2.resize(frame, (my_width, my_height), interpolation=cv2.INTER_LINEAR)
    darknet_image = dn.make_image(my_width, my_height, 3)
    dn.copy_image_from_bytes(darknet_image, frame_resized.tobytes())
    detections = dn.detect_image(my_net, my_class_names, darknet_image, thresh=thresh)
    # make coordinate function of initial size
    height_factor = frame.shape[0] / my_height
    width_factor = frame.shape[1] / my_width
    detections = [(r[0], float(r[1]), (r[2][0]*width_factor, r[2][1]*height_factor,
                                       r[2][2]*width_factor, r[2][3]*height_factor)) for r in detections]
    dn.free_image(darknet_image)
    return detections


class ProcessCamera(object):

    def __init__(self, cam, loop, tlock):
        self.cam = cam
        self.key = get_conf('key')
        self.running_level2 = False
        self.running_level1 = False
        self.loop = loop
        self.logger = Logger('process_camera_thread__' + str(self.cam["id"]) + '--' + self.cam["name"],
                             level=settings.PROCESS_CAMERA_LOG).run()
        self.vcap = None
        self.tlock = tlock
        self.th = cam['threshold'] * (1 - (float(cam['gap']) / 100))
        self.black_list = [i.encode() for i in settings.DARKNET_CONF['all']['RESTRICT']]
        self.result = Result()

    async def run(self):
        """
        Top level task to instantiate cv2 and httpx reader
        """
        self.logger.info('running Thread')
        self.running_level1 = True
        while self.running_level1:
            self.running_level2 = True
            if self.cam['stream']:
                if not self.vcap or not self.vcap.isOpened():
                    rtsp = self.cam['rtsp']
                    rtsp_login = 'rtsp://' + self.cam['username'] + ':' + self.cam['password'] + '@' + rtsp.split('//')[1]
                    self.vcap = cv2.VideoCapture(rtsp_login)
                    self.logger.warning(f'openning videocapture {self.vcap} is {self.vcap.isOpened()}')
                task = [self.task1(), self.task2(), self.task3(), ]
            else:
                task = [self.task1(), self.task3(), ]
            await asyncio.gather(*task)
            if self.cam['stream']:
                self.vcap.release()
                self.logger.warning('VideoCapture close on {}'.format(self.cam['name']))
            asyncio.sleep(3)

    async def task1(self):
        """
        Task to grab image and put informations in result
        """
        bad_read = 0
        while self.running_level2:
            t = time.time()
            if self.cam['stream']:
                self.running_level2 = self.vcap.isOpened()
                frame = await grab_rtsp(self.vcap, self.loop, self.logger, self.cam)
                if frame is False:
                    self.logger.warning(f"Bad rtsp read on {self.cam['name']} videocapture is {self.vcap.isOpened()} "
                                        f"bad_read is {bad_read}")
                    bad_read += 1
                    await asyncio.sleep(0.1)
                    if bad_read > 10:
                        self.running_level2 = False
                else:
                    bad_read = 0
            else:
                self.logger.debug(f"before grab_http on {self.cam['name']}")
                frame = await grab_http(self.cam, self.logger)
            self.logger.info(f"ecriture de la frame {self.cam['name']} {time.strftime('%Y-%m-%d-%H-%M-%S')}"
                             f" en {time.time() - t}s")
            if bad_read == 0:
                t = time.time()
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result_dict = {}
                tasks = []
                for nkey, network in net.items():
                    tasks.append(detect_thread(network, class_names[nkey], frame_rgb, width[nkey],
                                               height[nkey], self.th))
                    result_dict[nkey] = None
                async with self.tlock:
                    result_concurrent = await asyncio.gather(*tasks)
                result_dict = dict(zip(result_dict, result_concurrent))
                if 'all' in result_dict:
                    result_darknet = [r for r in result_dict['all'] if r[0] not in self.black_list]
                    result_dict.pop('all')
                else:
                    result_darknet = []
                for partial_result in result_dict.values():
                    result_darknet += partial_result
                self.result.result_darknet = result_darknet
                self.logger.info(f'{self.cam["name"]} -> brut result darknet {time.time()-t}s : {result_darknet} \n')
                self.result.img_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
                self.result.upload = True
                self.logger.warning(f"queue img bytes {len(self.result.img_bytes)}")

    async def task2(self):
        """
        task to empty the cv2 rtsp queue
        """
        while self.running_level2:
            await rtsp_reader(self.vcap, self.loop, self.logger)

    async def task3(self):
        """
        Task to upload informations to server using websocket connection
        """
        while self.running_level2:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_run_cam') as ws_cam:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_cam.send(json.dumps({'key': self.key}))
                    while self.running_level2:
                        await asyncio.sleep(0.02)
                        if self.result.upload:
                            await ws_cam.send(self.result.img_bytes)
                            self.logger.info(f'-------------> sending img bytes in task 3 {len(self.result.img_bytes)}')
                            self.result.upload = False
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue

    async def task4(self):
        """
        Task to retrieve informations from server :
        _ sending image real time LD
        _ sending image real time HD
        _ sending analysed images
        """
        while self.running_level2:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_get_camera_state') as ws_get_state:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_get_state.send(json.dumps({'key': self.key}))
                    while self.running_level2:
                        await asyncio.sleep(0.02)
                        state = await ws_get_state.recv()
                        self.logger.info(f'receiving state for camera{self.cam["name"]} -> {state}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue

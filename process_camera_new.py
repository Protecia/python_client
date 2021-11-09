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
from process_camera_utils import Result, Img
import websockets
import json
from utils import get_conf


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
        self.rec = False
        self.HD = False
        self.LD = False
        self.queue_frame = asyncio.Queue(maxsize=1)
        self.queue_img_real = asyncio.Queue(maxsize=settings.QUEUE_SIZE)
        self.queue_img = asyncio.Queue(maxsize=settings.QUEUE_SIZE)
        self.queue_result = asyncio.Queue(maxsize=settings.QUEUE_SIZE)

    async def run(self):
        """
        Top level task to instantiate cv2 and httpx reader
        """
        self.logger.info('running Thread')
        self.running_level1 = True
        if self.cam['stream']:
            task = [self.task1_rtsp(), self.task1_rtsp_flush(), self.task2(), self.task3(), self.task4(),
                    self.task5()]
        else:
            task = [self.task1_http(), self.task2(), self.task3(), self.task4(), self.task5()]
        await asyncio.gather(*task)
        await asyncio.sleep(3)

    async def task1_rtsp(self):
        """
        Task to grab image in rtsp and put informations in result
        """
        while self.running_level1:
            self.running_level2 = True
            if not self.vcap or not self.vcap.isOpened():
                rtsp = self.cam['rtsp']
                rtsp_login = 'rtsp://' + self.cam['username'] + ':' + self.cam['password'] + '@' + rtsp.split('//')[1]
                self.vcap = cv2.VideoCapture(rtsp_login)
                self.logger.warning(f'openning videocapture {self.vcap} is {self.vcap.isOpened()}')
            bad_read = 0
            while self.running_level2:
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
                if bad_read == 0:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    await self.queue_frame.put(frame_rgb)
            self.vcap.release()
            self.logger.warning('VideoCapture close on {}'.format(self.cam['name']))

    async def task1_rtsp_flush(self):
        """
        task to empty the cv2 rtsp queue
        """
        while self.running_level1:
            await rtsp_reader(self.vcap, self.loop, self.logger)

    async def task1_http(self):
        while self.running_level1:
            t = time.time()
            self.logger.debug(f"before grab_http on {self.cam['name']}")
            frame = await grab_http(self.cam, self.logger)
            self.logger.info(f"ecriture de la frame {self.cam['name']} {time.strftime('%Y-%m-%d-%H-%M-%S')}"
                             f" en {time.time() - t}s")
            await self.queue_frame.put(frame)

    async def task2(self):
        while self.running_level1:
            t = time.time()
            frame_rgb = await self.queue_frame.get()
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
            result = Result(self.cam['pos_sensivity'], self.cam['threshold'], self.logger, result_darknet)
            self.logger.info(f'{self.cam["name"]} -> brut result darknet {time.time()-t}s : {result_darknet} \n')
            await result.process_result()
            await self.queue_result.put(result.result_json)

            if self.HD or self.LD:
                if self.cam['reso']:
                    if frame.shape[0] != self.cam['height'] or frame.shape[1] != self.cam['width']:
                        frame = cv2.resize(frame, (self.cam['width'], self.cam['height']),
                                           interpolation=cv2.INTER_CUBIC)
                if self.LD:
                    resize_factor = self.cam['max_width_rtime'] / frame.shape[1]
                    frame = cv2.resize(frame, (self.cam['max_width_rtime'], int(frame.shape[0] * resize_factor)),
                                       interpolation=cv2.INTER_CUBIC)
                    await self.queue_img_real.put((self.cam['id'], result.result_json['result_filtered_true'],
                                                  cv2.imencode('.jpg', frame)[1].tobytes(), resize_factor))
                    self.logger.warning(f'Q_img_real LD on {self.cam["name"]} : size {self.queue_img_real.qsize()}')






    async def task3(self):
        """
        Task to upload results to server using websocket connection
        """
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_run_cam_result') as ws_cam:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_cam.send(json.dumps({'key': self.key}))
                    while self.running_level1:
                        result = await self.queue_result.get()
                        # await ws_cam.send(json.dumps(result))
                        self.logger.info(f'-------------> sending result in task 3 {result}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue

    async def task4(self):
        """
        Task to upload images real time to server using websocket connection
        """
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_run_cam_img') as ws_cam:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_cam.send(json.dumps({'key': self.key}))
                    while self.running_level1:
                        img = await self.queue_img_real.get()
                        # await ws_cam.send(json.dumps(result))
                        self.logger.info(f'-------------> sending images in task 4 {img}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue

    async def task5(self):
        """
        Task to retrieve informations from server :
        _ sending image real time LD
        _ sending image real time HD
        _ sending analysed images
        """
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_get_camera_state') as ws_get_state:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_get_state.send(json.dumps({'key': self.key, 'cam_id': self.cam["id"]}))
                    while self.running_level1:
                        await asyncio.sleep(0.02)
                        state = json.loads(await ws_get_state.recv())
                        self.logger.warning(f'receiving state for camera {self.cam["name"]} -> {state}')
                        if not state.get('ping'):
                            self.rec = state["rec"]
                            self.LD = state["on_camera_LD"]
                            self.HD = state["on_camera_HD"]
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError, websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue

    async def stop(self):
        """
        Function to stop all the loop and exit asyncio.gather
        """
        self.running_level1 = False
        self.running_level2 = False
        await self.queue_frame.put('stop')
        await self.queue_result.put('stop')
        await self.queue_img_real.put('stop')
        await self.queue_img.put('stop')
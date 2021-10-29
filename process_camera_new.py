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


def detect_thread(my_net, my_class_names, frame, my_width, my_height, thresh):
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


class ProcessCamera(Thread):

    def __init__(self, cam, tlock):
        Thread.__init__(self)
        self.a = []
        self.cam = cam
        self.key = get_conf('key')
        self.running = False
        self.thread_running = False
        self.loop = asyncio.new_event_loop()
        self.logger = Logger('process_camera_thread__' + str(self.cam["id"]) + '--' + self.cam["name"],
                             level=settings.PROCESS_CAMERA_LOG).run()
        self.img_bytes = None
        self.vcap = None
        self.tlock = tlock
        self.th = cam['threshold'] * (1 - (float(cam['gap']) / 100))
        self.black_list = [i.encode() for i in settings.DARKNET_CONF['all']['RESTRICT']]
        # self.queue = asyncio.Queue(maxsize=10)

    def run(self):

        self.logger.info('running Thread')
        self.thread_running = True
        asyncio.set_event_loop(self.loop)
        while self.thread_running:
            self.running = True
            if self.cam['stream']:
                if not self.vcap or not self.vcap.isOpened():
                    rtsp = self.cam['rtsp']
                    rtsp_login = 'rtsp://' + self.cam['username'] + ':' + self.cam['password'] + '@' + rtsp.split('//')[1]
                    self.vcap = cv2.VideoCapture(rtsp_login)
                    self.logger.warning(f'openning videocapture {self.vcap} is {self.vcap.isOpened()}')
                task = [self.task1(), self.task2(), self.task3(), ]
            else:
                task = [self.task1(), self.task3(), ]
            self.loop.run_until_complete(asyncio.gather(*task))
            if self.cam['stream']:
                self.vcap.release()
                self.logger.warning('VideoCapture close on {}'.format(self.cam['name']))
            time.sleep(5)

    async def task1(self):
        bad_read = 0
        while self.running:
            t = time.time()
            if self.cam['stream']:
                frame = await grab_rtsp(self.vcap, self.loop, self.logger, self.cam)
                if frame is False:
                    self.logger.warning(f"Bad rtsp read on {self.cam['name']} videocapture is {self.vcap.isOpened()}")
                    bad_read += 1
                    if bad_read > 10:
                        self.running = False
                else:
                    bad_read = 0
                self.running = self.vcap.isOpened()
            else:
                self.logger.debug(f"before grab_http on {self.cam['name']}")
                frame = await grab_http(self.cam, self.logger)
            self.logger.info(f"ecriture de la frame {self.cam['name']} {time.strftime('%Y-%m-%d-%H-%M-%S')}"
                             f" en {time.time() - t}s")
            if bad_read == 0:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with self.tlock:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        result_dict = {}
                        for nkey, network in net.items():
                            result_dict[nkey] = executor.submit(detect_thread, network, class_names[nkey],
                                                                frame_rgb, width[nkey], height[nkey], self.th)
                if 'all' in result_dict:
                    result_darknet = [r for r in result_dict['all'].result() if r[0] not in self.black_list]
                    result_dict.pop('all')
                else:
                    result_darknet = []
                for key, partial_result in result_dict.items():
                    result_darknet += partial_result.result()
                self.logger.info(f'{self.cam["name"]} -> brut result darknet {time.time()-t}s : {result_darknet} \n')
                self.img_bytes = cv2.imencode('.jpg', frame)[1].tobytes()
                self.logger.warning(f"queue img bytes {len(self.img_bytes)}")

    async def task2(self):
        while self.running:
            await rtsp_reader(self.vcap, self.loop, self.logger)

    async def task3(self):
        while self.running:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_run_cam') as ws_cam:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_cam.send(json.dumps({'key': self.key}))
                    while True:
                        await asyncio.sleep(0.1)
                        img_bytes = self.img_bytes
                        if img_bytes:
                            await ws_cam.send(img_bytes)
                            self.logger.info(f'--------------------> sending img bytes in task 3 {len(img_bytes)}')
                            self.img_bytes = None
            except (websockets.exceptions.ConnectionClosedError, OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue

    # async def task4(self):
    #     while self.running:
    #         while True:
    #             img_bytes = self.img_bytes
    #             if img_bytes:
    #                 self.logger.debug(f'>>>>>>>>>>>>>>>>>>>>  img_bytes in task 4 is {len(img_bytes)}')
    #             await asyncio.sleep(2)

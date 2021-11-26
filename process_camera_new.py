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
from process_camera_grab import grab_http, grab_rtsp
from process_camera_utils import Result, Img, get_list_diff
import websockets
import json
from utils import get_conf
from functools import partial
import datetime


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


async def detect_thread(my_net, my_class_names, frame, my_width, my_height, thresh, loop):
    return await loop.run_in_executor(None, partial(detect_block, my_net, my_class_names, frame, my_width, my_height,
                                                    thresh))


def detect_block(my_net, my_class_names, frame, my_width, my_height, thresh):
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
                             level=settings.PROCESS_CAMERA_LOG, file=True).run()
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
        self.time_of_last_correction = 0
        self.last_result = []

    async def run(self):
        """
        Top level task to instantiate cv2 and httpx reader
        """
        self.logger.info('running Thread')
        self.running_level1 = True
        task = [self.task2(), self.task3_result(), self.task3_img(), self.task4(), self.task5()]
        if self.cam['stream']:
            task.append(self.task1_rtsp())
        else:
            task.append(self.task1_http())
        await asyncio.gather(*task)
        await asyncio.sleep(3)
        self.logger.error('EXIT ALL TASKS')

    async def task1_rtsp(self):
        """
        Task to open rtsp flux
        """
        while self.running_level1:
            if not self.vcap or not await self.loop.run_in_executor(None, self.vcap.isOpened):
                rtsp = self.cam['rtsp']
                rtsp_login = 'rtsp://' + self.cam['username'] + ':' + self.cam['password'] + '@' + rtsp.split('//')[1]
                self.vcap = await self.loop.run_in_executor(None, partial(cv2.VideoCapture, rtsp_login))
                video_opened = await self.loop.run_in_executor(None, self.vcap.isOpened)
                self.logger.warning(f'openning videocapture {self.vcap} is {video_opened}')
            self.running_level2 = True
            await asyncio.gather(self.task1_rtsp_read(), self.task1_rtsp_flush())
            await asyncio.sleep(1)
            await self.loop.run_in_executor(None, self.vcap.release)
            self.logger.warning(f'VideoCapture close on {self.cam["name"]}')
        self.logger.error('EXIT task1_rtsp TASKS')

    async def task1_rtsp_read(self):
        """
        Task to grab image in rtsp
        """
        bad_read = 0
        while self.running_level2 and self.running_level1:
            video_live = await self.loop.run_in_executor(None, self.vcap.isOpened)
            self.running_level2 = video_live
            frame = await grab_rtsp(self.vcap, self.loop, self.logger, self.cam)
            if frame is False:
                self.logger.warning(f"Bad rtsp read on {self.cam['name']} videocapture is {video_live} "
                                    f"bad_read is {bad_read}")
                bad_read += 1
                await asyncio.sleep(0.1)
                if bad_read > 10:
                    self.running_level2 = False
            else:
                bad_read = 0
            if bad_read == 0:
                # frame_rgb = await self.loop.run_in_executor(None, partial(cv2.cvtColor, frame, cv2.COLOR_BGR2RGB))
                await self.queue_frame.put(frame)
                self.logger.info(f"queue frame is {self.queue_frame.qsize()}")
        self.logger.error('EXIT task1_rtsp_read TASKS')

    async def task1_rtsp_flush(self):
        """
        task to empty the cv2 rtsp queue
        """
        while self.running_level2 and self.running_level1:
            try:
                t = time.time()
                r = await self.loop.run_in_executor(None, self.vcap.grab)
                self.logger.debug(f'grabbing rtsp {r} {time.time() - t}')
            except AttributeError:
                pass
            # await asyncio.sleep(0.001)
        self.logger.error('EXIT task1_rtsp_flush TASKS')

    async def task1_http(self):
        while self.running_level1:
            t = time.time()
            self.logger.info(f"before grab_http on {self.cam['name']}")
            frame = await grab_http(self.cam, self.logger, self.loop)
            self.logger.info(f"ecriture de la frame {self.cam['name']} {time.strftime('%Y-%m-%d-%H-%M-%S')}"
                             f" en {time.time() - t}s")
            if frame is not False:
                await self.queue_frame.put(frame)
        self.logger.error('EXIT task1_http TASKS')

    async def task2(self):
        """
        Task to analyse image with the neural network
        Multi NN can run in parallel, the limit is given by the amount of GPU RAM
        """
        while self.running_level1:
            t = time.time()
            self.logger.debug(f'before get frame queue is {self.queue_frame.qsize()}')
            frame_rgb = await self.queue_frame.get()
            if frame_rgb == 'stop':
                break
            self.logger.debug(f'frame length is {len(frame_rgb)}')
            result_dict = {}
            tasks = []
            for nkey, network in net.items():
                tasks.append(detect_thread(network, class_names[nkey], frame_rgb, width[nkey],
                                           height[nkey], self.th, self.loop))
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

            result = Result(self.cam, self.logger, result_darknet)
            result.img = Img(frame_rgb, self.loop)
            await result.process_result()
            self.logger.info(f'{self.cam["name"]} -> brut result darknet {time.time()-t}s : {result_darknet} \n')

            # --------------- check the base condition for the result to queue --------------------------------
            if self.rec:
                if await self.base_condition(result):
                    self.logger.debug('>>> Result have changed <<< ')
                    await self.queue_img.put(result)
                    self.logger.debug(f'queue img size : {self.queue_img.qsize()}')
                    await self.queue_result.put(result)
                    self.logger.debug(f'queue result size : {self.queue_result.qsize()}')
                    self.logger.warning('>>>>>>>>>>>>>>>--------- Result change send to queue '
                                        '-------------<<<<<<<<<<<<<<<<<<<<<\n')
                    self.last_result = result.filtered
                self.logger.debug('brut result process in {}s '.format(time.time() - t))

            # ---------------- if real time visualization active, queue the image ------------------------------
            if self.LD:
                result.resolution = 'LD'
                await self.queue_img_real.put(result)
                self.logger.info(f'Q_img_real LD on {self.cam["name"]} : size {self.queue_img_real.qsize()}')
            elif self.HD:
                result.resolution = 'HD'
                await self.queue_img_real.put(result)
                self.logger.info(f'Q_img_real HD on {self.cam["name"]} : size {self.queue_img_real.qsize()}')
        self.logger.error('EXIT task2 TASKS')

    async def task3_result(self):
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
                        if result == 'stop':
                            break
                        result = await result.result_to_send()
                        self.logger.info(f'result is {result}')
                        await ws_cam.send(json.dumps(result))
                        self.logger.error(f'-------------> sending result in task 3 {result}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue
        self.logger.error('EXIT task3_result TASKS')

    async def task3_img(self):
        """
        Task to upload images to server using websocket connection
        """
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_run_cam_img') as ws_cam:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_cam.send(json.dumps({'key': self.key}))
                    while self.running_level1:
                        result = await self.queue_img.get()
                        if result == 'stop':
                            break
                        name = await result.img_name()
                        await ws_cam.send(json.dumps(name))
                        self.logger.error(f'-------------> sending img name in task 3 {name}')
                        img = await result.img_to_send()
                        await ws_cam.send(img)
                        self.logger.error(f'-------------> sending img bytes in task 3 for cam {self.cam["name"]}'
                                         f' {len(img)}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue
        self.logger.error('EXIT task3_img TASKS')

    async def task4(self):
        """
        Task to upload images real time to server using websocket connection
        """
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_run_cam_img_real') as ws_cam:
                    self.logger.debug(f'the key is {self.key}')
                    await ws_cam.send(json.dumps({'key': self.key}))
                    while self.running_level1:
                        result = await self.queue_img_real.get()
                        if result == 'stop':
                            break
                        name = await result.img_name()
                        await ws_cam.send(json.dumps(name))
                        self.logger.error(f'-------------> sending img name in task 4 {name}')
                        img = await result.img_to_send()
                        await ws_cam.send(img)
                        self.logger.error(f'-------------> sending img bytes in task 4 for cam {self.cam["name"]}'
                                         f' {len(img)}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue
        self.logger.error('EXIT task4')

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
                        self.logger.info(f'receiving state for camera {self.cam["name"]} -> {state}')
                        if not state.get('ping'):
                            self.rec = state["rec"]
                            self.LD = state["on_camera_LD"]
                            self.HD = state["on_camera_HD"]
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError, websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue
        self.logger.error('EXIT task5')

    async def stop(self):
        """
        Function to stop all the loop and exit asyncio.gather
        """
        self.running_level1 = False
        self.logger.info(f'running false on cam {self.cam["name"]} ')
        await asyncio.sleep(1)
        if self.queue_frame.empty():
            await self.queue_frame.put('stop')
        else:
            await self.queue_frame.get()
        if self.queue_result.empty():
            await self.queue_result.put('stop')
        else:
            await self.queue_result.get()
        if self.queue_img_real.empty():
            await self.queue_img_real.put('stop')
        else:
            await self.queue_img_real.get()
        if self.queue_img.empty():
            await self.queue_img.put('stop')
        else:
            await self.queue_img.get()
        self.logger.error(f'end STOP')

    async def base_condition(self, result):
        """
        return True if the result has really change or if there is a correction and a time gap from last correction
        """
        new, lost = await get_list_diff(result.filtered, self.last_result, self.cam['pos_sensivity'])
        if len(new) == 0 and len(lost) == 0:
            if result.correction and time.time() - self.time_of_last_correction > 60 * 10:
                self.time_of_last_correction = time.time()
                return True
            return False
        else:
            self.time_of_last_correction = 0
            self.logger.info('Change in objects detected : new={new} lost={old}')
            return True

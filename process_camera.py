import time
import cv2
import settings
import os
import darknet as dn
from log import Logger
import asyncio
from process_camera_grab import grab_http, grab_rtsp
from process_camera_utils import Result, Img, get_list_diff
import websockets
import json
from utils import get_conf
from functools import partial
from datetime import datetime, timezone


# ------------------------------ Loading the Network defined in settings -------------------------------------------
for key, values in settings.DARKNET_CONF.items():
    if 'RT' in key:  # if using Tensor RT
        path = settings.RT_PATH
        detect_func = dn.detect_image_RT
        make_func = dn.make_image_RT
        copy_func = dn.copy_image_from_bytes_RT
        free_func = dn.free_image_RT
        values['net'] = dn.load_net_RT(os.path.join(path, values['TENSOR_PATH']).encode(),
                                       values['NB_CLASS'],
                                       values['BATCH'],
                                       values['CONF_THRESH'])
        values['class_name'] = None
        values['width'] = values['WIDTH']
        values['height'] = values['HEIGHT']
    else:
        path = settings.DARKNET_PATH
        detect_func = dn.detect_image
        make_func = dn.make_image
        copy_func = dn.copy_image_from_bytes
        free_func = dn.free_image
        values['net'] = dn.load_net_custom(os.path.join(path, values['CFG']).encode(),
                                           os.path.join(path, values['WEIGHTS']).encode(), 0, 1)
        values['meta'] = dn.load_meta(os.path.join(path, values['DATA']).encode())
        values['width'] = dn.network_width(values['net'])
        values['height'] = dn.network_height(values['net'])
        values['class_name'] = [values['meta'].names[i].decode() for i in range(values['meta'].classes)]
# --------------------------------------------------------------------------------------------------------------------


async def detect_thread(my_net, my_class_names, frame, my_width, my_height, thresh, loop):
    return await loop.run_in_executor(None, partial(detect_block, my_net, my_class_names, frame, my_width, my_height,
                                                    thresh))


def detect_block(my_net, my_class_names, frame, my_width, my_height, thresh):
    frame_resized = cv2.resize(frame, (my_width, my_height), interpolation=cv2.INTER_LINEAR)
    darknet_image = make_func(my_width, my_height, 3)
    copy_func(darknet_image, frame_resized.tobytes())
    detections = detect_func(my_net, my_class_names, darknet_image, thresh=thresh)
    # make coordinate function of initial size
    height_factor = frame.shape[0] / my_height
    width_factor = frame.shape[1] / my_width
    detections = [(r[0], float(r[1]), (r[2][0]*width_factor, r[2][1]*height_factor,
                                       r[2][2]*width_factor, r[2][3]*height_factor)) for r in detections]
    free_func(darknet_image)
    #dn.free_image(darknet_image)
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
        self.rec = False
        self.HD = False
        self.LD = False
        self.queue_frame = asyncio.Queue(maxsize=1)
        self.queue_img_real = asyncio.Queue(maxsize=settings.QUEUE_SIZE)
        self.queue_img = asyncio.Queue(maxsize=settings.QUEUE_SIZE)
        self.queue_result = asyncio.Queue(maxsize=settings.QUEUE_SIZE)
        self.time_of_last_correction = 0
        self.last_result = []
        self.camera_tasks = []
        self.frame_id = 0
        self.start_process = True

    def __str__(self):
        return f"Instance for {self.cam['name']} / {self.cam['serial_number']} / {self.cam['ip']}"

    def catch_cancel(func):
        async def inner(self):
            try:
                await func(self)
            except Exception as e:
                self.logger.error(f'EXCEPTION GENERALE DE LA TASK {e} / name-->{type(e).__name__}')
            except asyncio.exceptions.CancelledError:
                self.logger.error(f'catch cancel of task')
        return inner

    async def run(self):
        """
        Top level task to instantiate cv2 and httpx reader
        """
        self.logger.info(f'running Tasks on {self.cam}')
        self.running_level1 = True
        task = [self.task2(), self.task3_result(), self.task3_img(), self.task4(), self.task5()]
        if self.cam['stream']:
            task.append(self.task1_rtsp())
        else:
            task.append(self.task1_http())
        self.camera_tasks = [asyncio.ensure_future(t) for t in task]  # creating task to permit cancellation
        await asyncio.gather(*self.camera_tasks)
        await asyncio.sleep(3)
        self.logger.error('EXIT ALL TASKS')

    @catch_cancel
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
        self.logger.warning('EXIT task1_rtsp TASKS')

    @catch_cancel
    async def task1_rtsp_read(self):
        """
        Task to grab image in rtsp
        """
        bad_read = 0
        while self.running_level2 and self.running_level1:
            video_live = await self.loop.run_in_executor(None, self.vcap.isOpened)
            self.running_level2 = video_live
            frame, frame_id = await grab_rtsp(self.vcap, self.loop, self.logger, self.cam, self.frame_id)
            self.frame_id = frame_id
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
                self.logger.info(f"rtsp queue frame is {self.queue_frame.qsize()}")
        self.logger.warning('EXIT task1_rtsp_read TASKS')

    @catch_cancel
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
        self.logger.warning('EXIT task1_rtsp_flush TASKS')

    @catch_cancel
    async def task1_http(self):
        while self.running_level1:
            t = time.time()
            self.logger.info(f"before grab_http on {self.cam['name']}")
            frame = await grab_http(self.cam, self.logger, self.loop)
            self.logger.info(f"ecriture de la frame {self.cam['name']} {time.strftime('%Y-%m-%d-%H-%M-%S')}"
                              f" en {time.time() - t} s frame is {frame}")
            if frame is not False:
                self.logger.info(f"waiting for frame to queue / queue size is {self.queue_frame.qsize()}")
                await self.queue_frame.put(frame)
                self.logger.info(f"after queue_frame.put")
        self.logger.error('EXIT task1_http TASKS')

    @catch_cancel
    async def task2(self):
        """
        Task to analyse image with the neural network
        Multi NN can run in parallel, the limit is given by the amount of GPU RAM
        """
        while self.running_level1:
            t = time.time()
            self.logger.info(f'before get frame queue is {self.queue_frame.qsize()}')
            time_frame = datetime.now(timezone.utc)
            frame_rgb = await self.queue_frame.get()
            if frame_rgb == 'stop':
                break
            self.logger.info(f'frame length is {len(frame_rgb)}')
            result_dict = {}
            tasks = []
            for nkey, network in settings.DARKNET_CONF.items():
                tasks.append(detect_thread(network['net'], network['class_name'], frame_rgb, network['width'],
                                           network['height'], self.th, self.loop))
                result_dict[nkey] = None
            async with self.tlock:
                result_concurrent = await asyncio.gather(*tasks)
            result_dict = dict(zip(result_dict, result_concurrent))
            result_darknet = []
            for result_network, result_values in result_dict.items():
                partial_result = [r for r in result_dict[result_network] if r[0] not in
                                  settings.DARKNET_CONF[result_network]['RESTRICT']]
                result_darknet += partial_result
            #  first iteration case
            if 'result' in locals():
                last_result = result.filtered
            else:
                last_result = []
            result = Result(self.cam, self.logger, result_darknet, last_result, time_frame)
            result.img = Img(frame_rgb, self.loop)
            await result.process_result()
            self.logger.info(f'{self.cam["name"]} -> brut result darknet {time.time()-t}s : {result_darknet} \n')

            # --------------- check the base condition for the result to queue --------------------------------
            self.logger.debug(f'rec is {self.rec}')
            if self.rec:
                if await self.base_condition(result):
                    self.logger.debug('>>> Result have changed <<< ')
                    await self.queue_img.put(result)
                    self.logger.debug(f'queue img size : {self.queue_img.qsize()}')
                    await self.queue_result.put(result)
                    self.logger.debug(f'queue result size : {self.queue_result.qsize()}')
                    self.logger.warning('>>>>>>>>>>>>>>>--------- Result change send to queue '
                                        '-------------<<<<<<<<<<<<<<<<<<<<<\n')
                self.logger.debug('brut result process in {}s '.format(time.time() - t))

            # ---------------- if real time visualization active, queue the image ------------------------------
            self.logger.info(f'LD state is {self.LD}    HD is {self.HD}')
            if self.HD:
                result.resolution = 'HD'
                await self.queue_img_real.put(result)
                self.logger.info(f'Q_img_real HD on {self.cam["name"]} : size {self.queue_img_real.qsize()}')
            elif self.LD:
                await self.queue_img_real.put(result)
                self.logger.info(f'Q_img_real LD on {self.cam["name"]} : size {self.queue_img_real.qsize()}')

        self.logger.error('EXIT task2 TASKS')

    @catch_cancel
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
                        result = await result.result_to_send('rec')
                        self.logger.info(f'result is {result}')
                        await ws_cam.send(json.dumps(result))
                        self.logger.info(f'-------------> sending result in task 3 {result}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam task3 disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
        self.logger.error('EXIT task3_result TASKS')

    @catch_cancel
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
                        name = await result.img_name('rec')
                        await ws_cam.send(json.dumps(name))
                        self.logger.info(f'-------------> sending img name in task 3 {name}')
                        img = await result.img_to_send()
                        await ws_cam.send(img)
                        self.logger.info(f'-------------> sending img bytes in task 3 for cam {self.cam["name"]}'
                                         f' {len(img)}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected task3 img!! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
        self.logger.error('EXIT task3_img TASKS')

    @catch_cancel
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
                        name = await result.img_name('real_time')
                        await ws_cam.send(json.dumps(name))
                        self.logger.info(f'-------------> sending img name in task 4 {name}'
                                          f' with resolution {result.resolution}')
                        img = await result.img_to_send_real()
                        await ws_cam.send(img)
                        self.logger.info(f'-------------> sending img bytes in task 4 for cam {self.cam["name"]}'
                                          f' {len(img)}')
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                    OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                self.logger.error(f'socket _send_cam disconnected task 4!! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
        self.logger.error('EXIT task4')

    @catch_cancel
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
                self.logger.error(f'socket _send_cam disconnected task5 !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
        self.logger.error('EXIT task5')

    async def empty(self, queue):
        if queue.empty():
            try:
                await asyncio.wait_for(queue.put('stop'), timeout=1.0)
            except asyncio.TimeoutError:
                self.logger.error(f'Timeout on put {queue}')
        else:
            try:
                await asyncio.wait_for(queue.get(), timeout=1.0)
                self.logger.error(f"getting the frame to emptied the queue size is now {self.queue_frame.qsize()}")
            except asyncio.TimeoutError:
                self.logger.error(f'Timeout on get {queue}')

    async def stop(self):
        """
        Function to stop all the loop and exit asyncio.gather
        """
        self.running_level1 = False
        self.logger.info(f'running false on cam {self.cam["name"]} ')
        await asyncio.sleep(1)
        # queue have to be emptied
        await self.empty(self.queue_frame)
        await self.empty(self.queue_result)
        await self.empty(self.queue_img_real)
        await self.empty(self.queue_img)
        self.logger.error(f'end STOP')
        # in case one task not canceled properly we cancel all the tasks
        await asyncio.sleep(3)
        await self.empty(self.queue_frame)
        for t in self.camera_tasks:
            self.logger.error(f'cancel for {t}')
            t.cancel()
            self.logger.error(f'ok for cancel')
        self.logger.error(f"after cancel queue size is {self.queue_frame.qsize()}")
        await self.empty(self.queue_frame)
        self.logger.error(f'all tasks cancel for {self.cam["name"]}')

    async def base_condition(self, result):
        """
        return True if the result has really change or if there is a correction and a time gap from last correction
        """
        if self.start_process:
            self.start_process = False
            return True

        new, lost = await get_list_diff(result.filtered, result.last_objects, self.cam['pos_sensivity'])
        self.logger.info(f'BASE CONDITION : {result.filtered} / {result.last_objects} --> {new} / {lost}')
        if len(new) == 0 and len(lost) == 0:
            if result.correction and time.time() - self.time_of_last_correction > 60 * 10:
                self.time_of_last_correction = time.time()
                result.force_send = True
                return True
            return False
        else:
            self.time_of_last_correction = 0
            self.logger.info('Change in objects detected : new={new} lost={old}')
            return True

import settings
import websockets
import json
import asyncio
import pathlib
import time
from log import Logger
from datetime import datetime
from filelock import Timeout, FileLock
import hashlib

logger = Logger(__name__, level=settings.SOCKET_LOG, file=True).run()


class Client(object):
    def __init__(self, key, scan):
        self.list_cam = None
        self.key = key
        self.scan = scan
        self.key_sha = hashlib.sha256(key.encode()).hexdigest()
        self.running_level1 = True
        self.camera_file = settings.INSTALL_PATH + f'/camera/camera_from_server_{key}.json'
        self.lock = FileLock(settings.INSTALL_PATH + f'/camera/camera_from_server_{key}.json.lock', timeout=1)

    def write(self):
        write = False
        while not write:
            try:
                with self.lock:
                    with open(self.camera_file, 'w') as cam:
                        json.dump(self.list_cam, cam)
                        logger.info(f' Writing the camera from server in file -> \n'
                                    f' {json.dumps(self.list_cam, indent=4, sort_keys=True)}')
                write = True
            except Timeout:
                logger.error(f' Error Writing the camera file, file is lock')
                time.sleep(1)

    async def get_cam(self):
        async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
            await ws.send(json.dumps({'key': self.key}))
            cam = await ws.recv()
            self.list_cam = json.loads(cam)
            logger.info(f' get cam receive cam from server -> {json.dumps(self.list_cam, indent=4, sort_keys=True)}')

    async def connect(self, extern_tasks):
        tasks = [self.receive_cam(), self.get_state(), ]
        if self.scan:
            tasks.append(self.send_cam())
        await asyncio.gather(*tasks)
        # except Exception as ex:
        #     logger.warning(f' exception in CONNECT**************** / except-->{ex} / name-->{type(ex).__name__}')
        for t in extern_tasks:
            logger.warning(f'trying to shut down extern task {t}')
            await t.stop()
        logger.error(f'EXIT web_camera.py')

    async def send_cam(self):
        t1 = time.time()
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_receive_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    while self.running_level1:
                        fname = pathlib.Path(settings.INSTALL_PATH + f'/camera/camera_from_scan_{self.key}.json')
                        logger.debug(f'loop for sending new cam')
                        try:
                            t2 = fname.stat().st_ctime
                            logger.debug(f't2 is {t2} / t1 is {t1}')
                            if t2 > t1:
                                with open(settings.INSTALL_PATH + f'/camera/camera_from_scan_{self.key}.json', 'r') as cam:
                                    cameras = json.load(cam)
                                logger.warning(f'Reading camera in file -> {cameras}')
                                fname_server = pathlib.Path(settings.INSTALL_PATH +
                                                            f'/camera/camera_from_server_{self.key}.json')
                                time_from_scan = fname.stat().st_mtime
                                time_from_server = fname_server.stat().st_ctime
                                if time_from_scan == time_from_server:
                                    await ws.send(json.dumps(cameras))
                                    logger.info(f'Sending scan camera to server->{time_from_scan} / {time_from_server}')
                                t1 = time.time()
                        except FileNotFoundError:
                            logger.error(f'scan file error NOT FOUND')
                            await asyncio.sleep(30)
                        await asyncio.sleep(5)
            except (websockets.exceptions.ConnectionClosedError, OSError, ConnectionResetError,
                    websockets.exceptions.InvalidMessage)as ex:
                logger.error(f'socket _send_cam disconnected !! web camera send / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(2)
                continue
            except json.decoder.JSONDecodeError:
                logger.error(f'bad json maybe writing the file !!')
                await asyncio.sleep(1)
                continue

    async def receive_cam(self):
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_send_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    cam = await ws.recv()
                    self.list_cam = json.loads(cam)
                    logger.info(f'Receive cam from server -> {json.dumps(self.list_cam, indent=4, sort_keys=True)}')
                    await ws.send(json.dumps({'answer': True}))
                    logger.warning(f'Running level 1 is -> {self.running_level1}')
                    self.running_level1 = False
                    logger.warning(f'Running level 1 is now-> {self.running_level1}')
            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _reveive_cam disconnected !!')
                await asyncio.sleep(1)
                continue

    async def get_state(self):
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_get_state') as ws:
                    await ws.send(json.dumps({'key': self.key, 'version': 2, }))
                    while self.running_level1:
                        state = json.loads(await ws.recv())
                        ping = state.get('ping', False)
                        logger.warning(f'Receive change state -> {state}')
                        if ping:
                            with open(settings.INSTALL_PATH + f'/conf/ping_{self.key}.json', 'w') as ping:
                                json.dump({'last': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), }, ping)
                            if state['token1']:
                                with open(settings.INSTALL_PATH + f'/conf/video_{self.key_sha}.json', 'w') as f:
                                    json.dump({'token1': state['token1'], 'token2': state['token2']}, f)
                                    logger.warning(f"video.json has been written :"
                                                   f"token1: {state['token1']}, token2: {state['token2']}")
                        else:
                            # write the change for reboot and docker version
                            with open(settings.INSTALL_PATH + '/conf/docker.json', 'w') as conf_json:
                                docker_json = {key: state[key] for key in ['tunnel_port', 'docker_version', 'reboot', ]}
                                json.dump(docker_json, conf_json)
                                logger.warning(f'Receiving  json docker :  {docker_json}')

            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _get_state disconnected !!')
                await asyncio.sleep(1)
                continue

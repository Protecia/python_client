import settings
import websockets
import json
import asyncio
import pathlib
import time
from log import Logger
from utils import get_conf
from datetime import datetime

logger = Logger(__name__, level=settings.SOCKET_LOG, file=True).run()


class Client(object):
    def __init__(self):
        self.list_cam = None
        self.key = get_conf('key')
        self.E_state = None
        self.running_level1 = True

    def write(self):
        with open(settings.INSTALL_PATH + '/camera/camera_from_server.json', 'w') as cam:
            json.dump(self.list_cam, cam)

    async def get_cam(self):
        async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
            await ws.send(json.dumps({'key': self.key}))
            cam = await ws.recv()
            self.list_cam = json.loads(cam)
            logger.warning(f' get cam receive cam from server -> {self.list_cam}')

    async def connect(self, scan_state, extern_tasks):
        await asyncio.gather(self.send_cam(), self.receive_cam(), self.get_state(scan_state))
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
                        fname = pathlib.Path(settings.INSTALL_PATH + '/camera/camera_from_scan.json')
                        logger.debug(f'loop for sending new cam')
                        try:
                            t2 = fname.stat().st_ctime
                            logger.debug(f't2 is {t2} / t1 is {t1}')
                            if t2 > t1:
                                with open(settings.INSTALL_PATH + '/camera/camera_from_scan.json', 'r') as cam:
                                    cameras = json.load(cam)
                                logger.warning(f'Reading camera in file -> {cameras}')
                                await ws.send(json.dumps(cameras))
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
                    logger.warning(f'Receive cam from server -> {cam}')
                    self.list_cam = json.loads(cam)
                    await ws.send(json.dumps({'answer': True}))
                    logger.warning(f'Running level 1 is -> {self.running_level1}')
                    self.running_level1 = False
                    logger.warning(f'Running level 1 is now-> {self.running_level1}')
            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _reveive_cam disconnected !!')
                await asyncio.sleep(1)
                continue

    async def get_state(self, scan_state):
        while self.running_level1:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_get_state') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    while self.running_level1:
                        state = json.loads(await ws.recv())
                        ping = state.get('ping', False)
                        logger.warning(f'Receive change state -> {state}')
                        if ping:
                            with open(settings.INSTALL_PATH + '/conf/ping.json', 'w') as ping:
                                json.dump({'ping': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), }, ping)
                            if state['token1']:
                                with open(settings.INSTALL_PATH + '/conf/video.json', 'w') as f:
                                    json.dump({'token1': state['token1'], 'token2': state['token2']}, f)
                                    logger.warning(f"video.json has been written :"
                                                   f"token1: {state['token1']}, token2: {state['token2']}")
                        else:
                            scan_state.set() if state['scan'] else scan_state.clear()
                            logger.debug(f'scan state from server is -> {state["scan"]}')
                            # write the change for reboot and docker version
                            with open(settings.INSTALL_PATH + '/conf/docker.json', 'w') as conf_json:
                                docker_json = {key: state[key] for key in ['tunnel_port', 'docker_version', 'reboot']}
                                json.dump(docker_json, conf_json)
                                logger.warning(f'Receiving  json docker :  {docker_json}')

            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _get_state disconnected !!')
                await asyncio.sleep(1)
                continue

import settings
import websockets
import json
import asyncio
import pathlib
import time
from log import Logger
from utils import get_conf

logger = Logger(__name__, level=settings.SOCKET_LOG).run()


class Cameras(object):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.running = True
        self.list_cam = None
        self.key = get_conf('key')
        self.E_state = None

    def write(self):
        with open(settings.INSTALL_PATH + '/camera/camera_from_server.json', 'w') as cam:
            json.dump(self.list_cam, cam)

    def get_cam(self):
        return self.loop.run_until_complete(self._get_cam())

    async def _get_cam(self):
        async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
            await ws.send(json.dumps({'key': self.key}))
            cam = await ws.recv()
            self.list_cam = json.loads(cam)
            logger.warning(f' receive cam from server -> {self.list_cam}')

    def connect(self, e_state, scan_state, camera_state):
        try:
            task1 = asyncio.ensure_future(self._send_cam())
            task2 = asyncio.ensure_future(self._receive_cam())
            task3 = asyncio.ensure_future(self._get_state(e_state, scan_state, camera_state))
            done, pending = self.loop.run_until_complete(asyncio.wait([task1, task2, task3],
                                                                      return_when=asyncio.FIRST_COMPLETED, ))
            for task in pending:
                task.cancel()
            for task in done:
                cam = task.result()
        except Exception as ex:
            logger.warning(f' exception in CONNECT**************** / except-->{ex} / name-->{type(ex).__name__}')

    async def _send_cam(self):
        finish = False
        t1 = time.time()
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_receive_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    while True:
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
                logger.error(f'socket _send_cam disconnected !! / except-->{ex} / name-->{type(ex).__name__}')
                await asyncio.sleep(1)
                continue
            except json.decoder.JSONDecodeError:
                logger.error(f'bad json maybe writing the file !!')
                await asyncio.sleep(1)
                continue

    async def _receive_cam(self):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_send_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    cam = await ws.recv()
                    logger.warning(f'Receive cam from server -> {cam}')
                    self.list_cam = json.loads(cam)
                    await ws.send(json.dumps({'answer': True}))
                    finish = True
            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _reveive_cam disconnected !!')
                await asyncio.sleep(1)
                continue

    async def _get_state(self, e_state, scan_state, camera_state):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_get_state') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    while True:
                        state = json.loads(await ws.recv())
                        ping = state.get('ping', False)
                        logger.warning(f'Receive change state -> {state}')
                        if ping:
                            if state['token1']:
                                with open(settings.INSTALL_PATH + '/settings/video.json', 'w') as f:
                                    json.dump({'token1': state['token1'], 'token2': state['token2']}, f)
                                    logger.warning(f"video.json has been written :"
                                                   f"token1: {state['token1']}, token2: {state['token2']}")
                        else:
                            e_state.set() if state['rec'] else e_state.clear()
                            scan_state.set() if state['scan'] else scan_state.clear()
                            logger.debug(f'scan state from server is -> {state["scan"]} / '
                                         f'events is {scan_state.is_set()}')
                            # trigger to send real time image
                            on_camera = state['cam']
                            logger.warning(f'camera state is -> {on_camera} / events are {camera_state}')
                            for pk, value in on_camera.items():
                                [camera_state[int(pk)][index].set() if i else camera_state[int(pk)][index].clear() for
                                 index, i in enumerate(value)]

                            # write the change for reboot and docker version
                            with open(settings.INSTALL_PATH + '/conf/docker.json', 'w') as conf_json:
                                docker_json = {key: state[key] for key in ['tunnel_port', 'docker_version', 'reboot']}
                                json.dump(docker_json, conf_json)
                                logger.warning(f'Receiving  json docker :  {docker_json}')

            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _get_state disconnected !!')
                await asyncio.sleep(1)
                continue

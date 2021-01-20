import settings.settings as settings
import websockets
import json
import asyncio
import pathlib
import time
from log import Logger

logger = Logger(__name__, level=settings.SOCKET_LOG).run()


class Cameras(object):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.running = True
        self.list_cam = None
        self.key = settings.CONF.get_conf('key')
        self.E_state = None

    def write(self):
        with open(settings.INSTALL_PATH + '/camera/camera_from_server.json', 'w') as cam:
            dict_cam = {}
            for c in self.list_cam:
                if c['ip'] not in dict_cam:
                    dict_cam[c['ip']] = c.copy()
                    dict_cam[c['ip']]['uri'] = [(c['url'], c['rtsp'], c['index_uri']), ]
                    key_to_remove = ('rtsp', 'url', 'on_camera_LD', 'on_camera_HD', 'ip')
                    for k in key_to_remove:
                        dict_cam[c['ip']].pop(k, None)
                else:
                    dict_cam[c['ip']]['uri'].append((c['url'], c['rtsp'], c['index_uri']))
            json.dump(dict_cam, cam)

    def active_cam(self):
        return [cam for cam in self.list_cam if cam['active_automatic']]

    def get_cam(self):
        return self.loop.run_until_complete(self._get_cam())

    async def _get_cam(self):
        async with websockets.connect(settings.SERVER_WS+'ws') as ws:
            await ws.send(json.dumps({'key': self.key}))
            cam = await ws.recv()
            self.list_cam = json.loads(cam)
            logger.warning(f' receive cam from server -> {self.list_cam}')
            await ws.send(json.dumps({'answer': True}))

    def connect(self, e_state):
        task1 = asyncio.ensure_future(self._send_cam())
        task2 = asyncio.ensure_future(self._receive_cam())
        task3 = asyncio.ensure_future(self._get_state(e_state))
        done, pending = self.loop.run_until_complete(asyncio.wait([task1, task2, task3],
                                                                  return_when=asyncio.FIRST_COMPLETED,))
        for task in pending:
            task.cancel()
        for task in done:
            cam = task.result()

    async def _send_cam(self):
        finish = False
        t1 = time.time()
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_receive_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    while True:
                        fname = pathlib.Path('camera/camera_from_scan.json')
                        t2 = fname.stat().st_ctime
                        if t2 > t1:
                            with open(settings.INSTALL_PATH + '/camera/camera_from_scan.json', 'r') as cam:
                                cameras = json.load(cam)
                            logger.warning(f'Reading camera in file -> {cameras}')
                            await ws.send(json.dumps(cameras))
                            t1 = time.time()
                        await asyncio.sleep(5)
            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _send_cam disconnected !!')
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

    async def _get_state(self, e_state):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_get_state') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    while True:
                        state = json.loads(await ws.recv())
                        logger.warning(f'Receive change state -> {state}')
                        e_state.set() if state['rec'] else e_state.clear()
            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket _get_state disconnected !!')
                await asyncio.sleep(1)
                continue

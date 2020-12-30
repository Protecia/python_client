import settings.settings as settings
import websockets
import json
import asyncio
from log import Logger
import scan_camera as sc
import socket

logger = Logger(__name__, level=settings.SOCKET_LOG).run()


class Cameras(object):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.running = True
        self.list = None
        with open(settings.INSTALL_PATH + '/settings/conf.json', 'r') as conf_json:
            data = json.load(conf_json)
        self.key = data["key"]

    def write(self):
        with open(settings.INSTALL_PATH + '/camera/camera.json', 'w') as cam:
            json.dump(self.list, cam)

    def get_cam(self):
        return self.loop.run_until_complete(self.__async__get_cam())

    async def __async__get_cam(self):
        async with websockets.connect(settings.SERVER_WS+'ws') as ws:
            await ws.send(json.dumps({'key': self.key, 'force': True}))
            cam = await ws.recv()
            self.list = json.loads(cam)

    def wait_cam(self):
        return self.loop.run_until_complete(self.__async__wait_cam())

    async def __async__wait_cam(self):
        async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
            await ws.send(json.dumps({'key': self.key, 'force': False}))
            cam = await ws.recv()
            self.list = json.loads(cam)
            await ws.send(json.dumps({'answer': True}))

    async def wait_cam_loop(self):
        async with websockets.connect(settings.SERVER_WS+'ws') as ws:
            while True:
                await ws.send(json.dumps({'key': self.key, 'force': False}))
                cam = await ws.recv()
                self.list = json.loads(cam)
                await ws.send(json.dumps({'answer': True}))

    def cam_connect(self):
        return self.loop.run_until_complete(self.__async__cam_task())

    async def __async__cam_task(self):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
                    await ws.send(json.dumps({'key': self.key, 'force': False}))
                    task1 = asyncio.ensure_future(self.coro1(ws))
                    task2 = asyncio.ensure_future(self.coro2(ws))
                    task3 = asyncio.ensure_future(self.coro3(ws))
                    done, pending = await asyncio.wait([task1, task2, task3], return_when=asyncio.FIRST_COMPLETED, )
                    finish = True
            except socket.gaierror:
                logger.warning(f'socket disconnected !!')
                continue
        for task in pending:
            task.cancel()
        for task in done:
            cam = task.result()
        self.list = json.loads(cam)
        await ws.send(json.dumps({'answer': True}))

    async def coro1(self, ws):
        cam = await ws.recv()
        return cam

    async def coro2(self, ws):
        while True:
            dict_cam = await sc.run()
            await ws.send(json.dumps(dict_cam))

            #dict_cam = await ping_network()
            #await ws.send(json.dumps(dict_cam))
            await asyncio.sleep(60)

    async def coro3(self, ws):
        while True:
            try:
                pong = await ws.ping()
                await asyncio.wait_for(pong, timeout=5)
                logger.warning(f'Ping ok')
                await asyncio.sleep(2)
                continue
            except:
                logger.warning(f'BAD ping')


import settings.settings as settings
import websockets
import json
import asyncio
from log import Logger
import scan_camera as sc

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
            await ws.send(json.dumps({'answer': True}))

    def connect(self):
        task1 = asyncio.ensure_future(self.__async__send_cam())
        task2 = asyncio.ensure_future(self.__async__receive_cam())
        done, pending = self.loop.run_until_complete(asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED,))
        for task in pending:
            task.cancel()
        for task in done:
            cam = task.result()

    def send_cam(self):
        return self.loop.run_until_complete(self.__async__send_cam())

    async def __async__send_cam(self):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_receive_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, 'force': False}))
                    while True:
                        logger.warning(f'START OF SCAN CAMERA')
                        dict_cam = await sc.run()
                        logger.warning(f'END OF SCAN CAMERA')
                        # await ws.send(json.dumps(dict_cam))
                        # logger.info(f'sending the scan camera to the server : {dict_cam}')
                        # dict_cam = await ping_network()
                        await ws.send(json.dumps({'cam': 'ollé'}))
                        await asyncio.sleep(10)
            except websockets.exceptions.ConnectionClosedError:
                logger.warning(f'socket disconnected !!')
                continue

    def receive_cam(self):
        return self.loop.run_until_complete(self.__async__receive_cam())

    async def __async__receive_cam(self):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_receive_cam') as ws:
                    cam = await ws.recv()
                    finish = True
            except websockets.exceptions.ConnectionClosedError:
                logger.warning(f'socket disconnected !!')
                continue





    async def __async__cam_task(self):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
                    await ws.send(json.dumps({'key': self.key, 'force': False}))
                    task1 = asyncio.ensure_future(self.coro_recv(ws))
                    task2 = asyncio.ensure_future(self.coro_send(ws))
                    #task3 = asyncio.ensure_future(self.coro3(ws))
                    done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED, )
                    finish = True
            except websockets.exceptions.ConnectionClosedError:
                logger.warning(f'socket disconnected !!')
                continue
        for task in pending:
            task.cancel()
        for task in done:
            cam = task.result()
        self.list = json.loads(cam)
        await ws.send(json.dumps({'answer': True}))

    async def coro_recv(self, ws):
        cam = await ws.recv()
        return cam

    async def coro_send(self, ws):
        while True:
            logger.warning(f'START OF SCAN CAMERA')
            dict_cam = await sc.run()
            logger.warning(f'END OF SCAN CAMERA')
            #await ws.send(json.dumps(dict_cam))
            #logger.info(f'sending the scan camera to the server : {dict_cam}')
            #dict_cam = await ping_network()
            await ws.send(json.dumps({'canal': 'receive_cam', 'cam': 'ollé'}))
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


import settings.settings as settings
import websockets
import json
import asyncio


class Cameras(object):
    def __init__(self, lock):
        self.loop = asyncio.get_event_loop()
        self.running = True
        self.list = None
        self.lock = lock
        with open(settings.INSTALL_PATH + '/settings/conf.json', 'r') as conf_json:
            data = json.load(conf_json)
        self.key = data["key"]

    def write(self):
        with self.lock:
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

    def test_task(self):
        self.loop.run_until_complete(self.__async__test_task())

    async def __async__test_task(self):
        async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
            task1 = asyncio.ensure_future(self.coro1())
            task2 = asyncio.ensure_future(self.coro2())
            done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED, )
            for task in pending:
                task.cancel()

    async def coro1(self):
        await asyncio.sleep(10)

    async def coro2(self):
        await asyncio.sleep(5)

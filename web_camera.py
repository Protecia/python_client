import settings.settings as settings
import websockets
import json
import asyncio
import scan_camera as sc


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
        async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
            loop = True
            while loop:
                task1 = asyncio.ensure_future(self.coro1(ws))
                task2 = asyncio.ensure_future(self.coro2(ws))
                done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED, )
                for task in done:
                    result = task.result()
                    if result == 'task1':
                        loop = False
                for task in pending:
                    task.cancel()
        return result

    async def coro1(self, ws):
        await ws.send(json.dumps({'key': self.key, 'force': False}))
        cam = await ws.recv()
        self.list = json.loads(cam)
        await ws.send(json.dumps({'answer': True}))
        return 'task1'

    async def coro2(self, ws):
        await sc.run()
        await asyncio.sleep(60)
        return 'task2'

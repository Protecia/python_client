from log import Logger
import settings.settings as settings
import websockets
import json
import asyncio


class Cameras(object):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.running = True
        self.camera = None

    def get_cam(self):
        return self.loop.run_until_complete(self.__async__get_cam())

    async def __async__get_cam(self):
        async with websockets.connect(settings.SERVER_WS+'ws') as ws:
            await ws.send(json.dumps({'key': settings.KEY, 'force': True}))
            self.camera = await ws.recv()

    def wait_cam(self):
        return self.loop.run_until_complete(self.__async__wait_cam())

    async def __async__wait_cam(self):
        async with websockets.connect(settings.SERVER_WS + 'ws') as ws:
            await ws.send(json.dumps({'key': settings.KEY, 'force': False}))
            self.camera = await ws.recv()
            await ws.send(json.dumps({'answer': True}))

    async def wait_cam_loop(self):
        async with websockets.connect(settings.SERVER_WS+'ws') as ws:
            while True:
                await ws.send(json.dumps({'key': settings.KEY, 'force': False}))
                self.camera = await ws.recv()
                await ws.send(json.dumps({'answer': True}))



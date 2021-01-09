import settings.settings as settings
import websockets
import json
import asyncio
from log import Logger

logger = Logger(__name__, level=settings.SOCKET_LOG).run()


class Cameras(object):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.running = True
        self.list = None
        self.key = settings.CONF.get_conf('key')

    def write(self):
        with open(settings.INSTALL_PATH + '/camera/camera_from_server.json', 'w') as cam:
            dict_cam = {}
            for c in self.list:
                if c['ip'] not in dict:
                    dict_cam['ip'] = c
                    dict_cam['ip']['uri'] = [(c['url'], c['rtsp'], c['index_uri']), ]
                    key_to_remove = ('rtsp', 'url', 'on_camera_LD', 'on_camera_HD', 'ip')
                    for k in key_to_remove:
                        dict_cam['ip'].pop(k, None)
                else:
                    dict_cam['ip']['uri'].append((c['url'], c['rtsp'], c['index_uri']))
            json.dump(dict_cam, cam)

    def get_cam(self):
        return self.loop.run_until_complete(self.__async__get_cam())

    async def __async__get_cam(self):
        async with websockets.connect(settings.SERVER_WS+'ws') as ws:
            await ws.send(json.dumps({'key': self.key}))
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

    async def __async__send_cam(self):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_receive_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    while True:
                        await asyncio.sleep(20)
                        with open(settings.INSTALL_PATH + '/camera/camera_from_scan.json', 'r') as cam:
                            cameras = json.load(cam)
                        logger.warning(f'Reading camera in file -> {cameras}')
                        await ws.send(json.dumps(cameras))
                        await asyncio.sleep(settings.SCAN_INTERVAL)
            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket disconnected !!')
                await asyncio.sleep(1)
                continue

    async def __async__receive_cam(self):
        finish = False
        while not finish:
            try:
                async with websockets.connect(settings.SERVER_WS + 'ws_send_cam') as ws:
                    await ws.send(json.dumps({'key': self.key, }))
                    cam = await ws.recv()
                    self.list = json.loads(cam)
                    await ws.send(json.dumps({'answer': True}))
                    finish = True
            except (websockets.exceptions.ConnectionClosedError, OSError):
                logger.error(f'socket disconnected !!')
                await asyncio.sleep(1)
                continue

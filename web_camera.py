import settings.settings as settings
import requests
from onvif import ONVIFCamera
from onvif.exceptions import ONVIFError
from log import Logger
import time
import socket
import psutil
import netifaces as ni
import xml.etree.ElementTree as eT
import re
from urllib3.exceptions import HeaderParsingError
import subprocess
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
            await ws.send(json.dumps({'key': self.key, 'force': False}))
            task1 = asyncio.ensure_future(self.coro1(ws))
            task2 = asyncio.ensure_future(self.coro2(ws))
            task3 = asyncio.ensure_future(self.coro3(ws))
            done, pending = await asyncio.wait([task1, task2, task3], return_when=asyncio.FIRST_COMPLETED, )
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
        logger.warning(f'retrieve cam : {self.list}')
        users_dict = dict(set([(c['username'], c['password']) for c in self.list]))
        logger.warning(f'retrieve user and pass : {users_dict}')
        while True:
            #dict_cam = await sc.run()
            #await ws.send(json.dumps(dict_cam))
            await ws.send(json.dumps({'answer': True}))
            addrs = psutil.net_if_addrs()
            box = [ni.ifaddresses(i)[ni.AF_INET][0]['addr'] for i in addrs if i.startswith('e')]
            network = ['.'.join(i.split('.')[:-1]) for i in box]
            list_task = []
            std = {}
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

    async def run(self, cmd):
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        # print(f'[{cmd!r} exited with {proc.returncode}]')
        if stdout:
            return stdout.decode("utf-8")
        else:
            return None

    async def ping_network(self):
        addrs = psutil.net_if_addrs()
        box = [ni.ifaddresses(i)[ni.AF_INET][0]['addr'] for i in addrs if i.startswith('e')]
        network = ['.'.join(i.split('.')[:-1]) for i in box]
        std = {}
        for net in network:
            list_task = []
            for i in range(1, 255):
                list_task.append(self.run(f'ping {net}.{i} -c 1 -w 5 >/dev/null && echo "{net}.{i}"'))
            done, _ = await asyncio.wait(list_task)
            for ip in [i.result().decode().rstrip() for i in done if i.result()]:
                if ip not in box:
                    std[ip] = str(settings.CONF.get_conf('scan_camera'))
        return std

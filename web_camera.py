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
        async with websockets.connect(settings.SERVER_WS + 'ws', ping_interval=None) as ws:
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

            dict_cam = await ping_network()
            await ws.send(json.dumps(dict_cam))
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


async def run_cmd(cmd):
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


async def ping_network():
    addrs = psutil.net_if_addrs()
    box = [ni.ifaddresses(i)[ni.AF_INET][0]['addr'] for i in addrs if i.startswith('e')]
    network = ['.'.join(i.split('.')[:-1]) for i in box]
    std = {}
    for net in network:
        list_task = []
        for i in range(1, 255):
            list_task.append(run_cmd(f'ping {net}.{i} -c 1 -w 5 >/dev/null && echo "{net}.{i}"'))
        done, _ = await asyncio.wait(list_task)
        for ip in [i.result().rstrip() for i in done if i.result()]:
            if ip not in box:
                std[ip] = str(settings.CONF.get_conf('scan_camera'))
    return std


def ws_discovery(repeat, wait):
    """Discover cameras on network using ws discovery.
    Returns:
        Dictionnary: { ip : port } of cameras found on network.
    """
    addrs = psutil.net_if_addrs()
    try:
        ip_list = [ni.ifaddresses(i)[ni.AF_INET][0]['addr'] for i in addrs if i.startswith('e')]
        with open('soap.xml') as f:
            soap_xml = f.read()
        mul_ip = "239.255.255.250"
        mul_port = 3702
        ret = []
        dcam = {}
        for i in range(repeat):
            for ip in ip_list:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
                s.bind((ip, mul_port))
                s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                             socket.inet_aton(mul_ip) + socket.inet_aton(ip))
                s.setblocking(False)
                s.sendto(soap_xml.encode(), (mul_ip, mul_port))
                time.sleep(3)
                while True:
                    try:
                        data, address = s.recvfrom(65535)
                        # time.sleep(1)
                        # print(address)
                        ret.append(data)
                    except BlockingIOError:
                        pass
                        break
                # s.shutdown()
                s.close()
            for rep in ret:
                xml = eT.fromstring(rep)
                url = [i.text for i in xml.iter('{http://schemas.xmlsoap.org/ws/2005/04/discovery}XAddrs')]
                if url:
                    url = url[0]
                    ip = re.search('http://(.*):', url).group(1)
                    port = re.search('[0-9]+:([0-9]+)/', url).group(1)
                    dcam[ip] = port
            if not i+1 == repeat:
                time.sleep(wait)
    except (KeyError, OSError):
        return {}
    logger.info('scan camera : {}'.format(dcam))
    return dcam


def get_onvif_uri(ip, port, user, passwd):
    """Find uri to request the camera.
    Returns:
        List: List of uri found for the camera.
    """
    wsdir = '/usr/local/lib/python3.6/site-packages/wsdl/'
    try:
        cam = ONVIFCamera(ip, port, user, passwd, wsdir)
        info = cam.devicemgmt.GetDeviceInformation()
        media_service = cam.create_media_service()
        profiles = media_service.GetProfiles()
        obj = media_service.create_type('GetStreamUri')
        uri = []
    except (ONVIFError, HeaderParsingError):
        return None
    for canal in profiles:
        try:
            obj.ProfileToken = canal.token
            obj.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
            rtsp = media_service.GetStreamUri(obj)['Uri']
        except (ONVIFError, HeaderParsingError):
            rtsp = None
            pass
        try:
            obj = media_service.create_type('GetSnapshotUri')
            obj.ProfileToken = canal.token
            http = media_service.GetSnapshotUri(obj)['Uri']  # .split('?')[0]
        except (ONVIFError, HeaderParsingError):
            http = None
            pass
        uri.append([http, rtsp])
    return info, uri


def check_auth(http, user, passwd):
    auth = {'B': requests.auth.HTTPBasicAuth(user, passwd), 'D': requests.auth.HTTPDigestAuth(user, passwd)}
    for t, a in auth.items():
        for i in range(4):
            for url in http:
                try:
                    r = requests.get(url, auth=a, stream=False, timeout=1)
                    logger.info(f'request on {url}')
                    if r.ok:
                        logger.info(f'request  on camera OK for {http} / {user} / {passwd} / {t}')
                        return t
                except (requests.exceptions.ConnectionError, requests.Timeout,
                        requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema):
                    time.sleep(0.5)
                    pass
    return False


def check_cam(cam_ip_dict, users_dict):
    """Test connection for all ip/port.
        Returns:
            List: List of camera dict that are active.
        """
    dict_cam = {}
    for ip, port in cam_ip_dict.items():
        dict_cam[ip] = {'name': 'unknow', 'port_onvif': port, 'active_automatic': False,
                        'uri': [('http://0.0.0.0', 'rtsp://0.0.0.0'), ]}
        for user, passwd in users_dict.items():
            logger.info(f'testing onvif cam with ip:{ip} port:{port} user:{user} pass:{passwd}')
            onvif = get_onvif_uri(ip, port, user, passwd)
            if onvif:
                info, uri = onvif
                logger.info(f'onvif OK for {ip} / {port} / {user} / {passwd} ')
                dict_cam[ip]['brand'] = info['Manufacturer']
                dict_cam[ip]['model'] = info['Model']
                dict_cam[ip]['uri'] = [(i[0], i[1].split('//')[0] + '//' + user + ':' + passwd + '@' +
                                        i[1].split('//')[1]) for i in uri]
                dict_cam[ip]['username'] = user
                dict_cam[ip]['active_automatic'] = True
                dict_cam[ip]['password'] = passwd
                dict_cam[ip]['wait_for_set'] = False
                auth = check_auth(uri[0][0], user, passwd)
                if auth:
                    dict_cam[ip]['auth_type'] = auth
    return dict_cam


async def scan_camera():
    with open(settings.INSTALL_PATH+'/camera/camera.json', 'r') as out:
        cameras = json.load(out)
    users_dict = dict(set([(c['username'], c['password']) for c in cameras]))
    cam_ip_dict = dict([(c['ip'], c['port_onvif']) for c in cameras])
    if settings.CONF.get_conf('scan_camera') != 0:
        detected_cam = ping_network()
    else:
        detected_cam = ws_discovery(2, 20)
    cam_ip_dict.update(detected_cam)
    dict_cam = await check_cam(cam_ip_dict, users_dict)
    return dict_cam

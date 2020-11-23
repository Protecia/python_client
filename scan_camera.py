# -*- coding: utf-8 -*-
"""
Created on Sat Dec  7 11:48:41 2019

@author: julien
"""

import json
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

logger = Logger('scan_camera', level=settings.SCAN_LOG).run()


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
        rtsp = []
        http = []
    except (ONVIFError, HeaderParsingError):
        return None
    for canal in profiles:
        try:
            obj.ProfileToken = canal.token
            obj.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
            rtsp.append(media_service.GetStreamUri(obj)['Uri'])
        except (ONVIFError, HeaderParsingError):
            pass
        try:
            obj = media_service.create_type('GetSnapshotUri')
            obj.ProfileToken = canal.token
            http.append(media_service.GetSnapshotUri(obj)['Uri'])  # .split('?')[0]
        except (ONVIFError, HeaderParsingError):
            pass
    return info, rtsp, http


def check_cam(cam_ip_dict, users_dict):
    """Test connection for all ip/port.
        Returns:
            List: List of camera dict that are active.
        """
    dict_cam = {}
    for ip, port in cam_ip_dict.items():
        dict_cam[ip] = {'name': 'unknow', 'port_onvif': port, 'active_automatic': False}
        for user, passwd in users_dict.items():
            logger.info(f'testing onvif cam with ip:{ip} port:{port} user:{user} pass:{passwd}')
            onvif = get_onvif_uri(ip, port, user, passwd)
            if onvif:
                info, rtsp, http = onvif
                auth = {'B': requests.auth.HTTPBasicAuth(user, passwd), 'D': requests.auth.HTTPDigestAuth(user, passwd)}
                for t, a in auth.items():
                    for i in range(4):
                        try:
                            r = requests.get(http.split('?')[0], auth=a, stream=False, timeout=1)
                            logger.info('request on {}'.format(http.split('?')[0]))
                            if r.ok:
                                logger.info(f'request  on camera OK for {ip} / {user} / {passwd} / {t}')
                                dict_cam[ip]['brand'] = info['Manufacturer']
                                dict_cam[ip]['model'] = info['Model']
                                dict_cam[ip]['url'] = http
                                dict_cam[ip]['auth_type'] = t
                                dict_cam[ip]['username'] = user
                                dict_cam[ip]['active_automatic'] = True
                                dict_cam[ip]['password'] = passwd
                                dict_cam[ip]['wait_for_set'] = False
                                dict_cam[ip]['rtsp'] = [i.split('//')[0]+'//'+user+':'+passwd+'@'+i.split('//')[1]
                                                        for i in rtsp]
                                break
                        except (requests.exceptions.ConnectionError, requests.Timeout,
                                requests.exceptions.MissingSchema):
                            time.sleep(0.5)
                            pass
    return dict_cam


def set_cam(cam):
    cam_json = {'key': settings.CONF.key, 'cam': cam}
    try:
        r = requests.post(settings.SERVER+"setCam", json=cam_json, timeout=40)
        logger.info('set cam {}'.format(cam))
        s = json.loads(r.text)
        return s
    except (requests.exceptions.ConnectionError, json.decoder.JSONDecodeError, requests.Timeout) as ex:
        logger.error('exception in setCam : {}'.format(ex))
        pass
    return False


def run(period, lock):
    while True:
        with lock:
            with open(settings.INSTALL_PATH+'/camera/camera.json', 'r') as out:
                cameras = json.loads(out.read())
        users_dict = dict(set([(c['username'], c['password']) for c in cameras]))
        cam_ip_dict = dict([(c['ip'], c['port_on_vif']) for c in cameras]) + ws_discovery(2, 20)
        dict_cam = check_cam(cam_ip_dict, users_dict)
        set_cam(dict_cam)
        time.sleep(period)

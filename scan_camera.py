# -*- coding: utf-8 -*-
"""
Created on Sat Dec  7 11:48:41 2019

@author: julien
"""

import json
import settings
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
import asyncio
import subprocess
from utils import get_conf

logger = Logger('scan_camera', level=settings.SCAN_LOG).run()


def ping_network():
    addrs = psutil.net_if_addrs()
    box = [ni.ifaddresses(i)[ni.AF_INET][0]['addr'] for i in addrs if i.startswith('e')]
    network = ['.'.join(i.split('.')[:-1]) for i in box]
    list_task = []
    std = {}
    for net in network:
        for i in range(1, 255):
            bash_cmd = f'ping {net}.{i} -c 1 -w 5 >/dev/null && echo "{net}.{i}"'
            list_task.append(subprocess.Popen(bash_cmd, shell=True, stdout=subprocess.PIPE))
        for proc in list_task:
            outs, errs = proc.communicate()
            if outs:
                ip = outs.decode().rstrip()
                if ip not in box:
                    std[ip] = {'port_onvif': get_conf('scan_camera')}
    return std


def ws_discovery(repeat, wait):
    """Discover cameras on network using ws discovery.
    Returns:
        Dictionnary: { ip : port } of cameras found on network.
    """
    addrs = psutil.net_if_addrs()
    try:
        ip_list = [ni.ifaddresses(i)[ni.AF_INET][0]['addr'] for i in addrs if i.startswith('e')]
        logger.info(f'ip of the box is :{ip_list} ')
        with open('/NNvision/python_client/soap.xml') as f:
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
                logger.info(f'Sending broadcast onvif')
                time.sleep(3)
                while True:
                    try:
                        data, address = s.recvfrom(65535)
                        logger.info(f'reading onvif answer {data}')
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
                    dcam[ip] = {'port_onvif': port}
            if not i+1 == repeat:
                time.sleep(wait)
    except (KeyError, OSError) as ex:
        logger.error(f'exception in ws_discovery : except-->{ex} / name-->{type(ex).__name__}')
        return {}
    logger.info('scan camera : {}'.format(dcam))
    return dcam


async def onvif_cam(ip, port, user, passwd, wsdir):
    return ONVIFCamera(ip, port, user, passwd, wsdir)


async def get_onvif_uri(ip, port, user, passwd):
    """Find uri to request the camera.
    Returns:
        List: List of uri found for the camera.
    """
    wsdir = settings.WSDIR
    try:
        cam = await asyncio.wait_for(onvif_cam(ip, port, user, passwd, wsdir), timeout=1.0)
        info = cam.devicemgmt.GetDeviceInformation()
        media_service = cam.create_media_service()
        profiles = media_service.GetProfiles()
        obj = media_service.create_type('GetStreamUri')
        uri = []
    except (ONVIFError, HeaderParsingError, asyncio.TimeoutError):
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


def check_auth(dict_cam_ip, user, passwd, auth):
    check = False
    for t, a in auth.items():
        for i in range(4):
            for url in dict_cam_ip['uri'].values():
                http = url['http']
                try:
                    logger.info(f'before request on {http}')
                    r = requests.get(http, auth=a, stream=True, timeout=10)
                    logger.info(f'after request on {http}')
                    logger.info(f'request  on camera is {r.ok} for {http} / {user} / {passwd} / {t}')
                    if r.ok:
                        dict_cam_ip['auth_type'] = t
                        dict_cam_ip['wait_for_set'] = False
                        dict_cam_ip['username'] = user
                        dict_cam_ip['password'] = passwd
                        check = True
                        break
                except (requests.exceptions.ConnectionError, requests.Timeout,
                        requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema):
                    time.sleep(0.5)
                    pass
            if check:
                break
        if check:
            break
    # result of the check chang the camera status
    dict_cam_ip['active_automatic'] = True if check else False


def check_cam(cam_ip_dict, users_dict):
    """Test connection for all ip/port.
        Returns:
            List: List of camera dict that are active.
        """
    dict_cam = {}
    for ip, cam in cam_ip_dict.items():
        dict_cam[ip] = cam
        http = cam.get('uri', None)
        if http:  # this is a known cam, so test
            logger.info(f'testing old cam with http:{http} user:{cam["username"]} pass:{cam["password"]}')
            auth = {'B': requests.auth.HTTPBasicAuth(cam["username"], cam["password"]),
                    'D': requests.auth.HTTPDigestAuth(cam["username"], cam["password"])}
            # auth = {cam['auth_type']: auth[cam['auth_type']]}
            check_auth(dict_cam[ip], cam["username"], cam["password"], auth)
        else:  # this is a new cam
            dict_cam[ip] = {'name': 'unknow', 'port_onvif': cam["port_onvif"],
                            'from_client': True, 'uri': {}}
            port = cam["port_onvif"]
            onvif_answer = False
            for user, passwd in users_dict.items():
                logger.info(f'testing onvif cam with ip:{ip} port:{port} user:{user} pass:{passwd}')
                loop = asyncio.get_event_loop()
                onvif = loop.run_until_complete(get_onvif_uri(ip, port, user, passwd))
                logger.info(f'onvif answer is {onvif}')
                if onvif:
                    onvif_answer = True
                    info, uri = onvif
                    logger.info(f'onvif OK for {ip} / {port} / {user} / {passwd} ')
                    dict_cam[ip]['brand'] = info['Manufacturer']
                    dict_cam[ip]['model'] = info['Model']
                    dict_cam[ip]['serial_number'] = info['SerialNumber']
                    # need to check if serial number is already know to find old cam with ip change --> check on server
                    for count, i in enumerate(uri):
                        dict_cam[ip]['uri'][count] = {'http': i[0], 'rtsp': i[1]}
                    auth = {'B': requests.auth.HTTPBasicAuth(user, passwd),
                            'D': requests.auth.HTTPDigestAuth(user, passwd)}
                    check_auth(dict_cam[ip], user, passwd, auth)
            if not onvif_answer:
                dict_cam[ip]['active_automatic'] = False
    return dict_cam


def run(wait, scan_state):
    while True:
        try:
            with open(settings.INSTALL_PATH+'/camera/camera_from_server.json', 'r') as out:
                cam_ip_dict = json.load(out)
            users_dict = {cam['username']: cam['password'] for cam in cam_ip_dict.values()}
            if get_conf('scan_camera') != 0:
                detected_cam = ping_network()
            else:
                detected_cam = ws_discovery(2, 20)
                logger.debug(f'ws disvovery cam <-  {detected_cam}')
            detected_cam.update(cam_ip_dict)
            logger.info(f'updated detected_cam <-  {detected_cam}')
            cam_ip_dict.update(detected_cam)
            dict_cam = check_cam(cam_ip_dict, users_dict)
            with open(settings.INSTALL_PATH+'/camera/camera_from_scan.json', 'w') as out:
                json.dump(dict_cam, out)
            logger.warning(f'Writing scan camera in file <-  {dict_cam} / scan_state is {scan_state.is_set()}')
            scan_state.wait()
            time.sleep(wait)
        except Exception as ex:
            logger.error(f'exception in scan_camera : except-->{ex} / name-->{type(ex).__name__}')
            time.sleep(1)
            continue


# only for testing and launching independant scan_camera
if __name__ == '__main__':
    from multiprocessing import Event as pEvent
    scan = pEvent()
    # initial scan state :
    if get_conf('scan'):
        scan.set()
    run(20, scan)

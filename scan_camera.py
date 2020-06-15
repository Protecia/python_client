# -*- coding: utf-8 -*-
"""
Created on Sat Dec  7 11:48:41 2019

@author: julien
"""

#import wsdiscovery
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
import xml.etree.ElementTree as ET
import re

logger = Logger('scan_camera', level=settings.SCAN_LOG).run()

'''
def wsDiscovery():
    """Discover cameras on network using onvif discovery.
    Returns:
        List: List of ips found in network.
    """
    wsd = wsdiscovery.WSDiscovery()
    wsd.start()
    ret = wsd.searchServices()
    dcam = {}
    for service in ret:
        scheme = service.getXAddrs()[0]
        if 'onvif' in scheme :
            dcam[scheme.split('/')[2].split(':')[0]] = scheme.split('/')[2].split(':')[1]
    wsd.stop()
    return dcam
'''

def wsDiscovery(repeat, wait):
    """Discover cameras on network using ws discovery.
    Returns:
        List: List of ips found in network.
    """
    addrs = psutil.net_if_addrs()
    try :
        ip_list = [ni.ifaddresses(i)[ni.AF_INET][0]['addr'] for i in addrs if i.startswith('e')]
        with open('soap.xml') as f:
            soap_xml = f.read()
        mul_ip = "239.255.255.250"
        mul_port = 3702
        ret = []
        dcam = {}
        for i in range(repeat):
            for ip in ip_list :
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
                        #time.sleep(1)
                        #print(address)
                        ret.append(data)
                    except BlockingIOError :
                        pass
                        break
                #s.shutdown()
                s.close()
            for rep in ret:
                xml = ET.fromstring(rep)
                url = [ i.text for i in xml.iter('{http://schemas.xmlsoap.org/ws/2005/04/discovery}XAddrs') ]
                if url :
                    url = url[0]
                    ip = re.search('http://(.*):',url).group(1)
                    port = re.search('[0-9]+:([0-9]+)/', url).group(1)
                    dcam[ip]=port
            if not i+1==repeat:
                time.sleep(wait)
    except (KeyError, OSError) :
        return False
    logger.info('scan camera : {}'.format(dcam))
    return dcam

def getOnvifUri(ip,port,user,passwd):
    """Find uri to request the camera.
    Returns:
        List: List of uri found for the camera.
    """
    wsdir =  '/usr/local/lib/python3.6/site-packages/wsdl/'
    try :
        cam = ONVIFCamera(ip, port, user, passwd, wsdir)
        info = cam.devicemgmt.GetDeviceInformation()
        media_service = cam.create_media_service()
        profiles = media_service.GetProfiles()
        obj = media_service.create_type('GetStreamUri')
        obj.ProfileToken = profiles[0].token
        obj.StreamSetup = {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}}
        rtsp = media_service.GetStreamUri(obj)['Uri']
        obj = media_service.create_type('GetSnapshotUri')
        obj.ProfileToken = profiles[0].token
        http = media_service.GetSnapshotUri(obj)['Uri']#.split('?')[0]
    except ONVIFError :
        return None
    return info, rtsp, http

def setCam(cam):
    camJson = {'key':settings.KEY,'cam':cam}
    try :
        r = requests.post(settings.SERVER+"setCam", json=camJson, timeout = 40 )
        logger.info('set cam {}'.format(cam))
        s = json.loads(r.text)
        return s
    except (requests.exceptions.ConnectionError, json.decoder.JSONDecodeError, requests.Timeout) as ex :
        logger.error('exception in setCam : {}'.format(ex))
        pass
    return False

def removeCam(cam):
    camJson = {'key':settings.KEY,'cam':cam}
    try :
        r = requests.post(settings.SERVER+"removeCam", json=camJson, timeout = 40 )
        s = json.loads(r.text)
        return s
    except (requests.exceptions.ConnectionError, json.decoder.JSONDecodeError, requests.Timeout) as ex :
        logger.error('exception in remove cam for cam {} : {}'.format(cam, ex))
        pass
    return False


def compareCam(ws, lock, force):
    with lock:
        with open(settings.INSTALL_PATH+'/camera/camera.json', 'r') as out:
            cameras = json.loads(out.read())
    cameras_users = list(set([(c['username'],c['password']) for c in cameras]))
    # cameras could have wait_for_set camera :
    # test connection for wait for set cam
    list_cam = []
    for cam in cameras :
        logger.info('cam {} in state / wait_for_set {} / from_client {} / force {}'.format(
                cam['ip'],cam['wait_for_set'],cam['from_client'], force))
        if cam['wait_for_set'] or (cam['from_client'] and force==2)  :
            for user , passwd in cameras_users:
                logger.info('testing onvif cam with {} {}'.format(user, passwd))
                onvif = getOnvifUri(cam['ip'],cam['port_onvif'],user,passwd)
                if onvif :
                    info, rtsp , http = onvif
                    auth = {'B':requests.auth.HTTPBasicAuth(user,passwd), 'D':requests.auth.HTTPDigestAuth(user,passwd)}
                    for t, a in auth.items() :
                        try:
                            r = requests.get(http.split('?')[0], auth = a , stream=False, timeout=1)
                            logger.info('request on {}'.format(http.split('?')[0]))
                            if r.ok:
                                logger.info('request  on camera OK for {} / {} / {} / {}'.format(
                                             cam['ip'],user, passwd, t))
                                cam['brand']=info['Manufacturer']
                                cam['model']=info['Model']
                                cam['url']= http
                                cam['auth_type']= t
                                cam['username'] = user
                                cam['active_automatic'] = True
                                cam['password'] = passwd
                                cam['wait_for_set'] = False
                                cam['rtsp'] = rtsp.split('//')[0]+'//'+user+':'+passwd+'@'+rtsp.split('//')[1]
                                list_cam.append(cam)
                        except (requests.exceptions.ConnectionError, requests.Timeout) :
                            pass
    for ips in ws.copy() :
        for c in cameras:
            if c['ip'] == ips :
                if c['active_automatic']:
                    del ws[ips]
                cameras[:] = [d for d in cameras if d['ip']!=ips]
    # take only ip for camera which are not scan and from client
    cameras[:] = [d for d in cameras if d['from_client'] is True]
    #test if camera is answering or not
    for cam in cameras.copy():
        user = cam['username']
        passwd = cam['password']
        auth = {'B':requests.auth.HTTPBasicAuth(user,passwd), 'D':requests.auth.HTTPDigestAuth(user,passwd)}
        for i in range(2):
            try:
                r = requests.get(
                        cam['url'],
                        auth = auth[cam['auth_type']] ,
                        stream=False, timeout=1)
                if r.ok :
                    cameras[:] = [d for d in cameras if d['id']!=cam['id']]
                    if not cam['active_automatic']:
                        cam['active_automatic']=True
                        list_cam.append(cam)
                    logger.error('ip {} not in ws but answer correct: so ignore'.format(cam['ip']))
                    break
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) :
                pass
            time.sleep(1)
    # ws contains new cam
    # test connection for new cam
    for ip,port in ws.items() :
        new_cam = {}
        new_cam['name']= 'unknow'
        new_cam['ip'] = ip
        new_cam['port_onvif'] = port
        new_cam['wait_for_set'] = True
        new_cam['from_client'] = True
        for user , passwd in cameras_users:
            onvif = getOnvifUri(ip,port,user,passwd)
            if onvif :
                info, rtsp , http = onvif
                auth = {'B':requests.auth.HTTPBasicAuth(user,passwd), 'D':requests.auth.HTTPDigestAuth(user,passwd)}
                for t, a in auth.items() :
                    try:
                        r = requests.get(http, auth = a , stream=False, timeout=1)
                        if r.ok:
                            new_cam['brand']=info['Manufacturer']
                            new_cam['model']=info['Model']
                            new_cam['url']= http
                            new_cam['auth_type']= t
                            new_cam['username'] = user
                            new_cam['password'] = passwd
                            new_cam['active'] = True
                            new_cam['wait_for_set'] = False
                            new_cam['rtsp'] = rtsp.split('//')[0]+'//'+user+':'+passwd+'@'+rtsp.split('//')[1]
                    except (requests.exceptions.ConnectionError, requests.Timeout) :
                        pass
        list_cam.append(new_cam)
    # cameras contains cam now unreachable
    logger.info('compare camera, new or set or force : {} / remove : {}'.format(list_cam,[c['ip'] for c in cameras if c['active_automatic']]))
    return list_cam, [c['ip'] for c in cameras  if c['active_automatic'] ]

def getCam(lock, force= 0):
    try :
        logger.info('get camera, force state : {}'.format(force))
        r = requests.post(settings.SERVER+"getCam", data = {'key': settings.KEY, 'force':force}, timeout = 40 )
        c = json.loads(r.text)
        logger.info('get camera : {}'.format(c))
        if not c==False :
            with lock:
                with open(settings.INSTALL_PATH+'/camera/camera.json', 'w') as out:
                    json.dump(c,out)
            r = requests.post(settings.SERVER+"upCam", data = {'key': settings.KEY})
        return c
    except (requests.exceptions.ConnectionError, json.decoder.JSONDecodeError, requests.Timeout) as ex :
        logger.error('exception in getCam: {}'.format(ex))
        return False
        pass

def run(period, lock, E_cam_start, E_cam_stop):
    remove_nb = {}
    # reboot
    cam = getCam(lock, 2)
    ws = wsDiscovery(2,20)
    if not ws==False:
        list_cam, remove_cam = compareCam(ws, lock, 2)
        if list_cam : setCam(list_cam)
        if remove_cam : removeCam(remove_cam)
    cam = getCam(lock, 1)
    force = 1
    E_cam_start.set()
    while True :
        # scan the cam on the network
        ws = wsDiscovery(2,20)
        if not ws==False:
            # pull the cam from the server
            cam = getCam(lock, force)
            # compare the cam with the camera file
            list_cam, remove_cam = compareCam(ws, lock, force)
            # check if changes
            if cam==False :
                E_cam_start.set()
                logger.info('camera unchanged : E_cam_start is_set {}'.format(E_cam_start.is_set()))
                force= 0
            else :
                E_cam_stop.set()
                logger.info(' ********* camera changed : E_cam_stop is_set {}'.format(E_cam_start.is_set()))
                force =  1
            # push the cam to the server
            if list_cam : setCam(list_cam)
            # inactive the cam on the server
            if remove_cam :
                logger.error('ip {} in remove cam'.format(remove_cam))
                for rcam in remove_cam:
                    if rcam not in remove_nb :
                        remove_nb[rcam] = 0
                    else :
                        remove_nb[rcam] +=1
                    if remove_nb[rcam]>2:
                        removeCam([rcam,])
                        remove_nb.pop(rcam, None)
                        logger.error('ip {} send to server to inactive'.format(rcam))
            # wait for the loop
            if force==0:
                time.sleep(period)
        else :
            time.sleep(30)




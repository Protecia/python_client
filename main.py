# -*- coding: utf-8 -*-
"""
Created on Sat Jun  1 07:34:04 2019

@author: julien
"""
import asyncio

import process_camera_new as pc
from threading import Lock as tLock, Event
from multiprocessing import Process, Queue, Lock, Event as pEvent
import json
from log import Logger
import scan_camera as sc
import upload as up
from video import http_serve
from install_cron import install_rec_backup_cron, install_check_tunnel_cron
import settings
import requests
import subprocess
import web_camera
import signal
import time
from urllib3.exceptions import ProtocolError
from utils import get_conf

# globals var
logger = Logger(__name__, level=settings.MAIN_LOG).run()



E_video = pEvent()
tlock = asyncio.Lock()
e_state = Event()
scan_state = pEvent()


def conf():
    try:
        machine_id = subprocess.check_output(['cat', settings.UUID]).decode().strip('\x00')
        r = requests.post(settings.SERVER + "conf", data={'machine': machine_id, 'pass': settings.INIT_PASS},
                          timeout=40)
        logger.warning(f'request :  {r.text}')
        data = json.loads(r.text)
        if data.get('key', False):
            with open(settings.INSTALL_PATH + '/conf/conf.json', 'w') as conf_json:
                json.dump({key: data[key] for key in ['cp', 'city', 'key', 'scan_camera', 'scan']}, conf_json)
            with open(settings.INSTALL_PATH + '/conf/docker.json', 'w') as docker_json:
                json.dump({key: data[key] for key in ['tunnel_port', 'docker_version', 'reboot']}, docker_json)
                logger.warning(f'Receiving  conf :  {r.text}')
            return True
        else:
            logger.warning(f'No client affected.')
            return False
    except (ConnectionResetError, requests.exceptions.ConnectionError, requests.Timeout, KeyError,
            json.decoder.JSONDecodeError, ProtocolError) as ex:
        logger.error(f'exception in configuration : except-->{ex} / name-->{type(ex).__name__}')
        return False


def end(signum, frame):
    raise KeyboardInterrupt('Extern interrupt')


def stop(list_thread):
    for t in list_thread:
        t.running_level2 = False
        t.running_rtsp = False
        try:
            t.thread_rtsp.join()
        except AttributeError:
            pass
        t.join()


def main():
    signal.signal(signal.SIGTERM, end)
    list_tasks = []
    process = {}
    loop = asyncio.get_event_loop()
    try:
        while not conf():
            time.sleep(10)
        # install some cron job
        install_rec_backup_cron()
        install_check_tunnel_cron()

        # Instanciate get_camera :
        cameras = web_camera.Client()

        # retrieve cam
        loop.run_until_complete(cameras.get_cam())

        # initial scan state :
        if get_conf('scan'):
            scan_state.set()

        # launch child processes
        process1 = {
            'serve_http': Process(target=http_serve, args=(2525,))}
        for p in process1.values():
            p.start()

        # log the id of the process
        txt = f'PID of different processes : '
        for key, value in process1.items():
            txt += f'{key}->{value.pid} / '
        logger.error(txt)

        while True:
            # write the file for backup video
            cameras.write()
            logger.warning(f'Writing camera in json : {cameras.list_cam}')
            # start the scan
            process2 = {'scan_camera': Process(target=sc.run, args=(settings.SCAN_INTERVAL, scan_state,)), }
            for p in process2.values():
                p.start()

            # set the video event
            E_video.set()

            # initialize the camera state event
            cameras_state = {}
            # launch the camera thread
            list_tasks = []
            for c in cameras.list_cam.values():
                if c['active'] and c['active_automatic']:
                    uri = None
                    for uri in c['uri'].values():  # get the camera uri in use or the last one
                        if uri['use']:
                            break
                    if uri:
                        uri.pop('id', None)
                        ready_cam = {**c, **uri}
                        p = pc.ProcessCamera(ready_cam, loop, tlock)
                        list_tasks.append(p.run())
                        # p.start()
                        logger.warning(f'starting process camera on  : {ready_cam}')

            # wait until a camera change
            list_tasks.append(cameras.connect(e_state, scan_state, cameras_state))
            loop.run_until_complete(asyncio.gather(*list_tasks))

            logger.debug('connect pass go on')
            # If camera change (websocket answer) -----------------------------
            stop(list_tasks)
            logger.debug('thread stopped')
            # stop the scan
            for p in process2.values():
                p.terminate()
            logger.error('Camera change restart !')

    except KeyboardInterrupt:
        stop(list_tasks)
        for p in process.values():
            p.terminate()
        logger.warning('Ctrl-c or SIGTERM')


# start the threads
if __name__ == '__main__':
    main()

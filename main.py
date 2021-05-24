# -*- coding: utf-8 -*-
"""
Created on Sat Jun  1 07:34:04 2019

@author: julien
"""
import process_camera_thread as pc
from threading import Lock as tLock, Event
from multiprocessing import Process, Queue, Lock, Event as pEvent
import json
from log import Logger
import scan_camera as sc
import upload as up
from video import http_serve
from install_cron import install_rec_backup_cron, install_check_tunnel_cron
import settings.settings as settings
import requests
import subprocess
import web_camera
import signal
import time
from urllib3.exceptions import ProtocolError
import ping as pg

# globals var
logger = Logger(__name__, level=settings.MAIN_LOG).run()

Q_img = Queue()
Q_img_real = Queue()
Q_result = Queue()
lock = Lock()
E_video = pEvent()
tlock = tLock()
e_state = Event()
scan_state = pEvent()


def conf():
    try:
        machine_id = subprocess.check_output(['cat', settings.UUID]).decode().strip('\x00')
        r = requests.post(settings.SERVER + "conf", data={'machine': machine_id, 'pass': settings.INIT_PASS},
                          timeout=40)
        data = json.loads(r.text)
        with open(settings.INSTALL_PATH + '/settings/conf.json', 'w') as conf_json:
            if data.get('key', False):
                json.dump(data, conf_json)
                logger.warning(f'Receiving  json conf :  {r.text}')
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
        t.running = False
        t.running_rtsp = False
        try:
            t.thread_rtsp.join()
        except AttributeError:
            pass
        t.join()


def main():
    signal.signal(signal.SIGTERM, end)
    list_thread = []
    process = {}
    try:
        while not conf():
            time.sleep(10)
        # install some cron job
        install_rec_backup_cron()
        install_check_tunnel_cron()

        # Instanciate get_camera :
        cameras = web_camera.Cameras()

        # retrieve cam
        cameras.get_cam()

        # launch child processes
        process = {
            'scan_camera': Process(target=sc.run, args=(settings.SCAN_INTERVAL, scan_state,)),
            'image_upload': Process(target=up.upload_image, args=(Q_img,)),
            'image_upload_real_time': Process(target=up.uploadImageRealTime, args=(Q_img_real,)),
            'result_upload': Process(target=up.upload_result, args=(Q_result, E_video)),
            'serve_http': Process(target=http_serve, args=(2525,))}
        for p in process.values():
            p.start()

        # log the id of the process
        txt = f'PID of different processes : '
        for key, value in process.items():
            txt += f'{key}->{value.pid} / '
        logger.error(txt)

        while True:
            # write the file for backup video
            cameras.write()
            logger.warning(f'Writing camera in json : {cameras.list_cam}')

            # set the video event
            E_video.set()

            # initialize the camera state event
            cameras_state = {}

            # launch the camera thread
            list_thread = []
            for c in cameras.list_cam.values():
                if c['active'] and c['active_automatic']:
                    uri = None
                    for uri in c['uri'].values():  # get the camera uri in use or the last one
                        if uri['use']:
                            break
                    if uri:
                        uri.pop('id', None)
                        ready_cam = {**c, **uri}
                        cameras_state[c['id']] = [Event(), Event()]
                        p = pc.ProcessCamera(ready_cam, Q_result, Q_img, Q_img_real, tlock, cameras_state, e_state)
                        list_thread.append(p)
                        p.start()
            # wait until a camera change
            cameras.connect(e_state, scan_state, cameras_state)

            # If camera change (websocket answer) -----------------------------
            stop(list_thread)
            logger.error('Camera change restart !')
            # write the file for backup video
            cameras.write()
    except KeyboardInterrupt:
        stop(list_thread)
        for p in process.values():
            p.terminate()
        logger.warning('Ctrl-c or SIGTERM')


# start the threads
if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""
Created on Sat Jun  1 07:34:04 2019

@author: julien
"""
import process_camera_thread as pc
from threading import Lock as tLock
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
import asyncio

# globals var
logger = Logger(__name__, level=settings.MAIN_LOG).run()

Q_img = Queue()
Q_img_real = Queue()
Q_result = Queue()
lock = Lock()
E_video = pEvent()
tlock = tLock()


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
        logger.warning(f'exception in configuration : except-->{ex} / name-->{type(ex).__name__}')
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

        # write the file for backup video
        cameras.write()
        logger.warning(f'Writing camera in json : {cameras.list}')

        # launch child processes
        process = {
            'image_upload': Process(target=up.uploadImage, args=(Q_img,)),
            'image_upload_real_time': Process(target=up.uploadImageRealTime, args=(Q_img_real,)),
            'result_upload': Process(target=up.uploadResult, args=(Q_result, E_video )),
            'serve_http': Process(target=http_serve, args=(2525,))}
        for p in process.values():
            p.start()

        # log the id of the process
        logger.error(f'PID of different processes : upload image->{process["image_upload"].pid} / '
                     f'upload real time image->{process["image_upload_real_time"].pid} / '
                     f'upload result->{process["result_upload"].pid} / serve cherrypy->{process["serve_http"].pid}')

        while True:
            list_thread = []
            for c in cameras.list:
                p = pc.ProcessCamera(c, Q_result, Q_img, Q_img_real, tlock)
                list_thread.append(p)
                p.start()

            # wait until a camera change
            cameras.cam_connect()
            # If camera change (websocket answer)
            stop(list_thread)
            logger.warning('Camera change restart !')
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

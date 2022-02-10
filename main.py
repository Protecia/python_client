# -*- coding: utf-8 -*-
"""
Created on Sat Jun  1 07:34:04 2019

@author: julien
"""
import asyncio

import process_camera_new as pc
from multiprocessing import Process, Event as pEvent
import json
from log import Logger
import scan_camera as sc
from video import http_serve
from install_cron import install_rec_backup_cron, install_check_tunnel_cron
import settings
import requests
import subprocess
import web_camera
import signal
import time
from urllib3.exceptions import ProtocolError
from utils import get_conf, display_top

import tracemalloc

tracemalloc.start()

# ... lancez votre application ...

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')


# globals var
logger = Logger(__name__, level=settings.MAIN_LOG, file=True).run()


tlock = asyncio.Lock()
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
            with open(settings.INSTALL_PATH + '/conf/force_reboot.json', 'w') as reboot_json:
                json.dump({'force_reboot': False, }, reboot_json)
                logger.warning(f'writing reboot  init conf')
            return True
        else:
            logger.warning(f'No client affected.')
            return False
    except (ConnectionResetError, requests.exceptions.ConnectionError, requests.Timeout, KeyError,
            json.decoder.JSONDecodeError, ProtocolError) as ex:
        logger.error(f'exception in configuration : except-->{ex} / name-->{type(ex).__name__}')
        return False


# def end(signum, frame):
#     raise KeyboardInterrupt('Extern interrupt')


def main():
    # signal.signal(signal.SIGTERM, end)
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
            p.daemon = True
            p.start()

        # log the id of the process
        txt = f'PID of different processes : '
        for key, value in process1.items():
            txt += f'{key}->{value.pid} / '
        logger.error(txt)

        while True:
            try:
                # write the file for backup video
                cameras.write()
                logger.info(f'Writing camera in json : {cameras.list_cam}')
                # start the scan
                process2 = {'scan_camera': Process(target=sc.run, args=(settings.SCAN_INTERVAL, scan_state,)), }
                for p in process2.values():
                    p.daemon = True
                    p.start()

                # log the id of the process
                txt = f'PID of different processes : '
                for key, value in process.items():
                    txt += f'{key}->{value.pid} / '
                logger.error(txt)

                # launch the camera thread
                list_tasks = []
                for c in cameras.list_cam.values():
                    if c['active'] and c['active_automatic']:
                        uri = None
                        for uri in c['uri'].values():  # get the camera uri in use or the last one
                            if uri['use']:
                                break
                        if uri:
                            # need to copy the dict because you can not remove the id from camera.list_cam
                            uri_copy = uri.copy()
                            uri_copy.pop('id', None)
                            ready_cam = {**c, **uri_copy}
                            p = pc.ProcessCamera(ready_cam, loop, tlock)
                            list_tasks.append(p)
                            logger.info(f'starting process camera on  : {ready_cam}')

                # wait until a camera change
                total_tasks = [cameras.connect(scan_state, list_tasks)] + \
                              [t.run() for t in list_tasks]
                logger.error(f'list of all tasks launched {[t.__str__() for t in list_tasks]}')
                snapshot = tracemalloc.take_snapshot()
                top_stats = snapshot.statistics('lineno')
                logger.error(f'Memory allocation {top_stats}')
                logger.error(f'Memory allocation top {display_top(snapshot)}')
                loop.run_until_complete(asyncio.gather(*total_tasks))

                logger.warning('tasks stopped')
                # stop the scan
                for p in process2.values():
                    p.terminate()
                    p.join(timeout=1.0)
                logger.error('Camera change restart !')
                cameras.running_level1 = True
            except Exception as ex:
                logger.error(f'EXCEPTION IN MAIN  trying to restart in 5 s/ except-->{ex} / name-->{type(ex).__name__}')
                time.sleep(5)
    except KeyboardInterrupt:
        for p in process1.values():
            p.terminate()
            p.join(timeout=1.0)
        for p in process2.values():
            p.terminate()
            p.join(timeout=1.0)
        logger.warning('Ctrl-c or SIGTERM')


# start the threads
if __name__ == '__main__':
    main()

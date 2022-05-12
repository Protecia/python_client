# -*- coding: utf-8 -*-
"""
Created on Sat Jun  1 07:34:04 2019

@author: julien
"""
import asyncio

import process_camera as pc
from multiprocessing import Process
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
import logging

import tracemalloc

if settings.MAIN_LOG == logging.DEBUG:
    tracemalloc.start()

# globals var
logger = Logger(__name__, level=settings.MAIN_LOG, file=True).run()


tlock = asyncio.Lock()


def conf():
    try:
        machine_id = subprocess.check_output(['cat', settings.UUID]).decode().strip('\x00')
        r = requests.post(settings.SERVER + "conf", data={'machine': machine_id, 'pass': settings.INIT_PASS,
                                                          'version': 2}, timeout=40)
        logger.warning(f'request :  {r.text}')
        data_dict = json.loads(r.text)
        if data_dict.get('clients', False):
            data_client = data_dict['clients']
            with open(settings.INSTALL_PATH + '/conf/conf.json', 'w') as conf_json:
                json.dump(data_client, conf_json)
            for data in data_client:
                requests.post(settings.SERVER + "conf", data={'key': data['key'],
                              'class_detected': json.dumps(settings.CLASS_DETECTED)},
                              timeout=40)
            data_machine = data_dict['machine'][0]
            with open(settings.INSTALL_PATH + '/conf/docker.json', 'w') as docker_json:
                json.dump({key: data_machine[key] for key in ['tunnel_port', 'docker_version', 'reboot']}, docker_json)
                logger.warning(f'Receiving  conf :  {data_machine}')
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
        list_client = get_conf('key')
        list_client = [web_camera.Client(obj) for obj in list_client]

        # retrieve cam
        list_camera_client_coroutine = [obj.get_cam() for obj in list_client]
        loop.run_until_complete(asyncio.gather(*list_camera_client_coroutine))

        # launch child processes
        process = {
            'serve_http': Process(target=http_serve, args=(2525,)),
        }

        # launch scan if True in scan state
        list_client_scan = [scan[0] for scan in zip(get_conf('key'), get_conf('scan')) if scan[1]]
        for k in list_client_scan:
            process[f'scan_camera_{k}'] = Process(target=sc.run, args=(settings.SCAN_INTERVAL, k))

        for p in process.values():
            p.daemon = True
            p.start()

        # log the id of the process
        txt = f'PID of different processes : '
        for key, value in process.items():
            txt += f'{key}->{value.pid} / '
        logger.error(txt)

        while True:
            try:
                # write the file for backup video
                [obj.write() for obj in list_client]
                logger.info(f'Writing camera in json : {[obj.list_cam for obj in list_client]}')

                total_tasks = []
                for client in list_client:
                    # launch the camera thread
                    list_tasks = []
                    for camera in client.list_cam.values():
                        if camera['active'] and camera['active_automatic']:
                            uri = None
                            for uri in camera['uri'].values():  # get the camera uri in use or the last one
                                if uri['use']:
                                    break
                            if uri:
                                # need to copy the dict because you can not remove the id from camera.list_cam
                                uri_copy = uri.copy()
                                uri_copy.pop('id', None)
                                ready_cam = {**camera, **uri_copy}
                                p = pc.ProcessCamera(ready_cam, loop, tlock)
                                list_tasks.append(p)
                                logger.info(f'starting process camera on  : {ready_cam}')

                    # wait until a camera change
                    regroup_tasks = [client.connect(list_tasks)] + [t.run() for t in list_tasks]
                    total_tasks += regroup_tasks

                logger.error(f'list of all tasks launched {[t.__str__() for t in list_tasks]}')
                if settings.MAIN_LOG == logging.DEBUG:  # Avoid evaluation of tracemalloc
                    logger.debug(f'Memory allocation {tracemalloc.take_snapshot().statistics("lineno")}')
                    logger.debug(f'Memory allocation top {display_top(tracemalloc.take_snapshot())}')

                loop.run_until_complete(asyncio.gather(*total_tasks))  # wait until a camera change
                time.sleep(0.1)
                logger.warning('tasks stopped')
                logger.error('Camera change restart !')
                for cam in list_client:
                    cam.running_level1 = True
            except Exception as ex:
                logger.error(f'EXCEPTION IN MAIN  trying to restart in 5 s/ except-->{ex} / name-->{type(ex).__name__}')
                time.sleep(5)
    except KeyboardInterrupt:
        for p in process.values():
            p.terminate()
            p.join(timeout=1.0)
        logger.warning('Ctrl-c or SIGTERM')


# start the threads
if __name__ == '__main__':
    main()

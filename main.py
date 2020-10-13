# -*- coding: utf-8 -*-
"""
Created on Sat Jun  1 07:34:04 2019

@author: julien
"""

import process_camera_thread as pc
from threading import Event, Lock as tLock
from multiprocessing import Process, Queue, Lock, Event as pEvent
import json
from collections import namedtuple
from log import Logger
import scan_camera as sc
import upload as up
from video import http_serve
from install_cron import install_rec_backup_cron, install_check_tunnel_cron
import ping as pg
import settings.settings as settings
import requests
import subprocess

logger = Logger(__name__).run()

Q_img = Queue()
Q_img_real = Queue()
Q_result = Queue()
E_cam_start = pEvent()
E_cam_stop = pEvent()
E_state = pEvent()
E_video = pEvent()
#E_state_real = pEvent()
lock = Lock()
tlock = tLock()
onLine = True

def conf():
    try :
       if settings.KEY is None:
           machine_id = subprocess.check_output(['cat', '/sys/class/dmi/id/product_uuid']).decode().strip()
           r = requests.post(settings.SERVER+"conf", data = {'machine': machine_id, }, timeout= 40 )
       else:    
           r = requests.post(settings.SERVER+"conf", data = {'key': settings.KEY, }, timeout= 40 )
           data = json.loads(r.text)
           with open(settings.INSTALL_PATH+'/settings/conf.json', 'w') as conf_json:
               json.dump(data['conf'],conf_json)
    except (requests.exceptions.ConnectionError, requests.Timeout, KeyError, json.decoder.JSONDecodeError ) as ex :
            logger.warning('conf Can not find the remote server : except --> {}'.format(ex))
            pass

def main():
    try:
        install_rec_backup_cron()
        install_check_tunnel_cron()
        pCameraDownload = Process(target=sc.run, args=(60,lock, E_cam_start, E_cam_stop))
        pCameraDownload.start()
        pImageUpload = Process(target=up.uploadImage, args=(Q_img,))
        pImageUploadRealTime = Process(target=up.uploadImageRealTime, args=(Q_img_real,))
        pResultUpload = Process(target=up.uploadResult, args=(Q_result,E_video))
        pServeHttp =  Process(target=http_serve, args=(2525,))
        #pState = Process(target=up.getState, args=(E_state,E_state_real))
        pImageUpload.start()
        pResultUpload.start()
        #pState.start()
        pImageUploadRealTime.start()
        pServeHttp.start()
        while(True):
            # start the process to synchronize cameras
            logger.warning('scan camera launch, E_cam_start.is_set : {}  / E_cam_stopt.is_set : {}'.format(E_cam_start.is_set(),E_cam_stop.is_set()) )
            E_cam_start.wait()
            E_cam_stop.clear()
            logger.warning('scan camera launch, E_cam_start.is_set : {}  / E_cam_stopt.is_set : {}'.format(E_cam_start.is_set(),E_cam_stop.is_set()) )
            with lock :
                with open('camera/camera.json', 'r') as json_file:
                    cameras = json.load(json_file, object_hook=lambda d: namedtuple('camera', d.keys())(*d.values()))
            E_video.set()        
            cameras = [c for c in cameras if (c.active==True and c.active_automatic==True)]
            list_thread=[]
            list_event=[Event() for i in range(len(cameras))]
            cameras_state={}
            for n, c in enumerate(cameras):
                cameras_state[c.id]=[pEvent(),pEvent()]
                p = pc.ProcessCamera(c, n, Q_result,
                                   list_event,
                                   len(cameras), Q_img, E_state, Q_img_real, cameras_state[c.id], tlock )
                list_thread.append(p)
                p.start()
            pState = Process(target=pg.getState, args=(E_state,cameras_state))
            pState.start()
            print('darknet is running...')
            # Just run4ever (until Ctrl-c...)
            if cameras : list_event[0].set()
            E_cam_stop.wait()
            E_cam_start.clear()
            for t in list_thread:
                t.running=False
                t.running_rtsp=False
                try :
                    t.thread_rtsp.join()
                except AttributeError:
                    pass
                t.join()
            pState.terminate()
            logger.warning('Camera change restart !')
    except KeyboardInterrupt:
        for t in list_thread:
            t.running=False
            t.running_rtsp=False
            try :
                t.thread_rtsp.join()
            except AttributeError:
                pass
            t.join()
        pImageUpload.terminate()
        pState.terminate()
        pCameraDownload.terminate()
        pResultUpload.terminate()
        pImageUploadRealTime.terminate()
        print("Bye bye!")

# start the threads
if __name__ == '__main__':
    main()

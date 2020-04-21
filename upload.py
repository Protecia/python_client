# -*- coding: utf-8 -*-
"""
Created on Tue Dec 24 16:14:52 2019

@author: julien
"""
import requests
import settings.settings as settings
from log import Logger
import time
import json


logger = Logger(__name__).run()
logger.setLevel(settings.UPLOAD_LOG)

def uploadImageRealTime(Q):
    logger.warning('starting upload real time image')
    while True:
        cam, result , img, resize_factor = Q.get()
        logger.info('get image from queue real on cam  : {}'.format(cam))
        files = {'myFile': img}
        imgJson = {'key': settings.KEY, 'img_name': 'temp_img_cam_'+str(cam), 'cam' : cam,
                   'result' : json.dumps([(r[0].decode(),r[1],r[2]) for r in result]), 'real_time' : True,
                   'resize_factor':resize_factor}
        try :
            r = requests.post(settings.SERVER+"uploadimage", files=files, data = imgJson,  timeout= 40)
            logger.warning('send json image real : {}'.format(r.status_code))
        except (requests.exceptions.ConnectionError, requests.Timeout) :
            logger.warning('uploadImageRealTime Can not find the remote server')
            time.sleep(5)
            pass

def uploadImage(Q):
    server = True
    logger.warning('starting upload image')
    while True:
        if server :
            cam, img_name, result, img = Q.get()
            logger.info('get image from queue : {}'.format(img_name))
            files = {'myFile': img}
            imgJson = {'key': settings.KEY, 'img_name': img_name, 'cam' : cam,
                       'result' : json.dumps([(r[0].decode(),r[1],r[2]) for r in result]), 'real_time' : False}
        try :
            r = requests.post(settings.SERVER+"uploadimage", files=files, data = imgJson,  timeout= 40)
            server = True
            logger.info('send json image : {}'.format(imgJson))
            logger.warning('send image to server  : {}'.format(r.status_code))
        except (requests.exceptions.ConnectionError, requests.Timeout) :
            server = False
            logger.warning('uploadImage Can not find the remote server')
            time.sleep(5)
            pass

def uploadResult(Q, E_video):
    from video import RecCamera
    recCamera  = RecCamera(E_video)
    server = True
    logger.warning('starting upload result')
    while True:
        if server :
            result = Q.get()
            logger.info('get result from queue : {}'.format(result))
            img, cam,  result_filtered, result_darknet = result[0], result[1], [(r[0].decode(),r[1],r[2]) for r in result[2] ], [(r[0].decode(),r[1],r[2]) for r in result[3] ]
            # set video record for this result
            video = recCamera.rec_cam(cam)
            logger.info('get video token : {}'.format(video))
            resultJson = {'key': settings.KEY, 'img' : img, 'cam' : cam, 'result_filtered' : result_filtered, 'result_darknet' : result_darknet, 'video' : video }
        try :
            r = requests.post(settings.SERVER+"uploadresult", json=resultJson,  timeout= 40)
            server = True
            logger.info('send json : {}'.format(resultJson))
            logger.warning('send result to server  : {}'.format(r.text))
        except (requests.exceptions.ConnectionError, requests.Timeout) :
            server = False
            logger.warning('uploadResult Can not find the remote server')
            time.sleep(5)
            pass


def set_token(token1, token2):
    with open(settings.INSTALL_PATH+'/token', 'w') as f:
        json.dump({'token1':token1, 'token2':token2},f)


def getState(E, camera_state):
    while True:
        try :
            r = requests.post(settings.SERVER+"getState", data = {'key': settings.KEY, }, timeout= 40 )
            data = json.loads(r.text)
            logger.warning('getState answer : {}'.format(data))
            if data['rec'] :
                E.set()
            else :
                E.clear()
            on_camera = data['cam']
            if data['token1']:
                set_token(data['token1'],data['token2'])
            for pk, state in on_camera.items():
                [camera_state[int(pk)][index].set() if i else camera_state[int(pk)][index].clear() for index, i in enumerate(state)]
        except (requests.exceptions.ConnectionError, requests.Timeout, KeyError) :
            logger.warning('getState Can not find the remote server')
            time.sleep(5)
            pass
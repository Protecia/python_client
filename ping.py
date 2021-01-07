# -*- coding: utf-8 -*-
"""
Created on Tue Sep 15 11:37:59 2020

@author: julien
"""
import requests
import settings.settings as settings
from log import Logger
import time
import json
import os


logger = Logger(__name__, level=settings.PING_LOG).run()

def set_token(token1, token2):
    with open(settings.INSTALL_PATH+'/token', 'w') as f:
        json.dump({'token1':token1, 'token2':token2},f)

def getState(E, camera_state):
    while True:
        try :
            r = requests.post(settings.SERVER+"getState", data = {'key': settings.CONF.get_conf('key') }, timeout= 40 )
            data = json.loads(r.text)
            logger.warning('getState answer : {}'.format(data))
            if data['reboot'] and settings.HARDWARE=='nano':
                os.system("sudo reboot")     
            if data['rec'] :
                E.set()
            else :
                E.clear()
            on_camera = data['cam']
            if data['token1']:
                set_token(data['token1'],data['token2'])
            for pk, state in on_camera.items():
                [camera_state[int(pk)][index].set() if i else camera_state[int(pk)][index].clear() for index, i in enumerate(state)]
        except (requests.exceptions.ConnectionError, requests.Timeout, KeyError, json.decoder.JSONDecodeError ) as ex :
            logger.warning('getState Can not find the remote server : except --> {}'.format(ex))
            time.sleep(5)
            pass
        except Exception as e:
            logger.error('exception in getState, type : {} --> {}'.format(e.__class__.__name__,e))
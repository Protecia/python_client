# -*- coding: utf-8 -*-
"""
Created on Tue Mar  3 11:03:53 2020

@author: julien
"""

from datetime import datetime
import psutil as ps
from subprocess import Popen, check_output
import shlex
import time
import secrets
from threading import Thread
from settings import settings
from log import Logger
import json
import os
import cherrypy

logger = Logger('video',settings.VIDEO_LOG).run()


class RecCamera(object):
    def __init__(self, E_video):
        self.update = E_video
        Thread(target=self.update_cam).start()
    def update_cam(self):
        while True :
            self.update.wait()
            with open('camera/camera.json', 'r') as json_file:
               cameras = json.load(json_file)
            self.cameras = dict((item['id'], item) for item in cameras if item['active'])
            for k,v in self.cameras.items() :
                if not 'rec' in v.keys():
                    v['rec'] = False
            logger.info('Update cameras')
            self.update.clear()
    
    def rec_cam(self,cam_id):
        if not self.cameras[cam_id]['rec']:
            self.cameras[cam_id]['rec']=True
            token = secrets.token_urlsafe()
            cmd = 'ffmpeg  -nostats -loglevel 0 -y -i  {} -vcodec copy camera/live/{}.mp4'.format(self.cameras[cam_id]['rtsp'], token )
            p = Popen(shlex.split(cmd))
            logger.info('Send ffmpeg process with cmd {}'.format(cmd))
            self.cameras[cam_id]['rec_time']=time.time()
            # thread to kill process
            t = Thread(target=self.kill_process, args=(cam_id, p))
            t.start()
            self.cameras[cam_id]['token']=token
        else :
            self.cameras[cam_id]['rec_time']=time.time()
        return self.cameras[cam_id]['token']
    def kill_process(self, cam_id, p):
        self.check_space(5)
        i=0
        while True :
            if time.time()-self.cameras[cam_id]['rec_time'] > settings.VIDEO_REC_TIME or i > 3600 : #max 30 mn per video
                self.cameras[cam_id]['rec'] =False
                logger.info('kill process {} for cam {}'.format(p, cam_id))
                try :
                    p.terminate()
                    time.sleep(2)
                    p.kill()
                    break
                except ps.AccessDenied :
                    pass
                except ps.NoSuchProcess :
                    pass
                    break
            i +=1
            time.sleep(0.5)
    def check_space(self,G):
    ##### check the space on disk to respect the quota #######
        path = os.path.join(settings.INSTALL_PATH,'camera/live')
        size = int(check_output(['du','-s', path]).split()[0].decode('utf-8'))
        logger.info('check size {} Go'.format(size/1000000))
        if size>settings.VIDEO_SPACE*1000000:
            files = [os.path.join(path, f) for f in os.listdir(path)] # add path to each file
            files.sort(key=lambda x: os.path.getmtime(x))
            while settings.VIDEO_SPACE*1000000-int(check_output(['du','-s', path]).split()[0].decode('utf-8')) < G*1000000 :
                os.remove(files[0])
                del(files[0])


def rec_all_cam():
    repeat = True
    while repeat :
        i = 0
        try :
            with open('camera/camera.json', 'r') as json_file:
                cameras = json.load(json_file)
            cameras = dict((item['id'], item) for item in cameras if item['active'])
            repeat = False
        except json.decoder.JSONDecodeError :
            pass
            i+=1
            if i > 3 :
                break
    for k,v in cameras.items():
        cmd = '/usr/local/bin/ffmpeg  -nostats -loglevel 0 -y -i  {} -vcodec copy camera/secu/{}.mp4'.format(v['rtsp'], 'backup_'+datetime.now().strftime("%H")+'_cam'+str(k))
        Popen(shlex.split(cmd))
        logger.warning('ffmpeg rec on  {}'.format(cmd))


def kill_ffmpeg_process():
    for p in ps.process_iter():
        try :
            cmd = ''.join(p.cmdline())
            if 'ffmpeg' in cmd and 'backup' in cmd :
                p.terminate()
                logger.warning('terminate process {}'.format(cmd))
                time.sleep(2)
                p.kill()
        except ps.AccessDenied :
            pass
            return False
        except ps.NoSuchProcess :
            pass
    return True


def http_serve(port):
    """Static file server, using Python's CherryPy. Used to serve video."""
    logger.warning('starting cherrypy')
    
    def check_token(token):
        for i in range(2):
            try :
                with open(settings.INSTALL_PATH+'/token', 'r') as f:
                    data = json.load(f)
                if token == data['token1'] or token == data['token2']:
                    return True
                else :
                    time.sleep(1)  
            except (FileNotFoundError, json.JSONDecodeError) :
                pass
                if i==1 :
                    return False         
        return False

    class Root:

        @cherrypy.expose
        def live(self, name, token):
            if check_token(token):
                return cherrypy.lib.static.serve_file(os.path.join(static_dir_live, name))
        
        @cherrypy.expose
        def secu(self, name, token):
            if check_token(token):
                return cherrypy.lib.static.serve_file(os.path.join(static_dir_secu, name))

        @cherrypy.expose
        def video(self,v,l, token):
            page = v.split('.')
            video_link = page[0]+'?name='+page[1]+'.mp4&token='+token
            back = 'http://'+'/'.join(l.split('_')) 
            file = os.path.join(static_dir, 'camera', page[0], page[1]+'.mp4')
            if os.path.isfile(file):
                return """
                <!DOCTYPE html>
                <html>
                  <head>
                    <meta charset="utf-8">
                    <title>Protecia</title>
                    <link rel="shortcut icon" href="img/favicon.ico">
                  </head>
                  <body>
                <p>
                  <a href="{}"><img   src="img/logo_protecia.jpg" alt="Protecia"></a>
                </p>
                <div style="text-align:center;">
                <video  controls autoplay>
                  <source src="{}" type="video/mp4">
                  Your browser does not support HTML5 video.
                </video>
                </div>
                  </body>
                </html>

                """.format(back,video_link)
            else:
                return """
                <!DOCTYPE html>
                <html>
                  <head>
                    <meta charset="utf-8">
                    <title>Protecia</title>
                    <link rel="shortcut icon" href="img/favicon.ico">
                  </head>
                  <body>
                <p>
                  <a href="{}"><img  src="img/logo_protecia.jpg" alt="Protecia"></a>
                </p>
                <div style="text-align:center;">
                <h1>
                  Video non disponible !
                 </h1>
                 <h6>
                 Des vidéo anciennes ont pu être effacées en fonction de la place disponible sur votre box d'enregistrement.
                 </h6>
                 <h1>
                  Video unavailable !
                 </h1>
                 <h6>
                 Video may have been deleted depends on the disk space available on your protecia box.
                 </h6>
                </video>
                </div>
                  </body>
                </html>
            """.format(back)
    
    static_dir = settings.INSTALL_PATH # Root static dir is this file's directory.
    static_dir_live = os.path.join(settings.INSTALL_PATH,'camera/live') # Root static dir is this file's directory.
    static_dir_secu = os.path.join(settings.INSTALL_PATH,'camera/secu') # Root static dir is this file's directory.

    cherrypy.config.update( {  # I prefer configuring the server here, instead of in an external file.
                'server.socket_host': '0.0.0.0',
                'server.socket_port': port,
                'environment': 'production',
            } )
    conf = {
                    '/img': {
            'tools.staticdir.on': True,
            'tools.staticdir.root': static_dir,
            'tools.staticdir.dir': 'img'}
        }
    
    cherrypy.quickstart(Root(), '/', config=conf)  # ..and LAUNCH ! :)

def main():
    print(logger)
    kill_ffmpeg_process()
    rec_all_cam()

# start the threads
if __name__ == '__main__':
    main()

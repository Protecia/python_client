# -*- coding: utf-8 -*-
"""
Created on Sat Feb  3 11:58:19 2018

@author: julien

Main script to process the camera images
"""
import time
import requests
import cv2
import numpy as np
from threading import Thread, Lock
import settings.settings as settings
import os
import darknet_RT as dn
from log import Logger
import secrets
import concurrent.futures

logger = Logger('process_camera_thread', level=settings.PROCESS_CAMERA_LOG).run()

threated_requests = settings.THREATED_REQUESTS
path = settings.DARKNET_PATH
net = {}
meta = {}

for key, values in settings.DARKNET_CONF.items():
    cfg = os.path.join(path,values['CFG']).encode()
    weights = os.path.join(path,values['WEIGHTS']).encode()
    data = os.path.join(path,values['DATA']).encode()
    net[key] = dn.load_net_custom(cfg,weights, 0, 1)
    meta[key] = dn.load_meta(data)

def detect_thread(net, meta, im, thresh):
    return dn.detect_image(net, meta, im, thresh)

def EtoB(E):
    if E.is_set() :
        return True
    else :
        return False

def get_list_diff(l_new,l_old,thresh):
    new_copy = l_new[:]
    old_copy = l_old[:]
    for e_new  in  l_new:
        flag = False
        limit_pos = thresh
        for e_old in l_old:
            if e_new[0]==e_old[0] :
                diff_pos = (sum([abs(i-j) for i,j in zip(e_new[2],e_old[2])]))/(e_old[2][2]+e_old[2][3])*100
                if diff_pos < thresh :
                    flag = True
                    if diff_pos < limit_pos:
                        limit_pos = diff_pos
                        to_remove = (e_new,e_old)
        if flag:
            #self.logger.debug('get_list-diff remove {} '.format(to_remove))
            new_copy.remove(to_remove[0])
            try :
                old_copy.remove(to_remove[1])
                new_copy.remove(to_remove[0])
            except ValueError:
                pass
    return new_copy,old_copy

def read_write(rw,*args):
    if rw=='r':
        im = cv2.imread(*args)
        return im
    if rw=='w':
        r = cv2.imwrite(*args)
        return r


# the base condition to store the image is : is there a new objects detection
# or a change in the localisation of the objects. It is not necessary to store
# billions of images but only the different one.

class ProcessCamera(Thread):
    """Thread used to grab camera images and process the image with darknet"""

    def __init__(self, cam, num, Q_result, list_event, nb_cam, Q_img, E_state, Q_img_real, camera_state, lock):
        Thread.__init__(self)
        self.event = list_event
        self.cam = cam
        self.num = num
        self.running = False
        self.running_rtsp = False
        self.pos_sensivity = cam.pos_sensivity
        #self.threated_requests = threated_requests
        self.request_OK = False
        self.lock = Lock()
        self.tlock = lock
        self.black_list=[i.encode() for i in settings.DARKNET_CONF['all']['RESTRICT']]
        self.logger = logger
        #self.net = net
        #self.meta = meta
        #self.array_to_image = array_to_image
        #self.detect_image = detect_image
        self.nb_cam = nb_cam
        self.Q_img = Q_img
        self.Q_result = Q_result
        self.result_DB = []
        self.E_state = E_state
        self.camera_state = camera_state
        self.Q_img_real = Q_img_real
        self.force_remove={}
        self.image_correction = [False,0]

        if cam.auth_type == 'B':
            self.auth = requests.auth.HTTPBasicAuth(cam.username,cam.password)
        if cam.auth_type == 'D' :
            self.auth = requests.auth.HTTPDigestAuth(cam.username,cam.password)

    def grab(self):
        self.vcap = cv2.VideoCapture(self.cam.rtsp)
        self.running_rtsp = self.vcap.isOpened()
        self.logger.warning('openning videocapture {} is {}'.format(self.vcap, self.vcap.isOpened()))
        i=15
        bad_read = 0
        while self.running_rtsp :
            if i==15:
                date = time.strftime("%Y-%m-%d-%H-%M-%S")
                ret, frame = self.vcap.read()
                self.logger.debug("resultat de la lecture rtsp : {} ".format(ret))
                self.logger.debug('*** {}'.format(date))
                t = time.time()
                if ret and len(frame)>100 :
                    bad_read = 0
                    if self.cam.reso:
                        if frame.shape[0]!=self.cam.height or frame.shape[1]!=self.cam.width:
                            frame = cv2.resize(frame,(self.cam.width, self.cam.height), interpolation = cv2.INTER_CUBIC)
                    with self.lock:
                        self.frame = frame
                        self.request_OK = True
                    self.logger.debug("resultat de l'ecriture de la frame : {} en {} ".format(
                            self.request_OK,time.time()-t))
                else :
                    self.request_OK = False
                    self.logger.warning('Bad rtsp read on {} videocapture is {}'.format(self.cam.name,self.vcap.isOpened()))
                    self.running_rtsp = self.vcap.isOpened()
                    bad_read+=1
                    if bad_read > 10:
                        break
                    time.sleep(0.5)
                i=0
            self.vcap.grab()
            i+=1
        with self.lock:
            self.vcap.release()
            self.logger.warning('VideoCapture close on {}'.format(self.cam.name))
            self.running_rtsp = False
            time.sleep(5)




    def run(self):
        """code run when the thread is started"""
        self.running = True
        while self.running :
            t=time.time()

            # Special stop point for dahua nvcr which can not answer multiple fast http requests
            if not threated_requests :
                #self.event[self.num].wait()    # NEED TO REMOVE ALL THE EVENT SYSTEM <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
                self.logger.debug('cam {} alive - not threated request'.format(self.cam.id))
            #-----------------------------------------------------------------------------------

            #******************************Grab images in http ********************************
            if not self.cam.stream :
                self.request_OK = True
                try :
                    r = requests.get(self.cam.url, auth=self.auth, stream=False, timeout=4)
                    if r.status_code == 200 and len(r.content)>1000 :
                        self.frame = cv2.imdecode(np.asarray(bytearray(r.content), dtype="uint8"), 1)
                    else:
                        self.request_OK = False
                        self.logger.warning('bad camera download on {} \n'.format(self.cam.name))
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, requests.exceptions.MissingSchema):
                    self.request_OK = False
                    self.logger.warning('network error on {} \n'.format(self.cam.name))
                    pass

            #*****************************Grab image in rtsp **********************************
            else :
                if not self.running_rtsp :
                    with self.lock:
                        try :
                            self.thread_rtsp.join()
                            self.logger.warning('close thread {} '.format(self.thread_rtsp))
                        except AttributeError:
                            pass
                        self.logger.warning('rtsp not running on cam {}, so launch '.format(self.cam.name))
                        self.thread_rtsp = Thread(target=self.grab)
                        self.thread_rtsp.start()
                        self.running_rtsp = True
            #*************************************************************************************
            t=time.time()
            # Normal stop point for ip camera-------------------------------
            if threated_requests :
                #self.event[self.num].wait() # NEED TO REMOVE ALL THE EVENT SYSTEM <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
                self.logger.debug('cam {} alive'.format(self.cam.id))
            #---------------------------------------------------------------
            if self.request_OK and self.Q_img.qsize() < settings.QUEUE_SIZE:
                with self.lock:
                    arr = self.frame.copy()
                th = self.cam.threshold*(1-(float(self.cam.gap)/100))
                self.logger.debug('thresh set to {}'.format(th))
                frame_rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                with self.tlock :
                    im, arrd = dn.array_to_image(frame_rgb)
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        result_dict={}
                        for key, network in net.items():
                            result_dict[key] = executor.submit(detect_thread, network, meta[key], im, th)
                if 'all' in result_dict:
                    result_darknet = [r for r in result_dict['all'].result() if r[0] not in self.black_list]
                    result_dict.pop('all')
                else :
                    result_darknet=[]
                for key, partial_result in result_dict.items():
                    result_darknet += partial_result.result()                        
                self.logger.info('get brut result from darknet in {}s : {} \n'.format(
                time.time()-t,result_darknet))
                self.event[self.num].clear()
                self.logger.debug('cam {} clear -> so wait !'.format(self.cam.id))
                self.event[((self.num)+1)%self.nb_cam].set()
                self.logger.debug('event {} set'.format((self.num+1)%self.nb_cam))

                # get only result above trheshlod or previously valid
                t=time.time()
                result_filtered, result_filtered_true  = self.check_thresh(result_darknet)
                # process image
                if self.cam.reso:
                    if arr.shape[0]!=self.cam.height or arr.shape[1]!=self.cam.width:
                        arr = cv2.resize(arr,(self.cam.width, self.cam.height), interpolation = cv2.INTER_CUBIC)
                img_bytes = cv2.imencode('.jpg', arr)[1].tobytes()
                # if gueue free
                if self.Q_img_real.qsize()<1:
                    # if on page camera HD
                    if EtoB(self.camera_state[1]):
                        resize_factor = self.cam.max_width_rtime_HD/arr.shape[1]
                        self.Q_img_real.put((self.cam.id, result_filtered_true, cv2.imencode('.jpg', arr)[1].tobytes(),resize_factor))
                        self.logger.warning('Q_img_real HD   on {} : size {}'.format(self.cam.name, self.Q_img_real.qsize()))
                    # if on page camera LD
                    elif EtoB(self.camera_state[0]):
                        resize_factor = self.cam.max_width_rtime/arr.shape[1]
                        arr = cv2.resize(arr,(self.cam.max_width_rtime, int(arr.shape[0]*resize_factor)), interpolation = cv2.INTER_CUBIC)
                        self.Q_img_real.put((self.cam.id, result_filtered_true, cv2.imencode('.jpg', arr)[1].tobytes(),resize_factor))
                        self.logger.warning('Q_img_real LD on {} : size {}'.format(self.cam.name, self.Q_img_real.qsize()))
                # compare with last result to check if different
                self.logger.debug('E_rec :{}'.format(EtoB(self.E_state)))
                if self.base_condition(result_filtered) and EtoB(self.E_state):
                    self.logger.debug('>>> Result have changed <<< ')
                    date = time.strftime("%Y-%m-%d-%H-%M-%S")
                    token = secrets.token_urlsafe(6)
                    self.Q_img.put((self.cam.id, date+'_'+token,result_filtered_true, img_bytes))
                    self.logger.warning('Q_img size : {}'.format(self.Q_img.qsize()))
                    self.Q_result.put((date+'_'+token+'.jpg', self.cam.id , result_filtered_true, result_darknet, self.image_correction[0]))
                    self.logger.warning('Q_result size : {}'.format(self.Q_result.qsize()))
                    self.logger.warning('>>>>>>>>>>>>>>>--------- Result change send to queue '
                    '-------------<<<<<<<<<<<<<<<<<<<<<\n')
                    self.result_DB = result_filtered
                self.logger.info('brut result process in {}s '.format(time.time()-t))
            else :
                self.event[self.num].clear()
                self.logger.debug('cam {} clear -> so wait !'.format(self.cam.id))
                self.event[((self.num)+1)%self.nb_cam].set()
                self.logger.debug('event {} set'.format((self.num+1)%self.nb_cam))
                time.sleep(0.5)

    def base_condition(self,new):
        compare = get_list_diff(new,self.result_DB,self.pos_sensivity)
        if len(compare[0])==0 and len(compare[1])==0 :
            if self.image_correction[0] and time.time()-self.image_correction[1] > 60*10:
                self.image_correction[1]= time.time()
                return True
            return False
        else:
            self.image_correction = [False, 0]
            self.logger.info('Change in objects detected : new={} lost={}'
            .format(compare[0], compare[1]))
            return True

    def check_thresh(self,resultb):
        #result = [(e1,e2,e3) if e1 not in self.clone else (self.clone[e1],e2,e3)
        #for (e1,e2,e3) in result]
        rp = [r for r in resultb if r[1]>=self.cam.threshold]
        last = self.result_DB.copy()
        self.get_lost(rp, last )
        obj_last, obj_new = self.search_result(last,resultb.copy(),rp)
        if obj_last and not self.image_correction[0] : 
            self.image_correction = [True, self.image_correction[1]]
        elif  not obj_last : 
            self.image_correction = [False, self.image_correction[1]] 
        self.logger.info('recovery objects from last detection :{} '.format(obj_last))
        rp_last = rp + obj_last
        rp_new = rp + obj_new
        self.logger.info('the filtered list of detected objects is {}'.format(rp_last))
        return rp_last, rp_new

    def search_result(self,lost,result,rp):
        # find if there is lost object in result
        obj_last = []
        obj_new = []
        for obj_lost in lost:
            find = None
            diff_pos_sav = 10000
            for obj_result in result:
                diff_pos = (sum([abs(i-j) for i,j in zip(obj_lost[2],obj_result[2])]))/(obj_lost[2][2]+obj_lost[2][3])*100
                if diff_pos < self.pos_sensivity and diff_pos < diff_pos_sav:
                    diff_pos_sav = diff_pos
                    find = obj_result
                    self.logger.debug('find object {} same as {}'.format(obj_result,obj_lost))
                    if find[1] > self.cam.threshold :
                        if find[0] not in self.force_remove:
                            self.force_remove[find[0]] =0
                        if self.force_remove[find[0]] < 5:
                            self.force_remove[find[0]] +=1
                            try :
                                rp.remove(find)
                            except ValueError:
                                pass
                    else:
                        self.force_remove[find[0]] =0        
            if find :
                result.remove(find)
                self.logger.info('find an object {} at same position than {}'.format(find,obj_lost))
                obj_new.append((obj_lost[0],)+find[1:])
                obj_last.append(obj_lost)
        return obj_last, obj_new

    def get_lost(self, new, last):
        # remove similar object so only lost are in last
        for obj_new in new:
            for obj_last in last:
                if obj_last[0]==obj_new[0] and (sum([abs(i-j) for i,j in zip(obj_new[2],obj_last[2])]))/(obj_last[2][2]+obj_last[2][3])*100 < self.pos_sensivity :
                    last.remove(obj_last)
                    break

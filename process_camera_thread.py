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
import settings
import os
import darknet as dn
from log import Logger
import secrets
import concurrent.futures



threated_requests = settings.THREATED_REQUESTS
path = settings.DARKNET_PATH
net = {}
meta = {}
width = {}
height = {}
class_names = {}

for key, values in settings.DARKNET_CONF.items():
    cfg = os.path.join(path, values['CFG']).encode()
    weights = os.path.join(path, values['WEIGHTS']).encode()
    data = os.path.join(path, values['DATA']).encode()
    net[key] = dn.load_net_custom(cfg, weights, 0, 1)
    meta[key] = dn.load_meta(data)
    class_names[key] = [meta[key].names[i].decode() for i in range(meta[key].classes)]
    width[key] = dn.network_width(net[key])
    height[key] = dn.network_height(net[key])


def detect_thread(my_net, my_class_names, frame, my_width, my_height, thresh):
    frame_resized = cv2.resize(frame, (my_width, my_height), interpolation=cv2.INTER_LINEAR)
    darknet_image = dn.make_image(my_width, my_height, 3)
    dn.copy_image_from_bytes(darknet_image, frame_resized.tobytes())
    detections = dn.detect_image(my_net, my_class_names, darknet_image, thresh=thresh)
    # make coordinate function of initial size
    height_factor = frame.shape[0] / my_height
    width_factor = frame.shape[1] / my_width
    detections = [(r[0], float(r[1]), (r[2][0]*width_factor, r[2][1]*height_factor,
                                       r[2][2]*width_factor, r[2][3]*height_factor)) for r in detections]
    dn.free_image(darknet_image)
    return detections


def get_list_diff(l_new, l_old, thresh):
    new_copy = l_new[:]
    old_copy = l_old[:]
    for e_new in l_new:
        flag = False
        limit_pos = thresh
        for e_old in l_old:
            if e_new[0] == e_old[0]:
                diff_pos = (sum([abs(i-j) for i, j in zip(e_new[2], e_old[2])]))/(e_old[2][2]+e_old[2][3])*100
                if diff_pos < thresh:
                    flag = True
                    if diff_pos < limit_pos:
                        limit_pos = diff_pos
                        to_remove = (e_new, e_old)
        if flag:
            new_copy.remove(to_remove[0])
            try:
                old_copy.remove(to_remove[1])
                new_copy.remove(to_remove[0])
            except ValueError:
                pass
    return new_copy, old_copy


def read_write(rw, *args):
    if rw == 'r':
        im = cv2.imread(*args)
        return im
    if rw == 'w':
        r = cv2.imwrite(*args)
        return r


def EtoB(E):
    if E.is_set():
        return True
    else:
        return False

# the base condition to store the image is : is there a new objects detection
# or a change in the localisation of the objects. It is not necessary to store
# billions of images but only the different one.


class ProcessCamera(Thread):
    """Thread used to grab camera images and process the image with darknet"""

    def __init__(self, cam, q_result, q_img, q_img_real, tlock, camera_state, e_state):
        Thread.__init__(self)
        self.cam = cam
        self.running = False
        self.running_rtsp = False
        self.pos_sensivity = cam['pos_sensivity']
        self.request_OK = False
        self.lock = Lock()
        self.tlock = tlock
        self.black_list = [i.encode() for i in settings.DARKNET_CONF['all']['RESTRICT']]
        self.logger = Logger('process_camera_thread__'+str(self.cam["id"])+'--'+self.cam["name"],
                             level=settings.PROCESS_CAMERA_LOG).run()
        self.Q_img = q_img
        self.Q_result = q_result
        self.result_DB = []
        self.Q_img_real = q_img_real
        self.force_remove = {}
        self.image_correction = [False, 0]
        self.vcap = None
        self.frame = None
        self.thread_rtsp = None
        #self.rec = False
        #self.real_time = {'HD': False, 'LD': False}
        self.camera_state = camera_state
        self.e_state = e_state

        if cam['auth_type'] == 'B':
            self.auth = requests.auth.HTTPBasicAuth(cam['username'], cam['password'])
        if cam['auth_type'] == 'D':
            self.auth = requests.auth.HTTPDigestAuth(cam['username'], cam['password'])

    def grab(self):
        rtsp = self.cam['rtsp']
        rtsp_login = 'rtsp://' + self.cam['username'] + ':' + self.cam['password'] + '@' + rtsp.split('//')[1]
        self.vcap = cv2.VideoCapture(rtsp_login)
        self.running_rtsp = self.vcap.isOpened()
        self.logger.warning('openning videocapture {} is {}'.format(self.vcap, self.vcap.isOpened()))
        i = 15
        bad_read = 0
        while self.running_rtsp:
            if i == 15:
                date = time.strftime("%Y-%m-%d-%H-%M-%S")
                ret, frame = self.vcap.read()
                self.logger.debug(f"resultat de la lecture rtsp : {ret}  pour {self.cam['name']}")
                self.logger.debug('*** {}'.format(date))
                t = time.time()
                if ret and len(frame) > 100:
                    bad_read = 0
                    if self.cam['reso']:
                        if frame.shape[0] != self.cam['height'] or frame.shape[1] != self.cam['width']:
                            frame = cv2.resize(frame, (self.cam['width'], self.cam['height']),
                                               interpolation=cv2.INTER_CUBIC)
                    with self.lock:
                        self.frame = frame
                        self.request_OK = True
                    self.logger.debug("resultat de l'ecriture de la frame : {} en {} ".format(
                            self.request_OK, time.time()-t))
                else:
                    self.request_OK = False
                    self.logger.warning('Bad rtsp read on {} videocapture is {}'.format(self.cam['name'],
                                                                                        self.vcap.isOpened()))
                    self.running_rtsp = self.vcap.isOpened()
                    bad_read += 1
                    if bad_read > 10:
                        break
                    time.sleep(0.5)
                i = 0
            self.vcap.grab()
            i += 1
        with self.lock:
            self.vcap.release()
            self.logger.warning('VideoCapture close on {}'.format(self.cam['name']))
            self.running_rtsp = False
            time.sleep(5)

    def run(self):
        """code run when the thread is started"""
        self.running = True
        while self.running:
            # ******************************Grab images in http ********************************
            if not self.cam['stream']:
                self.request_OK = True
                try:
                    t = time.time()
                    r = requests.get(self.cam['http'], auth=self.auth, stream=True, timeout=10)
                    self.logger.info(f'get http image {self.cam["http"]} in  {time.time()-t}s')
                    if r.status_code == 200 and len(r.content) > 1000:
                        self.frame = cv2.imdecode(np.asarray(bytearray(r.content), dtype="uint8"), 1)
                    else:
                        self.request_OK = False
                        self.logger.warning('bad camera download on {} \n'.format(self.cam['name']))
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                        requests.exceptions.ReadTimeout, requests.exceptions.MissingSchema):
                    self.request_OK = False
                    self.logger.warning('network error on {} \n'.format(self.cam['name']))
                    pass

            # *****************************Grab image in rtsp **********************************
            else:
                if not self.running_rtsp:
                    with self.lock:
                        try:
                            self.thread_rtsp.join()
                            self.logger.warning('close thread {} '.format(self.thread_rtsp))
                        except AttributeError:
                            pass
                        self.logger.warning('rtsp not running on cam {}, so launch '.format(self.cam['name']))
                        self.thread_rtsp = Thread(target=self.grab)
                        self.thread_rtsp.start()
                        self.running_rtsp = True
            # *************************************************************************************
            t = time.time()
            self.logger.debug(f'Q_img is  {self.Q_img.qsize()}')
            if self.request_OK and self.Q_img.qsize() < settings.QUEUE_SIZE:
                with self.lock:
                    arr = self.frame.copy()
                th = self.cam['threshold']*(1-(float(self.cam['gap'])/100))
                self.logger.debug('thresh set to {}'.format(th))
                frame_rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                with self.tlock:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        result_dict = {}
                        for nkey, network in net.items():
                            result_dict[nkey] = executor.submit(detect_thread, network, class_names[nkey],
                                                                frame_rgb, width[nkey], height[nkey], th)
                if 'all' in result_dict:
                    result_darknet = [r for r in result_dict['all'].result() if r[0] not in self.black_list]
                    result_dict.pop('all')
                else:
                    result_darknet = []
                for key, partial_result in result_dict.items():
                    result_darknet += partial_result.result()
                self.logger.info(f'{self.cam["name"]} -> brut result darknet {time.time()-t}s : {result_darknet} \n')
                # get only result above trheshlod or previously valid
                t = time.time()
                result_filtered, result_filtered_true  = self.check_thresh(result_darknet)
                # process image
                if self.cam['reso']:
                    if arr.shape[0] != self.cam['height'] or arr.shape[1] != self.cam['width']:
                        arr = cv2.resize(arr, (self.cam['width'], self.cam['height']), interpolation = cv2.INTER_CUBIC)
                img_bytes = cv2.imencode('.jpg', arr)[1].tobytes()
                # if gueue free
                if self.Q_img_real.qsize() < 1:
                    self.logger.info(f'camera state : {self.camera_state[self.cam["id"]]} / cam : {self.cam["name"]}')
                    # if on page camera HD
                    if EtoB(self.camera_state[self.cam['id']][1]):
                        resize_factor = self.cam['max_width_rtime_HD']/arr.shape[1]
                        self.Q_img_real.put((self.cam['id'], result_filtered_true, cv2.imencode('.jpg', arr)[1].tobytes(),
                                             resize_factor))
                        self.logger.warning('Q_img_real HD   on {} : size {}'.format(self.cam['name'],
                                                                                     self.Q_img_real.qsize()))
                    # if on page camera LD
                    elif EtoB(self.camera_state[self.cam['id']][0]):
                        resize_factor = self.cam['max_width_rtime']/arr.shape[1]
                        arr = cv2.resize(arr, (self.cam['max_width_rtime'], int(arr.shape[0]*resize_factor)),
                                         interpolation=cv2.INTER_CUBIC)
                        self.Q_img_real.put((self.cam['id'], result_filtered_true,
                                             cv2.imencode('.jpg', arr)[1].tobytes(), resize_factor))
                        self.logger.warning('Q_img_real LD on {} : size {}'.format(self.cam['name'],
                                                                                   self.Q_img_real.qsize()))
                # compare with last result to check if different
                self.logger.debug(f'rec :{EtoB(self.e_state)}')
                if self.base_condition(result_filtered) and EtoB(self.e_state):
                    self.logger.debug('>>> Result have changed <<< ')
                    date = time.strftime("%Y-%m-%d-%H-%M-%S")
                    token = secrets.token_urlsafe(6)
                    self.Q_img.put((self.cam['id'], date+'_'+token,result_filtered_true, img_bytes))
                    self.logger.warning('Q_img size : {}'.format(self.Q_img.qsize()))
                    self.Q_result.put((date+'_'+token+'.jpg', self.cam['id'], result_filtered_true, result_darknet,
                                       self.image_correction[0]))
                    self.logger.warning('Q_result size : {}'.format(self.Q_result.qsize()))
                    self.logger.warning('>>>>>>>>>>>>>>>--------- Result change send to queue '
                                        '-------------<<<<<<<<<<<<<<<<<<<<<\n')
                    self.result_DB = result_filtered
                self.logger.info('brut result process in {}s '.format(time.time()-t))
            else:
                time.sleep(0.5)

    def base_condition(self, new):
        compare = get_list_diff(new, self.result_DB, self.pos_sensivity)
        if len(compare[0]) == 0 and len(compare[1]) == 0:
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
        # result = [(e1,e2,e3) if e1 not in self.clone else (self.clone[e1],e2,e3)
        # for (e1,e2,e3) in result]
        rp = [r for r in resultb if float(r[1]) >= self.cam['threshold']]
        last = self.result_DB.copy()
        self.get_lost(rp, last)
        obj_last, obj_new = self.search_result(last, resultb.copy(), rp)
        if obj_last and not self.image_correction[0]:
            self.image_correction = [True, self.image_correction[1]]
        elif not obj_last:
            self.image_correction = [False, self.image_correction[1]] 
        self.logger.info('recovery objects from last detection :{} '.format(obj_last))
        rp_last = rp + obj_last
        rp_new = rp + obj_new
        self.logger.info('the filtered list of detected objects is {}'.format(rp_last))
        return rp_last, rp_new

    def search_result(self, lost, result, rp):
        # find if there is lost object in result
        obj_last = []
        obj_new = []
        for obj_lost in lost:
            find = None
            diff_pos_sav = 10000
            for obj_result in result:
                diff_pos = (sum([abs(i-j) for i, j in zip(obj_lost[2],obj_result[2])]))/(obj_lost[2][2]+obj_lost[2][3])\
                           * 100
                if diff_pos < self.pos_sensivity and diff_pos < diff_pos_sav:
                    diff_pos_sav = diff_pos
                    find = obj_result
                    self.logger.debug('find object {} same as {}'.format(obj_result, obj_lost))
                    if float(find[1]) > self.cam['threshold']:
                        if find[0] not in self.force_remove:
                            self.force_remove[find[0]] = 0
                        if self.force_remove[find[0]] < 5:
                            self.force_remove[find[0]] +=1
                            try:
                                rp.remove(find)
                            except ValueError:
                                pass
                    else:
                        self.force_remove[find[0]] = 0
            if find:
                result.remove(find)
                self.logger.info('find an object {} at same position than {}'.format(find,obj_lost))
                obj_new.append((obj_lost[0],)+find[1:])
                obj_last.append(obj_lost)
        return obj_last, obj_new

    def get_lost(self, new, last):
        # remove similar object so only lost are in last
        for obj_new in new:
            for obj_last in last:
                if obj_last[0] == obj_new[0] and (sum([abs(i-j) for i, j in zip(obj_new[2], obj_last[2])])) / \
                        (obj_last[2][2]+obj_last[2][3])*100 < self.pos_sensivity:
                    last.remove(obj_last)
                    break

"""
This part should be rewrite using a websocket for each camera, following this model : 
class Test(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.a = []
        self.loop=asyncio.new_event_loop()
    def run(self):
        print('ok')
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(asyncio.gather(self.task1(self.a), self.task2(self.a)))
    async def task1(self, a):
        for _ in range(10):
            self.a.append('toto')
            print(a)
            await asyncio.sleep(1)
    async def task2(self, a):
        for _ in range(10):
            self.a.append('tata')
            print(a)
            await asyncio.sleep(1)
t = Test()
t.start()
"""

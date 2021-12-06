import cv2
import time
import secrets
from functools import partial


async def get_list_diff(l_new, l_old, thresh):
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


class Img(object):

    def __init__(self, frame, loop):
        self.frame = frame
        self.loop = loop

    async def resize_img(self, width, height):
        return await self.loop.run_in_executor(None, partial(cv2.resize, self.frame, (width, height),
                                                             interpolation=cv2.INTER_CUBIC))

    async def bytes_img(self, frame):
        img_bytes = await self.loop.run_in_executor(None, cv2.imencode, '.jpg', frame)
        img_bytes = img_bytes[1]
        img_bytes = await self.loop.run_in_executor(None, img_bytes.tobytes)
        return img_bytes


class Result(object):

    def __init__(self, cam, logger, result_darknet, last_object):
        self.darknet = result_darknet
        self.last_objects = last_object
        self.filtered = []  # this is the real list of object return by darknet
        self.filtered_true = []  # this is the list corrected with rule : same place = same object
        self.time = time.time()
        self.correction = False
        self.upload = True
        self.logger = logger
        self.force_remove = {}
        self.correction = False
        self.cam = cam
        self.img = None
        self.token = None
        self.resolution = 'LD'

    async def process_result(self):
        obj_last, obj_new, obj_delete = await self.corrected_object_by_position()
        self.logger.info('recovery objects from last detection :{} '.format(obj_last))
        rp_last = await self.result_above_treshold(delete=obj_delete) + obj_last
        rp_new = await self.result_above_treshold(delete=obj_delete) + obj_new
        self.logger.info('the filtered list of detected objects is {}'.format(rp_last))
        self.filtered_true = rp_new  # this is the new result, corrected result
        self.filtered = rp_last  # this is the real result to keep trace of the history
        self.token = secrets.token_urlsafe(6)

    async def corrected_object_by_position(self):
        """
        Check of among lost objects from last detection you can find a similar one (same position) in the new objects
        obj_last : the lost objects you have retrieve
        obj_new : the new corrected objects (we keep the last object name 5 times) with new position
        warning this function should remove the corrected objects (wrong one) from the result above threshold list
        """
        result = self.darknet.copy()
        obj_last = []
        obj_new = []
        obj_delete = []
        for obj_lost in await self.result_lost():
            find = None
            diff_pos_sav = 10000
            for obj_result in result:
                diff_pos = (sum([abs(i - j) for i, j in zip(obj_lost[2], obj_result[2])])) / (
                            obj_lost[2][2] + obj_lost[2][3]) \
                           * 100
                if diff_pos < self.cam['pos_sensivity'] and diff_pos < diff_pos_sav:
                    diff_pos_sav = diff_pos
                    find = obj_result
                    self.logger.debug('find object {} same as {}'.format(obj_result, obj_lost))
                    if float(find[1]) > self.cam['threshold']:
                        if find[0] not in self.force_remove:
                            self.force_remove[find[0]] = 0
                        elif self.force_remove[find[0]] < 5:
                            self.force_remove[find[0]] += 1
                            obj_delete.append(find)
                    else:
                        self.force_remove[find[0]] = 0
            if find:
                result.remove(find)
                self.logger.info('find an object {} at same position than {}'.format(find, obj_lost))
                obj_new.append((obj_lost[0],) + find[1:])
                obj_last.append(obj_lost)
        if obj_last:
            self.correction = True
        else:
            self.correction = False
        return obj_last, obj_new, obj_delete

    async def result_above_treshold(self, delete=[]):
        return [r for r in self.darknet if float(r[1]) >= self.cam['threshold'] and r not in delete]

    async def result_lost(self):
        """
        Removing all objects from previous frame so objects remaining are :
        the lost objects from the last frame
        warning include objects with threshold now under the limit
        """
        last = self.last_objects.copy()
        for obj_new in await self.result_above_treshold():
            for obj_last in last:
                if obj_last[0] == obj_new[0] and (sum([abs(i-j) for i, j in zip(obj_new[2], obj_last[2])])) / \
                        (obj_last[2][2]+obj_last[2][3])*100 < self.cam['pos_sensivity']:
                    last.remove(obj_last)
                    break
        return last

    async def img_name(self, type_img):
        date = time.strftime("%Y-%m-%d-%H-%M-%S")
        if type_img == 'rec':
            name = date + '_' + self.token
        else:
            name = 'temp_img_cam_' + str(self.cam['id'])
        result_json = {'name': name, 'cam': self.cam['id'], 'result': self.filtered_true,
                       'resize_factor': await self.resize_factor(), }
        return result_json

    # async def resize_reso_max(self):
    #     if self.cam['reso']:
    #         return await self.img.resize(self.cam['height'], self.cam['width'])
    #     else:
    #         return False

    async def result_to_send(self, type_img):
        img_json = await self.img_name(type_img)
        result_json = {'img': img_json['name'], 'cam': self.cam['id'],
                       'result_filtered': self.filtered_true, 'result_darknet': self.darknet,
                       'correction': self.correction}
        return result_json

    async def img_to_send_real(self):
        if self.resolution == 'HD':
            frame = await self.img.resize_img(self.cam['max_width_rtime_HD'],
                                              int(self.img.frame.shape[0] * await self.resize_factor()))
        else:
            frame = await self.img.resize_img(self.cam['max_width_rtime'],
                                              int(self.img.frame.shape[0] * await self.resize_factor()))
        return await self.img.bytes_img(frame)

    async def img_to_send(self):
        if self.cam['reso']:
            frame = await self.img.resize_img(self.cam['width'], self.cam['height'])
        else:
            frame = self.img.frame
        return await self.img.bytes_img(frame)

    async def resize_factor(self):
        if self.resolution == 'HD':
            resize_factor = self.cam['max_width_rtime_HD'] / self.img.frame.shape[1]
        elif self.resolution == 'LD':
            resize_factor = self.cam['max_width_rtime'] / self.img.frame.shape[1]
        else:
            resize_factor = 1
        return resize_factor



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


def read_write(rw, *args):
    if rw == 'r':
        im = cv2.imread(*args)
        return im
    if rw == 'w':
        r = cv2.imwrite(*args)
        return r


class Img(object):

    def __init__(self, frame, loop):
        self.frame = frame
        self.loop = loop

    async def resize_img(self, width, height):
        return await self.loop.run_in_executor(None, cv2.resize, partial(self.frame, (width, height),
                                                                         interpolation=cv2.INTER_CUBIC))

    async def bytes_LD(self):
        pass

    async def bytes_HD(self):
        pass

    async def bytes_img(self, frame):
        img_bytes = await self.loop.run_in_executor(None, cv2.imencode, partial('.jpg', frame))
        img_bytes = img_bytes[1]
        img_bytes = await self.loop.run_in_executor(None, img_bytes.to_bytes)
        return img_bytes


class Result(object):

    def __init__(self, cam, logger, result_darknet):
        self.darknet = result_darknet
        self.filtered = []
        self.filtered_true = []
        self.time = time.time()
        self.correction = False
        self.upload = True
        self.logger = logger
        self.force_remove = {}
        self.correction = False
        self.json = {}
        self.cam = cam
        self.img = None
        self.token = None

    async def process_result(self):
        obj_last, obj_new = await self.split_result()
        self.logger.info('recovery objects from last detection :{} '.format(obj_last))
        rp_last = await self.result_above_treshold() + obj_last
        rp_new = await self.result_above_treshold() + obj_new
        self.logger.info('the filtered list of detected objects is {}'.format(rp_last))
        self.json['result_filtered'] = rp_last
        self.json['result_filtered_True'] = rp_new
        self.filtered_true = rp_last
        self.filtered = rp_new
        self.token = secrets.token_urlsafe(6)

    async def split_result(self):
        """
        Return objects split in objects present on last detection and object new
        """
        result = self.darknet.copy()
        obj_last = []
        obj_new = []
        for obj_lost in await self.result_lost():
            find = None
            diff_pos_sav = 10000
            for obj_result in self.darknet:
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
                        if self.force_remove[find[0]] < 5:
                            self.force_remove[find[0]] += 1
                            try:
                                rp = await self.result_above_treshold()
                                rp.remove(find)
                            except ValueError:
                                pass
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
        return obj_last, obj_new

    async def result_above_treshold(self):
        return [r for r in self.darknet if float(r[1]) >= self.cam['threshold']]

    async def result_lost(self):
        last = self.filtered.copy()
        for obj_new in await self.result_above_treshold():
            for obj_last in last:
                if obj_last[0] == obj_new[0] and (sum([abs(i-j) for i, j in zip(obj_new[2], obj_last[2])])) / \
                        (obj_last[2][2]+obj_last[2][3])*100 < self.cam['pos_sensivity']:
                    last.remove(obj_last)
                    break
        return last

    async def img_name(self):
        date = time.strftime("%Y-%m-%d-%H-%M-%S")
        return date + '_' + self.token

    # async def resize_reso_max(self):
    #     if self.cam['reso']:
    #         return await self.img.resize(self.cam['height'], self.cam['width'])
    #     else:
    #         return False

    async def result_to_send(self):
        return self.img_name, self.cam['id'], self.json['result_filtered_True'], self.darknet, self.correction

    async def img_to_send(self):
        if self.cam['reso']:
            frame = self.img.resize_img(self.cam['width'], self.cam['height'])
        else:
            frame = self.img.frame
        return await self.img.bytes_img(frame)

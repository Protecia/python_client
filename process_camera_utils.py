import cv2
import time


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


class Result(object):

    def __init__(self, pos_sensivity, threshold, logger, result_darknet):
        self.pos_sensivity = pos_sensivity
        self.threshold = threshold
        self.result_darknet = result_darknet
        self.result_filtered = []
        self.result_filtered_true = []
        self.time = time.time()
        self.correction = False
        self.upload = True
        self.logger = logger
        self.force_remove = {}
        self.image_correction = False
        self.result_json = {}

    async def base_condition(self):
        pass

    async def process_result(self):
        obj_last, obj_new = await self.split_result()
        self.logger.info('recovery objects from last detection :{} '.format(obj_last))
        rp_last = await self.result_above_treshold() + obj_last
        rp_new = await self.result_above_treshold() + obj_new
        self.logger.info('the filtered list of detected objects is {}'.format(rp_last))
        self.result_json['result_filtered'] = rp_last
        self.result_json['result_filtered_True'] = rp_new

    async def split_result(self):
        """
        Return objects split in objects present on last detection and object new
        """
        result = self.result_darknet.copy()
        obj_last = []
        obj_new = []
        for obj_lost in await self.result_lost():
            find = None
            diff_pos_sav = 10000
            for obj_result in self.result_darknet:
                diff_pos = (sum([abs(i - j) for i, j in zip(obj_lost[2], obj_result[2])])) / (
                            obj_lost[2][2] + obj_lost[2][3]) \
                           * 100
                if diff_pos < self.pos_sensivity and diff_pos < diff_pos_sav:
                    diff_pos_sav = diff_pos
                    find = obj_result
                    self.logger.debug('find object {} same as {}'.format(obj_result, obj_lost))
                    if float(find[1]) > self.threshold:
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
            self.image_correction = True
        else:
            self.image_correction = False
        return obj_last, obj_new

    async def result_above_treshold(self):
        return [r for r in self.result_darknet if float(r[1]) >= self.threshold]

    async def result_lost(self):
        last = self.result_filtered.copy()
        for obj_new in await self.result_above_treshold():
            for obj_last in last:
                if obj_last[0] == obj_new[0] and (sum([abs(i-j) for i, j in zip(obj_new[2], obj_last[2])])) / \
                        (obj_last[2][2]+obj_last[2][3])*100 < self.pos_sensivity:
                    last.remove(obj_last)
                    break
        return last


class Img(object):

    def __init__(self, name, img_bytes, result, resize_factor):
        self.img_bytes = img_bytes
        self.name = name
        self.result = result
        self.resize_factor = resize_factor

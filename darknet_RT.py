#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
Python 3 wrapper for identifying objects in image

@author: Xavier Robellet
@date: 20210401
"""

from ctypes import *
import cv2
import settings


class IMAGE(Structure):
    _fields_ = [("w", c_int),
                ("h", c_int),
                ("c", c_int),
                ("data", POINTER(c_float))]


class BOX(Structure):
    _fields_ = [("x", c_float),
                ("y", c_float),
                ("w", c_float),
                ("h", c_float)]


class DETECTION(Structure):
    _fields_ = [("cl", c_int),
                ("bbox", BOX),
                ("prob", c_float),
                ("name", c_char*20),
                ]


lib = CDLL(settings.RT_PATH + "/build/libdarknetTR.so", RTLD_GLOBAL)

load_network = lib.load_network
load_network.argtypes = [c_char_p, c_char_p, c_char_p, c_int, c_int, c_float]
load_network.restype = c_void_p

copy_image_from_bytes = lib.copy_image_from_bytes
copy_image_from_bytes.argtypes = [IMAGE, c_char_p]

make_image = lib.make_image
make_image.argtypes = [c_int, c_int, c_int]
make_image.restype = IMAGE

do_inference = lib.do_inference
do_inference.argtypes = [c_void_p, IMAGE]

get_network_boxes = lib.get_network_boxes
get_network_boxes.argtypes = [c_void_p, c_float, c_int, POINTER(c_int)]
get_network_boxes.restype = POINTER(DETECTION)


def detect_image(net, darknet_image, thresh, debug=False):
    num = c_int(0)
    if debug: print("Assigned num")
    pnum = pointer(num)
    if debug: print("Assigned pnum")
    do_inference(net, darknet_image)
    if debug: print("did prediction")
    dets = get_network_boxes(net, thresh, 0, pnum)
    if debug: print("Got dets")
    res = []
    for i in range(pnum[0]):
        b = dets[i].bbox
        res.append((dets[i].name.decode("ascii"), dets[i].prob, (b.x, b.y, b.w, b.h)))
    if debug: print("free detections")
    return res


class YOLO4RT(object):
    def __init__(self,
                 input_size,
                 weight_file,
                 conf_thres,
                 ):
        self.input_size = input_size
        self.metaMain =None
        self.model = load_network(weight_file.encode(), 15, 1)
        self.darknet_image = make_image(input_size, input_size, 3)
        self.thresh = conf_thres
         # self.resize_fn = ResizePadding(input_size, input_size)
         # self.transf_fn = transforms.ToTensor()

    def detect(self, image, need_resize=True):
        try:
            if need_resize:
                frame_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                image = cv2.resize(frame_rgb,
                                    (self.input_size, self.input_size),
                                    interpolation=cv2.INTER_LINEAR)
            frame_data = image.ctypes.data_as(c_char_p)
            copy_image_from_bytes(self.darknet_image, frame_data)

            detections = detect_image(self.model, self.darknet_image, self.thresh)

#             cvDrawBoxes(detections, image)
#             cv2.imshow("1", image)
#             cv2.waitKey(1)
#             detections = self.filter_results(detections, "person")
            return detections
        except Exception as e_s:
            print(e_s)

# -*- coding: utf-8 -*-
"""
Created on Sun Dec 22 11:11:54 2019

@author: julien
"""
import logging
from logging.handlers import RotatingFileHandler
import os
import settings
import sys
# ------------------------------------------------------------------------------
# a simple config to create a file log - change the level to warning in
# production
# ------------------------------------------------------------------------------


class Logger(object):
    def __init__(self, name, level=logging.ERROR, file=True):
        self.logger = logging.getLogger(name)
        if not len(self.logger.handlers):
            self.logger.setLevel(level)
            formatter = logging.Formatter('%(name)s :: %(asctime)s :: %(levelname)s :: %(message)s')
            if file:
                file_handler = RotatingFileHandler(os.path.join(settings.INSTALL_PATH+'/camera', name+'.log'),
                                                   'a', 10000000, 1)
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            screen_handler = logging.StreamHandler(stream=sys.stdout)
            screen_handler.setFormatter(formatter)
            self.logger.addHandler(screen_handler)
            self.logger.propagate = False

    def run(self):
        return self.logger




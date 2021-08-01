# -*- coding: utf-8 -*-
"""
Created on Sat Apr 11 17:56:13 2020

@author: julien
"""
from crontab import CronTab
import os
import settings


# install cron for backup rec
# don't forget to cd for the cron cd /home/protecia/NNvision/python_client &&
def install_rec_backup_cron():
    cron = CronTab(user=True)
    if not any(cron.find_command('video.py')):
        cmd = "cd "+settings.INSTALL_PATH+" && "
        cmd += settings.PYTHON+' '+os.path.join(settings.INSTALL_PATH, 'video.py')
        cmd += " > "+settings.INSTALL_PATH+"/camera/cron_video.log 2>&1&"
        job = cron.new(command=cmd)
        job.minute.every(1)
        cron.write()


def install_check_tunnel_cron():
    cron = CronTab(user=True)
    if not any(cron.find_command('check_tunnel')):
        cmd = "sleep 200 && cd "+settings.INSTALL_PATH+" && "
        cmd += settings.PYTHON+' '+os.path.join(settings.INSTALL_PATH, 'check_tunnel.py')
        cmd += " > "+settings.INSTALL_PATH+"/camera/cron_tunnel.log 2>&1&"
        job = cron.new(command=cmd)
        job.minute.every(10)
        cron.write()


if __name__ == "__main__":
    install_rec_backup_cron()
    install_check_tunnel_cron()

# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 19:31:50 2020

@author: julien
"""
import socket
import time
import settings
import psutil
import subprocess
import json
from log import Logger, logging


logger = Logger(__name__, level=logging.DEBUG, file=False).run()

retry = 3
delay = 2
timeout = 3


def is_open(host_o, port_o):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        logger.info(f'try connecting {host_o} / {port_o}')
        s.connect((host_o, port_o))
        s.shutdown(socket.SHUT_RDWR)
        return True
    except OSError:
        return False
    finally:
        s.close()


def check_host():
    host_check = settings.SERVER.split('/')[2]
    with open(settings.INSTALL_PATH + '/conf/docker.json', 'r') as conf_json:
        data = json.load(conf_json)
    port_check = int(data['tunnel_port'])
    ipup_check = False
    for i in range(retry):
        if is_open(host_check, port_check) and is_open(host_check, port_check+1000):
            ipup_check = True
            break
        else:
            time.sleep(delay)
    return ipup_check, host_check, port_check


if __name__ == '__main__':
    ipup, host, port = check_host()
    if not ipup:
        print(host, 'is DOWN')
        for proc in psutil.process_iter():
            # check whether the process name matches
            if 'ssh' in proc.name() and 'sshd' not in proc.name():
                try:
                    proc.kill()
                except psutil.AccessDenied:
                    pass
        user = settings.SSH_USER + '@' + host
        cmd = f"autossh -o StrictHostKeyChecking=no -C -N -f -n -T -p {settings.SSH_SERVER_PORT} " \
              f"-R {port}:localhost:22  -R {port+1000}:localhost:2525  {user}"
        logger.info(f'cmd is {cmd}')
        subprocess.call(cmd, shell=True)

    # on docker restart autossh
    # on nano reboot

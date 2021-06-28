# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 19:31:50 2020

@author: julien
"""

import socket
import time
import settings.settings as settings
import psutil
import subprocess
import json

# ip = settings.TUNNEL_IP
# port = settings.TUNNEL_PORT
retry = 3
delay = 2
timeout = 3


def is_open(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        s.shutdown(socket.SHUT_RDWR)
        return True
    except:
        return False
    finally:
        s.close()


def check_host(ip, port):
    ip = settings.SERVER.split('//')[1]
    with open(settings.INSTALL_PATH + '/settings/docker.json', 'r') as conf_json:
        data = json.load(conf_json)
    port = data['tunnel_port']
    ipup = False
    for i in range(retry):
        if is_open(ip, port) and is_open(ip, port+1000):
            ipup = True
            break
        else:
            time.sleep(delay)
    return ipup


if __name__ == 'main':
    if not check_host():
        print(settings.SERVER.split('//')[1], 'is DOWN')
        for proc in psutil.process_iter():
            # check whether the process name matches
            if 'ssh' in proc.name() and 'sshd' not in proc.name():
                try:
                    proc.kill()
                except psutil.AccessDenied:
                    pass
        subprocess.call("./sshtunnel.sh")


    # on docker restart autossh
    # on nano reboot

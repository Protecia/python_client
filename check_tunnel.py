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

ip = "client.protecia.com"
port = settings.TUNNEL_PORT
retry = 3
delay = 2
timeout = 3

def isOpen(ip, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
                s.connect((ip, int(port)))
                s.shutdown(socket.SHUT_RDWR)
                return True
        except:
                return False
        finally:
                s.close()

def checkHost(ip, port):
        ipup = False
        for i in range(retry):
                if isOpen(ip, port) and isOpen(ip, port+1):
                        ipup = True
                        break
                else:
                        time.sleep(delay)
        return ipup

if not checkHost(ip, port):
    print(ip,'is DOWN')
    for proc in psutil.process_iter():
        # check whether the process name matches
        if 'ssh' in proc.name():
            proc.kill()
    subprocess.call("./sshtunnel.sh")

        
    # on docker restart autossh
    # on nano reboot
    
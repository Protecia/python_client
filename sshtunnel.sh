#!/bin/bash
port=`python3 port_ssh_tunnel.py`
sshpass -p 'protecia2020' autossh -o StrictHostKeyChecking=no -N -R $port:localhost:22 -p 2222 sshtunnel@client.protecia.com &
sshpass -p 'protecia2020' autossh -o StrictHostKeyChecking=no -N -R $(($port+1)):localhost:2525 -p 2222 sshtunnel@client.protecia.com &

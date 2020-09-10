#!/bin/bash
port=`python3 port_ssh_tunnel.py port`
user=`python3 port_ssh_tunnel.py user`
server=`python3 port_ssh_tunnel.py ssh_server`
#sshpass -p 'ki4d6z' autossh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N -R $port:localhost:22 -p 2222 cez542de@client.protecia.com &
#sshpass -p 'ki4d6z' autossh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N -R $(($port+1)):localhost:2525 -p 2222 cez542de@client.protecia.com &
autossh -C -N -f -n -T -p $server -R $port:localhost:22  -R $(($port+1)):localhost:2525  $user

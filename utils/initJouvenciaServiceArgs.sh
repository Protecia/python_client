#Création d un script lancant l interface utilisateur

touch /home/$1/Documents/runUserInterface.py

echo "#!/usr/bin/env python3
import os
import json
import webbrowser
import subprocess
with open('/home/nnvision/conf/conf.json') as n:
    keyLoader = json.load(n)

firefox = '/usr/bin/firefox %s'
key = keyLoader["'"'"key"'"'"]
address = f'https://dev.jouvencia.net/app4/auth/{key}/'
os.system('export DISPLAY=:1')
subprocess.run(['/usr/bin/chromium-browser', '--no-sandbox', '--kiosk', address])

" > /home/$1/Documents/runUserInterface.py
chmod +x /home/$1/Documents/runUserInterface.py

touch /home/$1/Documents/runUserInterface.desktop

echo "[Desktop Entry]
Name=LXTerminal
Type=Application
Exec=/home/$1/Documents/runUserInterface.py
" > /home/$1/Documents/runUserInterface.desktop

cp /home/$1/Documents/runUserInterface.desktop /etc/xdg/autostart/runUserInterface.desktop
touch ~/.config/autostart
echo "[Desktop Entry]
Name=LXTerminal
Type=Application
Exec=/home/$1/Documents/runUserInterface.py
" > ~/.config/autostart


#Creation du script lançant un container dans le cas d un reboot

touch /home/$1/Documents/runOnStartup.py
echo "#!/usr/bin/env python3
import subprocess
import json


with open('/home/nnvision/conf/docker.json') as nextVersion:
    update = json.load(nextVersion)

n = update["'"'"docker_version"'"'"]
pullName='roboticia/nnvision_jetson_nano:'+str(n)
dockrun='docker run -d --restart unless-stopped --entrypoint /NNvision/python_client/start.sh --gpus=all --name nnvision --net=host -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video -v /home/nnvision/conf:/NNvision/python_client/settings -v /usr/src/jetson_multimedia_api:/usr/src/jetson_multimedia_api -v nn_camera:/NNvision/python_client/camera -v /proc/device-tree/chosen:/NNvision/uuid ' + str(pullName)
subprocess.run(dockrun.split(' '))
print('Container started')" > /home/$1/Documents/runOnStartup.py
chmod +x /home/$1/Documents/runOnStartup.py

#Creation du script lancé par le service
systemctl daemon-reload
cd
cd /home/$1/Documents/
rm initJouvenciaScript
touch initJouvenciaScript
echo "#!/bin/bash
if [[ '$(docker images -q roboticia/nnvision_jetson_nano 2> /dev/null)' ]]; then
    echo 'a new image already exists'
    python3 /home/$1/Documents/runUserInterface.py
    python3 /home/$1/Documents/runOnStartup.py
else
    cd
    rm pass.txt
    touch pass.txt
    echo 'aicnevuoj*26' > pass.txt
    cat ~/pass.txt | docker login --username yayab42 --password-stdin
    rm pass.txt
    docker pull roboticia/nnvision_jetson_nano:0.2
    docker run  -d --restart unless-stopped --entrypoint /NNvision/python_client/start.sh --gpus=all --name nnvision --net=host \
                -e NVIDIA_VISIBLE_DEVICES=all \
                -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video  \
                -v /home/nnvision/conf:/NNvision/python_client/settings \
                -v /usr/src/jetson_multimedia_api:/usr/src/jetson_multimedia_api\
                -v nn_camera:/NNvision/python_client/camera \
                -v /proc/device-tree/chosen:/NNvision/uuid \
fi
" > /home/$1/Documents/initJouvenciaScript
chmod +x initJouvenciaScript

#Creation du service qui lance le script

cd
cd /etc/systemd/system/
rm initJouvenciaService.service
touch initJouvenciaService.service
echo "[Unit]
Description=initJouvenciaScript Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$1
WorkingDirectory=/home/$1/Documents
ExecStart=/home/$1/Documents/initJouvenciaScript

[Install]
WantedBy=multi-user.target" > /etc/systemd/system/initJouvenciaService.service

systemctl stop initJouvenciaService.service
chmod 777 /etc/systemd/system/initJouvenciaService.service
systemctl enable initJouvenciaService.service

#Initialisation du cron vérifiant la version actuelle avec la version à jour

apt install jq
cd /home/$1/Documents
touch updateScript.py
touch login
echo "#!/bin/bash
cd
rm pass.txt
touch pass.txt
echo 'aicnevuoj*26' > pass.txt
cat ~/pass.txt | docker login --username yayab42 --password-stdin
rm pass.txt" > /home/$1/Documents/login
chmod +x /home/$1/Documents/login
echo "#!/usr/bin/env python3
import subprocess
import json
import os


with open('/home/nnvision/conf/docker.json') as nextVersion:
    update = json.load(nextVersion)

cont = subprocess.check_output(['docker', 'ps'])
version=cont.decode().split('roboticia/nnvision_jetson_nano:')[1].split(' ')[0]
name='roboticia/nnvision_jetson_nano:'+str(version)
n = update["'"'"docker_version"'"'"]
pullName='roboticia/nnvision_jetson_nano:'+str(n)
if str(n) != str(version):
    subprocess.run(['docker', 'stop', 'nnvision'])
    print('Container stopped')
    subprocess.run(['docker', 'image', 'rm', name])
    print('Image rm')
    subprocess.run(['/home/$1/Documents/login'])
    print('login succeed')
    subprocess.run(['docker','pull', pullName])
    print('Pull succeed')
    dockrun='docker run -d --restart unless-stopped --entrypoint /NNvision/python_client/start.sh --gpus=all --name nnvision --net=host -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video -v /home/nnvision/conf:/NNvision/python_client/settings -v /usr/src/jetson_multimedia_api:/usr/src/jetson_multimedia_api -v nn_camera:/NNvision/python_client/camera -v /proc/device-tree/chosen:/NNvision/uuid ' + str(pullName)
    subprocess.run(dockrun.split(' '))
    print('Container started')
" > /home/$1/Documents/updateScript.py
chmod +x /home/$1/Documents/updateScript.py



echo "*/2 * * * *  root /home/$1/Documents/updateScript.py > /home/$1/Documents/logs.txt 2>&1&" >> /etc/crontab



#Initialisation du cron vérifiant si la jetson doit reboot

cd /home/$1/Documents
touch rebootScript
echo '#!/bin/bash

reboot=$(jq -r .reboot /home/nnvision/conf/docker.json )
if [[ reboot == '"'"'true'"'"' ]]; then
    sleep 200
    reboot
    
fi' > /home/$1/Documents/rebootScript

echo "*/5 * * * *  root /home/$1/Documents/rebootScript
#
" >> /etc/crontab

chmod +x /home/$1/Documents/rebootScript

systemctl enable cron
echo $version
echo $versionUpdate

#Set up de l UX/UI
apt install crudini
crudini --set /etc/gdm3/custom.conf daemon AutomaticLoginEnable true
crudini --set /etc/gdm3/custom.conf daemon AutomaticLogin $1
gsettings set org.gnome.desktop.screensaver lock-enabled false
chmod -x $(type -p gnome-keyring-daemon)

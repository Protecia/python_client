#!/bin/bash
echo "deb https://repo.download.nvidia.com/jetson/common r32.7 main" > /etc/apt/sources.list.d/nvidia-l4t-apt-source.list
echo "deb https://repo.download.nvidia.com/jetson/t210 r32.7 main"  >> /etc/apt/sources.list.d/nvidia-l4t-apt-source.list
sudo apt -y update
yes | sudo DEBIAN_FRONTEND=noninteractive apt  -y dist-upgrade
# maybe yes | apt install foo
sudo apt install -y nvidia-jetpack
date > /home/nnvision/patch1.ok

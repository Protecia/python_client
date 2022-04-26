#!/bin/bash
echo "deb https://repo.download.nvidia.com/jetson/common r32.7 main" > /etc/apt/sources.list.d/nvidia-l4t-apt-source.list
echo "deb https://repo.download.nvidia.com/jetson/t210 r32.7 main"  >> /etc/apt/sources.list.d/nvidia-l4t-apt-source.list
sudo apt -y update
sudo apt  -y dist-upgrade
echo date > /home/nnvision/patch1.ok

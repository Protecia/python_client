#!/bin/bash

cat repo.txt > /etc/apt/sources.list.d/nvidia-l4t-apt-source.list
sudo apt update
sudo apt dist-upgrade
echo date > /home/nnvision/patch1.ok

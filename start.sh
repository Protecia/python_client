#!/bin/bash
service cron start
/NNvision/sshtunnel.sh
python3 /NNvision/main.py

#!/bin/bash
service cron start
python3 /NNvision/python_client/check_tunnel.py
python3 /NNvision/python_client/install_cron.py
python3 /NNvision/python_client/main.py

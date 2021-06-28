#!/bin/bash
service cron start
python3 /NNvision/python_client/install_cron.py
python3 /NNvision/python_client/main.py

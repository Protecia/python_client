#!/bin/bash
docker run  --restart unless-stopped  --entrypoint /NNvision/python_client/start.sh --gpus=all --name nnvision --net=host \
            -e NVIDIA_VISIBLE_DEVICES=all \
            -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video  \
            -v /home/nnvision/conf:/NNvision/python_client/settings \
            -v /usr/src/jetson_multimedia_api:/usr/src/jetson_multimedia_api\
            -v nn_camera:/NNvision/python_client/camera \
            -v /proc/device-tree/chosen:/NNvision/uuid \
            roboticia/nnvision_jetson_nano:0.3

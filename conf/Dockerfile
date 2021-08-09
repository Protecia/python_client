FROM nvcr.io/nvidia/l4t-ml:r32.5.0-py3

RUN apt-get update && apt-get install -y apt-utils && rm -rf /var/lib/apt/lists/*

# Set the locale
RUN  apt-get update && apt-get install locales && locale-gen en_US.UTF-8 && rm -rf /var/lib/apt/lists/*
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
tzdata libxml2-dev libxslt-dev \
               wget mlocate build-essential openssh-client sshpass\
               nano cron yasm cmake libjpeg-dev autossh \
               libpng-dev libtiff-dev libavcodec-dev libavformat-dev \
               libswscale-dev libv4l-dev libxvidcore-dev libx264-dev  \
               libgtk-3-dev libatlas-base-dev gfortran libpq-dev curl fail2ban

WORKDIR /NNvision

RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python3 get-pip.py

RUN pip install psutil Pillow WSDiscovery requests onvif_zeep-roboticia cherrypy python-crontab

ENV LD_LIBRARY_PATH=/usr/local/cuda-10.2/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}

RUN git clone https://github.com/AlexeyAB/darknet

RUN cd  darknet  && \
	sed -i '1,10s/GPU=.*/GPU=1/' Makefile && \
	sed -i '1,10s/CUDNN=.*/CUDNN=1/' Makefile && \
	sed -i '1,10s/OPENCV=.*/OPENCV=1/' Makefile && \
	sed -i '1,10s/LIBSO=.*/LIBSO=1/' Makefile

# darknet have to be compiled in the container and commit after -> cd darknet && make -j4 && ldconfig


CMD ["/NNvision/python_client/start.sh"]

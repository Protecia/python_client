FROM nnvision_client_base

RUN pip3 install python-crontab

WORKDIR /NNvision
COPY . /NNvision


CMD ["/NNvision/start.sh"]

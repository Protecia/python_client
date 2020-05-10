FROM nnvision_client_base

WORKDIR /NNvision
COPY . /NNvision


CMD ["/NNvision/start.sh"]

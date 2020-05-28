FROM nnvision_client_base2

WORKDIR /NNvision
COPY . /NNvision


CMD ["/NNvision/start.sh"]

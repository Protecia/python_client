import settings
import json


def get_conf(value):
    try:
        with open(settings.INSTALL_PATH + '/conf/conf.json', 'r') as conf_json:
            data = json.load(conf_json)
    except (KeyError, FileNotFoundError):
        pass
    return data[value]
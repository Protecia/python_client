import settings.settings as settings
import json


def get_conf(value):
    try:
        with open(settings.INSTALL_PATH + '/settings/conf.json', 'r') as conf_json:
            data = json.load(conf_json)
    except (KeyError, FileNotFoundError):
        pass
    return data[value]
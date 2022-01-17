import json
import settings

with open(settings.INSTALL_PATH + '/conf/ping.json', 'r') as ping:
    ping = json.load(ping)

import json
from datetime import datetime


def main():
    try:
        with open('home/nnvision/conf/ping.json', 'r') as f:
            ping = json.load(f)
    except json.decoder.JSONDecodeError:
        print('bad json load, maybe file was writing')

    delta_time = datetime.now() - datetime.strptime(ping['last'], '%Y-%m-%d %H:%M:%S')
    if delta_time.total_seconds() > 500:
        with open('/home/nnvision/conf/force_reboot.json', 'r') as f:
            json.dump({'force_reboot': True, }, f)


if __name__ == '__main__':
    main()




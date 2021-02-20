import sys
from settings import settings
from utils import get_conf

if 'port' in sys.argv :
    print(settings.TUNNEL_PORT)
elif 'ip' in sys.argv:
    print(settings.TUNNEL_IP)
elif 'user' in sys.argv:
    print(settings.TUNNEL_USER)
elif 'ssh_server' in sys.argv:
    print(settings.SSH_SERVER)

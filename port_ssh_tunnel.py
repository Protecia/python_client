import sys
from settings import settings

if  'port' in sys.argv :
    print(settings.TUNNEL_PORT)
elif 'ip' in sys.argv:
    print(settings.TUNNEL_IP)
elif 'user' in sys.argv:
    print(settings.TUNNEL_USER)
    

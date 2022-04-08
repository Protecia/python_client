def change_ip(on_vif_camera):
    return on_vif_camera.devicemgmt.SetNetworkInterfaces(
        {'InterfaceToken': 'eth0', 'NetworkInterface': {'IPv4': {'Enabled': True, 'Manual': [
            {'Address': '192.168.1.20', 'PrefixLength': 24}], 'DHCP': False}}}
    )


def get_ip(onvif_camera):
    return onvif_camera.devicemgmt.GetNetworkInterfaces()


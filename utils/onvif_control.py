def change_ip(on_vif_camera):
    return on_vif_camera.devicemgmt.SetNetworkInterfaces(
        {'InterfaceToken': 'eth0', 'NetworkInterface': {'IPv4': {'Enabled': True, 'Manual': [
            {'Address': '192.168.1.20', 'PrefixLength': 24}], 'DHCP': False}}}
    )


def get_ip(onvif_camera):
    return onvif_camera.devicemgmt.GetNetworkInterfaces()

# http://www.onvif.org/wp-content/uploads/2016/12/ONVIF_WG-APG-Application_Programmers_Guide-1.pdf
# https://github.com/FalkTannhaeuser/python-onvif-zeep
# time_params = mycam.devicemgmt.create_type('SetSystemDateAndTime')
# time_params.DateTimeType = 'NTP'
# time_params.DaylightSavings = True
# time_params.TimeZone = 'GMT+02:00'
# mycam.devicemgmt.SetSystemDateAndTime(time_params)


import os
import socket
socket_name = '/tmp/%s.s' % 'test'
if os.path.exists(socket_name):
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        client.connect(socket_name)
        client.sendall(b'report,_1_halimeh')
    except:
        print('don"t know')

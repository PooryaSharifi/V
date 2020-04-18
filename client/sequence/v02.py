import time
from random import randint, choice
from threading import Thread
import requests
from tools.maths import rnd
from client.motors.v07 import Motor
from client import host, tehran, fastness
from static.names import names
from client.simulator import motors, app, logger, paths, os
from sanic.response import json
from datetime import datetime
from ego import encrypt
import csv

admin_key = encrypt('a', 'admin', '', datetime.now())
requests.delete(host + '/!!/food/locations', data={'key': admin_key, 'q': '{}'})
requests.delete(host + '/!!/food/paths', data={'key': admin_key, 'q': '{}'})
requests.delete(host + '/!!/food/users', data={'key': admin_key, 'q': '{}'})

response = requests.post(host + '/food/@credit=1000000,@password=123', data={'key': admin_key})
b_key = response.json()['key']


head = int(randint(0, 6) * 2 * 3600 / fastness)
extra = int(choice('000114'))
extra = 2
response = requests.post(host + '/food/~{},{};{},{}'.format('_', '_', *rnd(tehran)), data={
    'key': b_key,
    'volume': 2,
    **({'extra': extra} if extra else {}),
    'priority': 1,
    'delay': 400,
    'head': head,
    'tail': int(head + 2 * 3600 / fastness),
}, timeout=5).json()
print(response)

requests.post(host + '/food/!!!/hng', data={'key': b_key})

import pandas as pd
from random import choices
from bson import ObjectId
from datetime import datetime, timedelta
import requests

xl = pd.read_excel('/home/poorya/Downloads/routing_input.xlsx')

orders = []
for key, values in xl.items():
    for i, value in enumerate(values):
        if len(orders) <= i:
            orders.append(dict())
        orders[i][key] = value

depot = orders[0]
orders = orders[1:]

size = sum(o['per month'] for o in orders)
size /= 30
size = int(size)

chooses = choices(orders, weights=[o['per month'] for o in orders], k=size)


hang = '_'
now = datetime.now()
for i, ch in enumerate(chooses):
    _id = ObjectId()
    chooses[i] = {
        '_id': _id,
        # '_date': now,
        'hang': hang,
        'points': [  # TWISTED
            {
                '_id': _id,
                # 'window': [],
                'location': [ch['lat'], ch['lng']],
                '_author': hang,
                # 'at': datetime.now(),
                **({
                       'head': now + timedelta(seconds=0),
                       'tail': now + timedelta(seconds=int(3600 * 8)),
                       'bound': (now + timedelta(seconds=int(3600 * 8))).timestamp()
                   } if True else {})
            }, {
                '_id': _id,
                '_date': now,
                '_author': hang,
                'volume': ch['demands'],
                'head': now,
                'tail': 0,
                'location': [depot['lat'], depot['lng']],
                'priority': 0,
                # 'at': datetime.now()
                'territory': 0
            }
        ],
        'porters': []
    }

# login in version .2 it is in client doesn't need kes exists already

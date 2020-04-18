import numpy as np
import json
from bson import ObjectId
from datetime import datetime
import ujson
from mmap import mmap
from tools.maths import rnd as _rnd
from tools.maths import inside
from static.restaurants import restaurants
from static import tehran
from random import choice
import socket
import os


def awake(listeners, hang, msg):
    client = listeners.get(hang, None)
    if client is None:
        socket_name = '/tmp/%s.s' % hang
        if os.path.exists(socket_name):
            client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            try:
                client.connect(socket_name)
            except:
                try:
                    os.remove('/tmp/%s.s' % hang)
                except:
                    pass
                client = False
        else:
            client = False
        listeners[hang] = client
    if client:
        try:
            client.sendall(msg.encode())
        except:
            try:
                os.remove('/tmp/%s.s' % hang)
            except:
                pass


def gaussian(location, std):
    std /= 100000
    std = std ** 2
    locations = np.random.multivariate_normal(location, [[std, 0], [0, std]], 7)
    for _location in locations:
        if inside(*_location, tehran):
            return _location
    return gaussian(location, std)


restaurant = lambda: choice(restaurants)
rnd = lambda: _rnd(tehran)
parse_location = lambda location: [float(word.replace('%20', " ").strip()) for word in location.split(',')]
parse_path = lambda path: np.ravel([parse_location(word) for word in path.split(';')])
points = lambda ps: ';'.join(['{},{}'.format(*reversed(p)) for p in ps])


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId) or isinstance(o, datetime):
            return str(o)
        return json.JSONEncoder.default(self, o)


def obj2str(tree):
    if isinstance(tree, dict):
        for k, node in tree.items():
            tree[k] = obj2str(node)
        return tree
    elif isinstance(tree, list):
        _tree = []
        for node in tree:
            _tree.append(obj2str(node))
        return _tree
    elif isinstance(tree, ObjectId) or isinstance(tree, datetime):
        return str(tree)
    else:
        return tree


def pathify(paths, twist=False):
    paths = ujson.loads(paths)
    d_format = '%Y-%m-%d %H:%M:%S.%f'
    for path in paths:
        path['_id'] = ObjectId(path['_id'])
        if 'lock' in path:
            path['lock'] = ObjectId(path['lock'])
        if twist:
            path['points'] = list(reversed(path['points']))
        for i, p in enumerate(path['points']):
            p['_id'] = ObjectId(p['_id'])
            if 'head' in p:
                p['head'] = datetime.strptime(p['head'], d_format)
            if 'tail' in p:
                p['tail'] = datetime.strptime(p['tail'], d_format)
            if '_date' in p:
                p['_date'] = datetime.strptime(p['_date'], d_format)
        for p in path['porters']:
            if '_date' in p:
                p['_date'] = datetime.strptime(p['_date'], d_format)
    return paths


if __name__ == '__main__':
    r = gaussian((0, 0), 5000)
    m = np.sum(r, axis=0) / len(r)
    print(m)
    s = 0
    for x in r:
        x -= m
        s += x[0] ** 2 + x[1] ** 2
    s /= len(r)
    s = s ** .5
    print(s)

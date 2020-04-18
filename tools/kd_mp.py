import time
import numpy as np
import multiprocessing as mp
import ctypes
from scipy.spatial import cKDTree
import pickle
import os
import subprocess
from mmap import mmap
from osmread import parse_file, Way, Node, Relation
import struct
from random import random, randint
from multiprocessing.managers import BaseManager
from datetime import datetime, timedelta
from pymongo import MongoClient

# os.system("ps u -p %s | awk '{sum=sum+$6}; END {print sum/1024}'" % os.getpid())

# manager = mp.Manager()
#
# n = time.time()
#
# shared_nodes = [{'k{}'.format(2 * j): i for j in range(200)} for i in range(60000)]
#
# print(time.time() - n)
# n = time.time()
#
# shared_nodes = manager.list(shared_nodes)
#
# print(time.time() - n)
# shared_nodes[4]['yt'] = 2

# print(len(shared_nodes))
# print(time.time() - n)
# print(10 / 33000)


class Family:
    """
    400 * 500 * 150 = 28s
    400 * 500 * 15 = 4s
    """
    def __init__(self, region):
        self.region = region
        self._hang = []
        try:
            self.kd, self.porters = self.load(region)
        except FileNotFoundError:
            self.kd, self.porters = self.init(region)

    @staticmethod
    def load(region):
        with open('static/{}.pkl'.format(region), 'rb') as f:
            kd = pickle.load(f)
        with open('static/porters.pkl', 'rb') as f:
            porters = pickle.load(f)
        return kd, porters

    @staticmethod
    def init(region):
        nodes = []
        for entity in parse_file('/home/pouria/Downloads/osm/{}.osm'.format(region)):
            if isinstance(entity, Node):
                nodes.append([entity.lat, entity.lon])

        return cKDTree(nodes), {}

    def save(self):
        with open('static/{}.pkl'.format(self.region), 'wb') as f:
            pickle.dump(self.kd, f, protocol=pickle.HIGHEST_PROTOCOL)

        with open('static/{}.pkl'.format('porters'), 'wb') as f:
            pickle.dump(self.porters, f, protocol=pickle.HIGHEST_PROTOCOL)

    def hang(self, hang):
        self._hang = hang

    def inc(self, lat, lng, porter, weight):
        _, ids = self.kd.query([lat, lng], k=1)
        for _id in ids:
            self.porters[porter][_id] += weight
        pass

    def merge(self, old, new):
        if old not in self.porters or new not in self.porters:
            return
        _old, old, new = old, self.porters[old], self.porters[new]
        for _id, w in old.items():
            if _id not in new:
                new[_id] = 0
            new[_id] += w
        del self.porters[old]

    def update(self, head, tail=0):
        now = datetime.now()
        head = now - timedelta(days=head)
        tail = now - timedelta(days=tail)
        locations = MongoClient(port=27020).express.locations.find({'_date': {'$gte': head, '$lt': tail}})
        for location in locations:
            self.inc(*location['location'], ('' if location['porter'][1:].isalnum() else location['hang']) + location['porter'], 1)
        for porter, nodes in self.porters.items():
            if len(nodes) > 10000:
                self.porters[porter] = dict(sorted(nodes.items(), key=lambda _id, w: -w)[: 5000])

    def familiarity(self, lat, lng):
        _, ids = self.kd.query([lat, lng], k=150)
        return [round(sum((self.porters[porter][_id] if _id in self.porters[porter] else 0) * (151 - _idx) ** .2 for _idx, _id in enumerate(ids))) if porter in self.porters else 0 for porter in self._hang]


if __name__ == '__main__':
    BaseManager.register('Family', Family)
    manager = BaseManager()
    manager.start()
    f = manager.Family('tehran')
    from static.names import names
    names = sum([[str(i) + '_' + name for i in range(3)] for name in names], [])
    f.hang(names)
    print('here')
    n = time.time()
    for i in range(500):
        lat, lng = 31 + i / 10, 53 + i / 10
        f.familiarity(lat, lng)
    print(time.time() - n)

from osgeo import gdal
from osgeo.gdalconst import GA_ReadOnly
import numpy as np
from sanic import Blueprint
from sanic.response import json
from datetime import datetime, timedelta
from tools.pqdict import pqdict
import config
from multiprocessing.managers import BaseManager
from ego import privileges


blu = Blueprint('spy', url_prefix='/v0.2/!')
zoom = 2
key = lambda _lat, _lng: '{},{}'.format("%.{}f".format(zoom) % _lat, "%.{}f".format(zoom) % _lng)


class Spy:
    def __init__(self):
        self.q = pqdict(key=lambda x: x[1])

    def h(self, lat, lng):
        lat = 2 * int(lat) + 1 - lat - .00000001
        f_lat, f_lng = lat % 2 ** -zoom, lng % 2 ** -zoom
        lat -= f_lat - .000000001
        lng -= f_lng - .000000001
        _key = key(lat, lng)
        if _key not in self.q:
            self.q[_key] = np.load('static/tiles/{}.npy'.format(_key)), datetime.now()
            if len(self.q) > 128:
                self.q.pop()

        return self.q[_key][0][int(f_lat * 3600), int(f_lng * 3600)]

    def deviation(self, locations):
        n = 0
        s = 0
        for location in locations:
            s += (self.h(*location['location']) - location['altitude']) ** 2
            n += 1
        return 0 if n == 0 else (s / n) ** .5


BaseManager.register('Spy', Spy)
manager = BaseManager()
manager.start()
spy = manager.Spy()


@blu.route('/@<lat>,<lng>')
async def height(request, lat, lng):
    return json({'altitude': int(spy.h(float(lat), float(lng)))})


@blu.route('/<hang>/<user>/@fake=<back_head:int>:<back_tail:int>', methods=['POST'])
@blu.route('/<hang>/<user>/@fake=<back_head:int>', methods=['POST'])
@privileges({'a', 'b', 'o'})
async def explore_fake(request, payload, user, hang, back_head, back_tail=0):
    now = datetime.now()
    back_head = now - timedelta(hours=back_head)
    back_tail = now - timedelta(hours=back_tail)
    locations = await config.locations.find({
        'hang': hang,
        'user': user,
        '_date': {
            '$lte': back_head,
            '$gt': back_tail
        },
        'altitude': {'$exists': True}
    }).to_list(None)

    locations = [(*location['location'], location['altitude']) for location in locations]

    return json({'deviation': spy.deviation(locations)})


@blu.route('/<hang>/<user>/@lazy=<back_head:int>:<back_tail:int>', methods=['POST'])
@blu.route('/<hang>/<user>/@lazy=<back_head:int>', methods=['POST'])
@privileges({'a', 'b', 'o'})
async def explore_lazy(request, payload, user, hang, back_head, back_tail=0):
    now = datetime.now()
    back_head = now - timedelta(hours=back_head)
    back_tail = now - timedelta(hours=back_tail)
    """
        choose one path -> simulate it -> compare real and virtual duration -> check if she is lazy
    """
    return json({'deviation': 101})


def _2csv(file, z=0):
    """
    url: http://dwtkns.com/srtm30m/
    :param file:
    :param z:
    :return:
    """
    def _zoom(arr, zz, _lat, _lng):
        if z == zz:
            return np.save(directory + '/{}.npy'.format(key(_lat, _lng)), arr)
        arr = np.split(arr, 2, axis=0)
        arr = [*np.split(arr[0], 2, axis=1), *np.split(arr[1], 2, axis=1)]
        zz += 1
        for i, a in enumerate(arr):
            _zoom(a, zz, _lat + int(i / 2) * 2 ** -zz, _lng + (i % 2) * 2 ** -zz)
    lat, lng = file.split('E')
    lat, lng = int(lat[1:]), int(lng)
    directory = 'static/tiles/'
    raster = gdal.Open(directory + file + '.hgt', GA_ReadOnly)
    heights = raster.GetRasterBand(1).ReadAsArray()[:-1, :-1]
    _zoom(heights, 0, lat, lng)


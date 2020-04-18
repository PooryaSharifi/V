import subprocess
import os
from multiprocessing import Process
import math
from osmread import parse_file, Way, Node, Relation
import time
import pickle
from static import osm_dir as _dir
from tools.weather import weather
from tools.mercator import colors
from tools import parse_location
from sanic import Blueprint
from sanic.response import json
import asyncio
from tools.mercator import async_session, big_picture
from bson import ObjectId
import numpy as np
import config
import aiohttp


blu = Blueprint(__name__, url_prefix='/v0.2/maps')


@blu.route('/weathers/<area>')
async def __weather__(_, area):
    _weather = await weather(area)
    _weather['_date'] = str(_weather['_date'])
    _weather['date'] = str(_weather['date'])
    _weather['sun']['rise'] = str(_weather['sun']['rise'])
    _weather['sun']['set'] = str(_weather['sun']['set'])
    return json(_weather)


@blu.route('/pictures/@<location>z/@padding=<padding>')
async def ll_picture(_, location, padding):
    area = str(ObjectId())
    padding = int(padding)
    lat, lng, zoom = parse_location(location)
    # now = datetime.now()

    async def _area_picture():
        sessions = [async_session() for _ in range(32)]
        picture = await big_picture('_', sessions, place={
            'padding': padding,
            'zoom': zoom,
            'location': [lat, lng]
        })
        # picture.save(_dir + '{}_{}-{}-{}_{}:00.png'.format(area, now.year, now.month, now.day, now.hour))
        picture.save(_dir + '{}.png'.format(area))
        for session, conn in sessions:
            await conn.close()
            await session.__aexit__(None, None, None)
    asyncio.ensure_future(_area_picture())
    return json({'SUCCESS': True, 'M': 'task added to loop', 'area': area})


@blu.route('/pictures/<area>')
async def area_picture(_, area):
    # now = datetime.now()

    async def _area_picture():
        sessions = [async_session() for _ in range(32)]
        picture = await big_picture(area, sessions)
        # picture.save(_dir + '{}_{}-{}-{}_{}:00.png'.format(area, now.year, now.month, now.day, now.hour))
        picture.save(_dir + '{}.png'.format(area))
        for session, conn in sessions:
            await conn.close()
            await session.__aexit__(None, None, None)
    asyncio.ensure_future(_area_picture())
    return json({'SUCCESS': True, 'M': 'task added to loop'})


default = {
    'motorway': 90,
    'motorway_link': 45,
    'trunk': 85,
    'trunk_link': 40,
    'primary': 65,
    'primary_link': 30,
    'secondary': 55,
    'secondary_link': 25,
    'tertiary': 40,
    'tertiary_link': 20,
    'unclassified': 25,
    'residential': 25,
    'living_street': 10,
    'service': 15,

    'path': 30,
    'footway': 40,
    'pedestrian': 25,
    'road': 30,
    'track': 40,
    'construction': 55,
    'steps': 40,
    'bridleway': 20,
    'bus_guideway': 30,
    'cycleway': 50,
    'bus_stop': 30,
    'services': 40,
    'rest_area': 30,
    'raceway': 70,
    'emergency_access_point': 90,
    'platform': 30,
}


def server(name, port, csv=None):
    if not csv:
        csv = name

    def shell():
        subprocess.call(['/usr/local/bin/osrm-customize --segment-speed-file ./{}.csv ./{}.osrm'.format(csv, name)], shell=True, cwd=_dir)
        subprocess.call(['/usr/local/bin/osrm-routed --port={} --algorithm=MLD ./{}.osrm'.format(port, name)], shell=True, cwd=_dir)
    p = Process(target=shell, kwargs={})
    p.start()
    return p


def _ways(name):
    try:
        with open(_dir + name + '.pkl', 'rb') as f:
            return pickle.load(f)
    except FileNotFoundError as e:
        __ways = {}
        for entity in parse_file(_dir + name + '.osm'):
            if isinstance(entity, Node):
                __ways[entity.id] = (entity.lat, entity.lon)
            if isinstance(entity, Way) and 'highway' in entity.tags:
                highway = entity.tags['highway']
                speed = int(entity.tags['maxspeed']) if 'maxspeed' in entity.tags else default.get(highway, 20)
                nodes = entity.nodes
                nodes = [nodes[i * 5:min(i * 5 + 5, len(nodes))] for i in range(math.ceil(len(nodes) / 5))]
                if len(nodes[-1]) == 1:
                    nodes[-2] = list(nodes[-2])
                    nodes[-2].append(nodes[-1][0])
                    nodes = nodes[:-1]
                for points in nodes:
                    __ways[(points[0], points[-1])] = {
                        'highway': highway,
                        'speed': [speed, speed],
                        'nodes': points
                    }
                    if 'oneway' not in entity.tags or entity.tags['oneway'] == 'no':
                        __ways[(points[-1], points[0])] = {
                            'highway': highway,
                            'speed': [speed, speed],
                            'nodes': tuple(reversed(points))
                        }
        with open(_dir + name + '.pkl', 'wb') as f:
            pickle.dump(__ways, f, pickle.HIGHEST_PROTOCOL)
    return __ways


async def traffics(ways, name):
    import tensorflow as tf
    perceptron = tf.keras.Sequential([
        tf.keras.layers.Dense(5, input_shape=(7,), activation='sigmoid', kernel_initializer='random_uniform'),
        tf.keras.layers.Dense(1, activation='softmax', kernel_initializer='random_uniform')
    ])
    perceptron.compile(optimizer='adam', loss='mse', metrics=['accuracy'])

    w = await weather(name)
    x = []
    with open(_dir + name + '.csv', 'wb') as traffics:
        for key, segment in ways.items():
            if isinstance(key, tuple):
                x.append([0, 0, 0, 0, segment['speed'][-1], (w['temperature'] + 40) / 100, 0])
                x[-1][segment['color']] = 1

        y = perceptron.predict(np.array(x))
        y *= 100
        i = 0
        for key, segment in ways.items():
            if isinstance(key, tuple):
                segment['speed'].append(int(y[i][0]))
                i += 1
                pairs = ((node, segment['nodes'][i + 1], segment['speed'][-1]) for i, node in enumerate(segment['nodes'][:-1]))
                for p in pairs:
                    traffics.write('{},{},{}\n'.format(*p).encode())


def main():
    _0 = None
    while True:
        if _0:
            time.sleep(30)
        traffics('tehran')
        _1 = server('tehran', 5002)
        time.sleep(2)
        if _0:
            os.kill(_0.pid, 9)
        time.sleep(30)
        traffics('tehran')
        _0 = server('tehran', 5001)
        time.sleep(2)
        os.kill(_1.pid, 9)


# from keras.models import Sequential
# from keras.layers import LSTM, ConvLSTM2D, Dense, Conv2D, Conv1D, TimeDistributed
# from keras import optimizers
# import numpy as np
# from PIL import Image
# tree, green_threshold, yellow_threshold = _kd
# # print(tree.data)
# image = np.zeros((8960, 8960, 3))
# for i, index in enumerate(tree.data):
#     if i < green_threshold:
#         image[int(index[0]), int(index[1])] = [50, 255, 20]
#     elif green_threshold < i < yellow_threshold:
#         image[int(index[0]), int(index[1])] = [200, 205, 20]
#     else:
#         image[int(index[0]), int(index[1])] = [255, 50, 20]
# image = Image.fromarray(np.uint8(image))
# image.save('colors.png')

if __name__ == '__main__':
    ways = _ways('tehran')
    # with open(_dir + 'tehran.colors' + '.pkl', 'rb') as f:
    #     _kd = pickle.load(f)
    #
    # ways = colors(ways, 'tehran', _kd=_kd)
    # with open(_dir + 'tehran' + '.pkl', 'wb') as f:
    #     pickle.dump(ways, f, pickle.HIGHEST_PROTOCOL)
    config.session = asyncio.get_event_loop().run_until_complete(aiohttp.ClientSession().__aenter__())
    asyncio.get_event_loop().run_until_complete(traffics(ways, 'tehran'))

from sanic import Blueprint
from sanic.response import text, json
from sanic.exceptions import abort
import ujson
from tools import parse_location, parse_path, awake
from datetime import datetime
from ego import privileges
from geopy.distance import vincenty
import config
from tools import points
import ujson
import numpy as np
from bson import ObjectId
from static import osrm_host
from tools.mu import manager as mu
from aiofile import AIOFile, Writer
import asyncio
import os
import socket

c = .01

# from oracle import observe
blu = Blueprint('motion', url_prefix='/v0.2')


@blu.route('/~<path>/@', methods=['GET'])
@blu.route('/<hang>/~<path>/@', methods=['GET'])
@privileges({'a', 'b', 'o', 'p', 'u'})
async def path_location(request, payload, path, hang=None):
    location = await config.locations.find({
        'hang': hang,
        'points._id': ObjectId(path)
    }).sort([('_date', -1)]).to_list(1)
    if location:
        location = location[0]
        if 'points' in location:
            for i, p_id in enumerate(location['points']):
                location['points'][i]['_id'] = str(p_id['_id'])
        del location['_id']
    else:
        location = None
    return json(location, 200)


@blu.route("/<hang>/<user>/@", methods=['GET'])
@privileges({'a', 'b', 'o', 'p'})
async def user_location(request, payload, hang, user):
    location = await config.locations.find({'hang': hang, 'porter': user}).sort([('_date', -1)]).to_list(1)
    if location:
        location = location[0]
        if 'points' in location:
            for i, p_id in enumerate(location['points']):
                location['points'][i]['_id'] = str(p_id['_id'])
        del location['_id']
    else:
        location = {}
    return json(location, 200)


async def __location__(request, _id, location):
    location = parse_location(location)
    now = datetime.now()
    _response = None
    if _id in porters and 'aim' in porters[_id]:
        d = vincenty(location, porters[_id]['aim']['location']).m
        if d < 450:
            await paths.update_one({'_id': porters[_id]['aim']['_id']}, {
                '$set': {'done': now}
            })
            del porters[_id]['aim']
            _response = "{}'v been observed at lat: {}," \
                        " lng: {} also it's path with id: {} finished".format(_id, *location, porters[_id]['aim']['_id'])
    if not _response:
        _response = "{}'v been observed at lat: {}, lng: {} ".format(_id, *location)
    if _id in porters and 'observe' in porters[_id]:
        d = vincenty(location, porters[_id]['observe']['location']).m
        location_json = {
            'porter': _id,
            'location': location,
            '_date': now,
            'vector': [location[0] - porters[_id]['observe']['location'][0],
                       location[1] - porters[_id]['observe']['location'][1]],
            'velocity': d / (now - porters[_id]['observe']['_date']).total_seconds()
        }
        locations_buffer.append(location_json)
        if len(locations_buffer) > 15:
            await locations.insert_many(locations_buffer)
            locations_buffer.clear()

    if _id not in porters:
        porters[_id] = {
            'observe': {
                'location': location, '_date': now
            }
        }
    else:
        porters[_id]['observe']['location'] = location
        porters[_id]['observe']['_date'] = now
    return text(_response)


async def __location(hang, user, _location_, points, fcm, capacity=None):
    now = datetime.now()
    # awake(config.listeners, hang, 'locations/%s/@%f,%f,%0.0ft' % (user, *_location_[:2], now.timestamp()))
    previous = mu.reverse(user, hang)
    # mu.observe(
    #     {
    #         'type': 2,
    #         '_id': user,
    #         'hang': hang,
    #         'location': _location_[:2],
    #         'value': 1,
    #         '_date': now
    #     })
    mu.observe(1, user, hang, location=_location_[:2], date=now, capacity=capacity, fcm=fcm)
    velocity = None
    if previous:
        lat, lng = previous['location']
        ts = (now - previous['_date']).total_seconds()
        if ts < 100 and ts != 0:
            d = vincenty(_location_, (lat, lng)).m
            d /= ts
            if d > 2:
                velocity = [d, _location_[0] - lat, _location_[1] - lng]

    # print('---', user)
    location = {
        '_date': now,
        'porter': user,
        'hang': hang,
        'location': _location_[:2],
    }
    if len(_location_) > 2:
        location['altitude'] = _location_[2],
    if velocity:
        location['velocity'] = velocity
    if points:
        location['points'] = [{'_id': ObjectId(_id)} for _id in set(points)]
    if fcm:
        location['fcm'] = fcm
    if capacity:
        location['capacity'] = capacity

    insert = await config.locations.insert_one(location)
    awake(config.listeners, hang, 'location,%s,%f,%f,%0.0f' % (user, *_location_[:2], now.timestamp()))
    return {"inserted_id": str(insert.inserted_id)}


@blu.websocket('/<hang>/<user>/@@')
@privileges({'a', 'b', 'o', 'p'})
async def _location_loop(request, payload, ws, hang, user):
    while True:
        data = await ws.recv()
        data = ujson.loads(data)
        location = data['location']
        points = data['points']
        fcm = data['fcm'] if 'fcm' in data else None
        await ws.send(ujson.dumps(await __location(hang, user, location, points, fcm, capacity=int(request.form['capacity'][0]) if 'capacity' in request.form else None)))


@blu.route("/<hang>/<user>/@<location>", methods=['GET', 'POST', 'PUT'])
@blu.route("/<hang>/<user>/@<location>/~<points>", methods=['GET', 'POST', 'PUT'])
@privileges({'a', 'b', 'o', 'p'})
async def _location(request, payload, hang, user, location, points=''):
    if location == '_,_':
        location = [float(request.form['lat'][0]), float(request.form['lng'][0])]
    else:
        location = parse_location(location)
    return json(await __location(hang, user, location, points.split(';') if points else [], request.form['fcm'][0] if 'fcm' in request.form else None, capacity=int(request.form['capacity'][0]) if 'capacity' in request.form else None))


async def sum_star(porters, transmitter, receiver):
    porters.append(transmitter)
    porters.append(receiver)
    async with config.session.get(osrm_host + '/table/v1/driving/' + points(porters), params={
        'sources': ';'.join([str(i) for i in range(len(porters) - 1)]),
        'destinations': ';'.join([str(i) for i in range(len(porters) - 2, len(porters))])
    }) as response:
        m = np.array(ujson.loads(await response.text())['durations'])
        return sum(m[:-1, 0]) / (m.shape[0] - 1) + m[-1, 1]


@blu.route('/<hang>/~<path>/*')
async def _sum_star(request, porters, transmitter, receiver):
    return text(await sum_star())


@blu.route('/<hang>/~<path>/$')
async def cost(request, path, hang, porters=None, entropy=True, priority=0):
    if not porters:
        from oracle.oracle import hangs
        porters = hangs[hang][2].knn(path[0])
        print(porters)
        # reassign porters to have [ point ]
    s = await _sum_star(porters, *porters) + priority * 100
    # += entropy() -> *= k
    if entropy:
        from oracle.oracle import hangs
        s += (hangs[hang][2](path[0]) - hangs[hang](path[1])) * c
    # get K from flash
    return text(s * config.flash.get_khang(hang.encode()))

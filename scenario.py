import asyncio
from uuid import uuid4
from sanic import Blueprint
from sanic.response import text, json
import ujson
from ego import privileges, ban
from motion import sum_star
from datetime import datetime, timedelta
import config
from config import wrk
from tools import parse_location, parse_path, JSONEncoder, pathify, awake
from tools.ql import hot_query, frees, expected_frees
from bson import ObjectId
import ujson
import solver
from pymongo import ReturnDocument
# from eta import predict, reform, eta
from aiofcm import Message, PRIORITY_HIGH
from tools.voronoi import territory, _extra_base
from math import log2, ceil
from solver import p2f, screaming_durations, nearest_neighbor
from static import osrm_host
from tools.mu import manager as mu

blu = Blueprint('scenario', url_prefix='/v0.2')


# @blu.route('/~<path>/@priority=<priority>', methods=['POST'])
@blu.route('/<hang>/~<path>/@priority=<priority>', methods=['POST'])
@privileges({'a', 'b', 'o'})
async def set_priority(request, payload, hang, path, volume=0, priority=0):
    print(path)
    pass


# @blu.route('/~<path>/@delay=<delay>', methods=['POST'])
@blu.route('/<hang>/~<path>/@delay=<delay>', methods=['POST'])
@privileges({'a', 'b', 'o'})
async def alter_delay(request, payload, path):
    pass


@blu.route('/<hang>/~<path>/@sell=<price>', methods=['POST'])
@privileges({'a', 'b', 'o', 'p'})
async def sell(request, payload, hang, path, price):
    try:
        location = (await config.locations.find({'hang': hang, 'porter': payload[1]}).sort([('_date', -1)]).to_list(1))[0]
    except:
        print(payload[1])
        raise
    path = path.split(';')  # bunch of ids
    now = datetime.now()
    if len(path) <= 2:
        returned_id = path[0]
        path = await config.paths.find_one_and_update({
            'points._id': ObjectId(returned_id),
            'hang': hang,
            'porters.ack': {'$exists': False}
        }, {
            '$push': {
                'porters': {
                    'porter': payload[1],
                    '_date': now,
                    'ack': True,
                    'location': location['location'],
                    'price': float(price)
                },
            },
            **({'$set': {
                'points.1.location.0': float(request.form['latitude'][0]),
                'points.1.location.1': float(request.form['longitude'][0])
            }} if 'latitude' in request.form and 'longitude' in request.form else {})
        }, return_document=ReturnDocument.AFTER)
        if not path:
            return json({"SUCCESS": False})
    else:
        paths = await config.paths.find({
            'points._id': {'$in': [ObjectId(point) for point in path]},  # fixme maybe it check them two
            'hang': hang,
            'porters.ack': {'$exists': False}
        }).to_list(None)
        if len(paths) != len(set(path)):
            return json({"SUCCESS": False})
        # for now let's just say an order just participate into one of batched or normal paths
        # so if we try to delete they are all existed or all gone so we can find it
        result = await config.paths.delete_many({
            '_id': {'$in': [p['_id'] for p in paths]},
        })
        if result.deleted_count == 0:
            return json({"SUCCESS": False})
        paths = {str(p['_id']): p for p in paths}
        flags = set()
        ids = []
        for p in path:
            if p in flags:
                ids.append('$' + p)
            else:
                ids.append(p)
            flags.add(p)
        path = {
            '_id': ObjectId(),  # paths[path[0]]['_id'],
            'hang': hang,
            'points': [paths[_id[1:]]['points'][0] if '$' in _id else paths[_id]['points'][1] for _id in reversed(ids)],
            'porters': [{
                'porter': payload[1],
                '_date': now,
                'ack': True,
                'location': location['location'],
                'price': float(price)
            }]
        }
        if 'latitude' in request.form and 'longitude' in request.form:
            path['points'][-1]['location'] = [float(request.form['latitude'][0]), float(request.form['longitude'][0])]
        returned_id = str((await config.paths.insert_one(path)).inserted_id)
    ps = {}
    if path:
        points = path['points']
        config.locations.update_one({'_id': location['_id']}, {
            '$set': {'points': [{'_id': _id} for _id in set(p['_id'] for p in points)]}
        })
        previous = mu.reverse(payload[1], hang)
        previous['points'] = []
        for i, p in enumerate(reversed(points)):
            _id = str(p['_id'])
            if '_date' in p:
                delay = (now - p['_date']).total_seconds()
                ps[_id] = delay
                # mu.observe({
                #     'type': 0,
                #     '_id': _id,
                #     'hang': hang,
                #     'location': p['location'],
                #     'value': delay,
                #     '_date': now
                # })
                mu.observe(delay, _id, hang, location=p['location'], date=now, type=0)
                # pfs[i].date = p['_date'].timestamp()
                previous['points'].append({'_id': p['_id']})
            else:
                # mu.observe({
                #     'type': 1,
                #     '_id': _id,
                #     'hang': hang,
                #     'location': p['location'],
                #     'value': ps[_id],
                #     '_date': now
                # })
                mu.observe(ps[_id], _id, hang, location=p['location'], date=now, type=1)

        previous['hang'] = hang
        previous['porter'] = payload[1]
        await config.locations.insert_one(previous)
        path_packet = [str(points[-1]['_id'])]
        if len(points) == 4:
            path_packet.append(str(points[-2]['_id']))
            path_packet.append('z' if points[0]['_id'] == points[-1]['_id'] else 'x')
        awake(config.listeners, hang, 'sell,%s,%s' % (payload[1], ','.join(path_packet)))
        print('sell,%s,%s' % (payload[1], ','.join(path_packet)))
    return json({"SUCCESS": True, '_id': returned_id})


# @blu.route('/~<path>/@nack', methods=['POST'])
@blu.route('/<hang>/~<path>/@nack', methods=['POST'])
@privileges({'a', 'b', 'o', 'p'})
async def reject(request, payload, path, hang):
    # unwrap all to atomic paths ->
    pass


# @blu.route('/~<path>/@at', methods=['POST'])
@blu.route('/<hang>/~<_id>/@at', methods=['POST'])
@privileges({'a', 'b', 'o', 'p'})
async def at(request, payload, _id, hang):
    _id = ObjectId(_id)
    now = datetime.now()
    path = await config.paths.find_one_and_update({
        'points': {
            '$elemMatch': {
                '_id': _id,
                'volume': {'$exists': True}
            }
        }
    }, {
        '$set': {
            'points.$.at': now
        }
    }, new=True, upsert=True)
    if path:
        for p in path['points']:
            if p['_id'] == _id and '_date' in p:
                if 'territory' in p:
                    location = mu.reverse(str(p['territory']), hang)  # just for test and show  ...str(p['terri -> p['terri because territory is user
                    if location and 'fcm' in location:
                        asyncio.ensure_future(promise([config.fcm.send_message(Message(
                            device_token=location['fcm'],
                            notification={  # optional
                                "title": "OFFER",
                                "body": "new offers received",
                                # "sound": "default",
                                "sound": "refah"
                            },
                            data={"porter": payload[1], 'path': str(_id), '_id': str(path['_id'])},  # optional
                            message_id=str(uuid4()),  # optional
                            time_to_live=3,  # optional
                            priority=PRIORITY_HIGH,  # optional
                        ))]))
                upper_bound = None
                duration = None
                if 'eta' in p:
                    upper_bound = p['_date'] + timedelta(seconds=p['eta']['eta'])
                    duration = timedelta(seconds=p['eta']['duration'])
                if 'tail' in p:
                    upper_bound = p['tail']
                    # duration = await duration()
                    duration = timedelta(seconds=0)
                if not upper_bound:
                    break
                # fastness
                if upper_bound - timedelta(minutes=10) > now + duration:
                    # TODO add listeners
                    print('at late')
                    # e.g. send discount code via sms
                    pass
    awake(config.listeners, hang, 'at,%s' % str(_id))
    return json({'SUCCESS': True})


# @blu.route('/~<path>/@done', methods=['POST'])
@blu.route('/<hang>/~<path>/@done', methods=['POST'])
@privileges({'a', 'b', 'o', 'p'})
async def done(request, payload, path, hang):
    path = ObjectId(path)
    now = datetime.now()
    """
    if it is in batch mode if it is the last point then we remove it from flash and
    """
    document = await config.paths.find_one_and_update({
        'points': {
            '$elemMatch': {
                '_id': path,
                'volume': {'$exists': False}
            }
        }
    }, {
        '$set': {
            'points.$.at': now
        },
        '$inc': {
            'points.$.bound': -now.timestamp()
        }
    }, new=True, upsert=True)
    if not document:  # result.modified_count == 0:
        raise Exception
    for p in document['points']:
        if 'territory' in p and p['territory'] == 0:
            await config.paths.update_one({'hang': hang, 'lock': p['_id']}, {'$unset': {'lock': 1}})
    await config.users.update_one({'user': hang, 'hang': hang}, {'$inc': {'credit': -1}})
    user = (await config.users.aggregate([
        {'$match': {'user': payload[1], 'hang': hang}},
        {
            '$graphLookup': {
                'from': "users",
                'startWith': "$parent",
                'connectFromField': "parent",
                'connectToField': "user",
                'as': "hierarchy",
                'restrictSearchWithMatch': {'hang': hang}
            }
        }
    ]).to_list(None))[0]
    ancestors = [parent['_id'] for parent in user['hierarchy']]
    ancestors.append(user['_id'])
    price = [porter['price'] for porter in document['porters'] if 'price' in porter and porter['ack']][0]
    await config.users.update_many({
        '_id': {'$in': ancestors}
    }, {

        '$inc': {'cash': price / len(ancestors)}
    })
    previous = mu.reverse(payload[1], hang)
    previous['hang'] = hang
    previous['porter'] = payload[1]
    await config.locations.insert_one(previous)
    for p in document['points']:
        if p['_id'] == path and 'bound' in p:
            if p['bound'] < 0:
                # TODO add listeners
                # print('done late')
                # e.g. send discount code via sms
                pass
    awake(config.listeners, hang, 'done,%s' % str(path))
    print('done', document['porters'][0]['porter'], str(path))
    return json({'SUCCESS': True})


@blu.route('/<hang>/~_,_;<location>', methods=['POST', 'PUT'])
@privileges({'a', 'b', 'o', 'u'})
async def _auto_path(request, payload, hang, location):
    t_lat, t_lng = parse_location(location)
    now = datetime.now()
    fastness = int(request.form['fastness'][0]) if 'fastness' in request.form else 1
    base_bound = int(request.form['baseBound'][0] if 'baseBound' in request.form else '0')
    base_bound /= fastness
    (s_lat, s_lng), _territory = territory(t_lat, t_lng)
    _id = ObjectId()
    volume = int(request.form['volume'][0])
    paths = [{
        '_id': _id,
        'hang': hang,
        'points': [  # TWISTED
            {
                '_id': _id,
                'location': [t_lat, t_lng],
                '_author': payload[1],
                'head': now + timedelta(seconds=int(request.form['head'][0])),
                'tail': now + timedelta(seconds=int(request.form['tail'][0])),
                'bound': (now + timedelta(seconds=int(request.form['tail'][0]))).timestamp() + base_bound,
            }, {
                **({'id': request.form['id'][0]} if 'id' in request.form else {}),
                '_id': _id,
                '_date': now,
                '_author': payload[1],
                'volume': volume,
                'territory': int(_territory),
                'location': [s_lat, s_lng],
            }
        ],
        'porters': [],
        'offer': 0,
    }]
    extra = int(request.form['extra'][0]) if 'extra' in request.form else 0
    if extra:
        _id = ObjectId()
        table = await config.session.post(
            osrm_host + '/table/v1/driving/' + '{s_lng},{s_lat};{t_lng},{t_lat}?sources=0&destinations=1'.format(
                s_lat=s_lat, s_lng=s_lng, t_lat=t_lat, t_lng=t_lng))
        paths.append({
            '_id': _id,
            'hang': hang,
            'points': [  # TWISTED
                {
                    '_id': _id,
                    'location': [s_lat, s_lng],
                    '_author': payload[1],
                    'head': now,
                    'tail': now + timedelta(
                        seconds=int(request.form['head'][0]) - (await table.json())['durations'][0][0] / fastness),
                    'bound': (now + timedelta(
                        seconds=int(request.form['head'][0]) - (await table.json())['durations'][0][0] / fastness)).timestamp() + base_bound,
                }, {
                    **({'id': request.form['id'][0]} if 'id' in request.form else {}),
                    '_id': _id,
                    '_date': now,
                    '_author': payload[1],
                    'volume': extra,
                    'territory': 0,
                    'location': [_extra_base[0], _extra_base[1]],
                }
            ],
            'porters': [],
            'offer': 0,
        })
        paths[0]['lock'] = _id
    if volume == extra:
        paths[1]['points'][0]['head'] = paths[0]['points'][0]['head']
        paths[1]['points'][0]['tail'] = paths[0]['points'][0]['tail']
        paths[1]['points'][0]['location'] = [t_lat, t_lng]
        paths = paths[1:]
    # print([(path['points'][-1]['territory'], path['points'][-1]['volume']) for path in paths])
    result = await config.paths.insert_many(paths)
    return json({'SUCCESS': True, '_ids': [str(_id) for _id in result.inserted_ids]}, 201)


@blu.route('/<hang>/<_id>/~<path>', methods=['POST', 'PUT'])
@blu.route('/<hang>/~<path>', methods=['POST', 'PUT'])
@privileges({'a', 'b', 'o', 'u'})
async def push_path(request, payload, hang, path, _id=None):
    s_lat, s_lng, t_lat, t_lng = parse_path(path)
    _id = ObjectId() if not _id else ObjectId(_id)
    now = datetime.now()
    fastness = int(request.form['fastness'][0]) if 'fastness' in request.form else 1
    base_bound = int(request.form['baseBound'][0] if 'baseBound' in request.form else '0')
    base_bound /= fastness
    priority = int(request.form['priority'][0]) if 'priority' in request.form else 1
    volume = int(request.form['volume'][0]) if 'volume' in request.form else 0
    path = {
        '_id': _id,
        # '_date': now,
        'hang': hang,
        'points': [  # TWISTED
            {
                '_id': _id,
                # 'window': [],
                'location': [t_lat, t_lng],
                '_author': payload[1],
                # 'at': datetime.now(),
                **({
                       'head': now + timedelta(seconds=int(request.form['head'][0])),
                       'tail': now + timedelta(seconds=int(request.form['tail'][0])),
                       'bound': (now + timedelta(seconds=int(request.form['tail'][0]))).timestamp() + base_bound
                   } if 'head' in request.form and 'tail' in request.form else {})
            }, {
                **({'id': request.form['id'][0]} if 'id' in request.form else {}),
                '_id': _id,
                '_date': now,
                '_author': payload[1],
                'volume': volume,
                'head': now + timedelta(seconds=int(request.form['delay'][0]) if 'delay' in request.form else 0),
                'tail': 0,
                'location': [s_lat, s_lng],
                'priority': priority,
                # 'at': datetime.now()
                **({'territory': int(request.form['territory'][0])} if 'territory' in request.form else {})
            }
        ],
        'porters': [
            # {            #     '_id': '',
            #     '_date': datetime.now(),
            #     'ack': None
            # }
        ]
    }
    if 'offer' in request.form:
        path['offer'] = float(request.form['offer'][0])
    if 'eta' in request.form:
        path['points'][-1]['eta'] = ujson.loads(request.form['eta'][0])
    elif 'head' not in path['points'][0] and 'tail' not in path['points'][0]:
        # data = await eta(s_lat, s_lng, t_lat, t_lng, float(request.form['wait'][0]) if 'wait' in request.form else 0)
        data = {'eta': {'eta': 0, 'duration': 0}}
        if data:
            path['points'][-1]['eta'] = data['eta']

    if 'bound' not in path['points'][0]:
        path['points'][0]['bound'] = now.timestamp() + path['points'][-1]['eta']['eta']

    result = await config.paths.insert_one(path)
    awake(config.listeners, hang, 'insert,%s,%f,%f,%f,%f,%0.0f' % (str(_id), s_lat, s_lng, t_lat, t_lng, now.timestamp()))
    return json({'SUCCESS': True, '_id': str(result.inserted_id)}, 201)


@blu.route('/<hang>/~<path>', methods=['GET'])
@privileges({'a', 'b', 'o', 'u'})
async def _eta(request, payload, hang, path):
    wait = float(request.args['wait'][0]) if 'wait' in request.args else 0
    s_lat, s_lng, t_lat, t_lng = parse_path(path)
    porters, muses, density = await config.mu.x(hang, [s_lat, s_lng], True)
    points = '{};{},{};{},{}'.format(
        ';'.join(['{},{}'.format(location[1], location[0]) for location in porters]),
        s_lng, s_lat, t_lng, t_lat,
    )
    async with config.session.get(osrm_host + '/table/v1/driving/' + points, params={
        'sources': ';'.join([str(i) for i in range(len(porters) + 1)]),
        'destinations': str(len(porters)) + ';' + str(len(porters) + 1)
    }) as response:
        m = ujson.loads(await response.text())['durations']
        for i, location in enumerate(porters):
            porters[i] = m[i][0] + m[-1][1]
        offer = sum(porters) / len(porters)
        data = {
            'eta': {
                'knn_porters_duration': porters,
                'p_mu': muses[2],
                's_mu': muses[0],
                't_mu': muses[1],
                'time_mu': density,
                # 'eta': max(predict(reform([0] * (7 - len(porters)) + porters, m[0][1], porters), m[0][1]), wait) + m[-1][1],
                'duration': m[-1][1]
            },
            'offer': offer
        }
    return json(data)


async def prepare(matches, twist=True):
    for porter, paths in matches:
        location = porter['location']
        for path in paths:
            cash = 0
            path['_id'] = str(path['_id'])
            if 'lock' in path:
                path['lock'] = str(path['lock'])
            if twist:
                path['points'] = list(reversed(path['points']))
            for i, p in enumerate(path['points']):
                if i & 1 == 0:
                    if i == 0:
                        cash += await sum_star([location], path['points'][i]['location'],
                                               path['points'][i + 1]['location'])
                    else:
                        cash += await sum_star([path['points'][i - 1]['location']], path['points'][i]['location'],
                                               path['points'][i + 1]['location'])
                p['_id'] = str(p['_id'])
                if 'head' in p:
                    p['head'] = str(p['head'])
                    p['tail'] = str(p['tail'])
                if '_date' in p:
                    p['_date'] = str(p['_date'])

            if 'offer' not in path:
                path['offer'] = cash
    return matches


@blu.route('/<hang>/!!!/NN', methods=['POST'])
async def __notify(request, hang):
    matches = request.body.decode()
    matches = matches.split(';') if matches else []
    matches = [match.split(',') for match in matches]
    free_porters = await config.locations.find({'porter': {'$in': [match[0] for match in matches]}}).to_list(None)
    free_porters = {porter['porter']: porter for porter in free_porters}
    paths = [match[1] for match in matches]
    paths.extend([match[2] for match in matches if len(match) > 2])
    paths = await config.paths.find({'points._id': {'$in': [ObjectId(path) for path in paths]}}).to_list(None)
    _paths = {}
    for path in paths:
        for point in path['points']:
            _paths[str(point['_id'])] = path
    paths = _paths
    _matches = []
    for i, match in enumerate(matches):
        path = paths[match[1]]
        if len(match) > 2:
            if not paths[match[2]]['porters'] and len(path['points']) == 2:
                points = paths[match[2]]['points']
                points.append(path['points'][-1])
                points.insert(0, path['points'][0])
                if match[3] == 'x':
                    points[0], points[1] = points[1], points[0]
                path['points'] = points
                _matches.append([free_porters[match[0]], [path]])
        else:
            if not path['porters']:
                _matches.append([free_porters[match[0]], [path]])
    await notify(request, hang, await prepare(_matches))
    return text("")


@blu.route('/<hang>/!!!/N', methods=['POST'])
@privileges({'a', 'b'})
async def _notify(request, payload, hang):
    matches = await prepare(ujson.loads(request.form['matches'][0]))
    await notify(request, hang, matches)
    return json({'SUCCESS': True})


@blu.route('/<hang>/!!!/T', methods=['POST'])
@privileges({'a', 'b'})
async def _telegram(request, payload, hang):
    from pytg.sender import Sender
    sender = Sender(host="localhost", port=4458)
    matches = await prepare(ujson.loads(request.form['matches'][0]))
    porters = [porter['porter'] for porter, paths in matches]
    porters = await config.users.find({'hang': hang, 'user': {'$in': porters}, 'phone': {'$exists': True}}).to_list(None)
    contacts = {porter['user']: porter['phone'] for porter in porters}
    bag = set()
    for porter, (path, ) in matches:
        phone = contacts[porter['porter']]
        if phone not in bag:
            bag.add(phone)
            name = sender.contact_add(phone, phone, "")[0]['print_name']
            for i, point in enumerate(path['points'][: int(len(path['points']) / 2)]):
                sender.send_msg(name, point['name'])
                sender.send_location(name, *path['points'][-i - 1]['location'])

    return json({'SUCCESS': True})


@blu.route('/<hang>/!!!/@fastness=<fastness>', methods=['POST'])
@blu.route('/<hang>/!!!/@fastness=<fastness>;@capacity=<capacity>', methods=['POST'])
@blu.route('/<hang>/!!!/@capacity=<capacity>;@fastness=<fastness>', methods=['POST'])
@privileges({'a', 'b', 'o', 'u'})
async def _evaluate(request, payload, hang, fastness='1', capacity='40'):
    fastness = int(fastness)
    capacity = int(capacity)
    total_volume = 0
    paths = pathify(request.form['paths'][0], twist=True)
    resp = {
        'volume': 0,
        'duration': 0,
        'duration_plus': 0,
        'distance': 0,
        'dissatisfaction': 0,
        'efficiency': 0,
    }
    for path in paths:
        volume = sum(p['volume'] for p in path['points'] if 'volume' in p)
        total_volume += volume
        resp['volume'] += max(volume - capacity, 0) * max(volume - capacity, 0)
    routes = [[path['porters'][0]['location']] for path in paths]
    for i, path in enumerate(paths):
        for point in path['points'][int(len(path['points']) / 2) - 1:]:
            routes[i].append(point['location'])

    service_time = 90 / fastness
    for i, route in enumerate(routes):
        async with config.session.get(osrm_host + '/route/v1/driving/' + ';'.join('%s,%s' % tuple(reversed(location)) for location in route)) as response:
            m = ujson.loads(await response.text())['routes'][0]['legs']
            resp['duration'] += sum(leg['duration'] for leg in m)
            resp['duration_plus'] += sum(leg['duration'] for leg in m) + (len(m) - 1) * service_time
            resp['distance'] += sum(leg['distance'] for leg in m)
            time = paths[i]['porters'][0]['_date'] + timedelta(seconds=m[0]['duration'])
            for j, leg in enumerate(m[1:]):
                time += timedelta(seconds=leg['duration'])
                point = paths[i]['points'][int(len(paths[i]['points']) / 2) + j]
                if time < point['head']:
                    resp['dissatisfaction'] += (point['head'] - time).seconds ** 2
                if point['tail'] < time:
                    resp['dissatisfaction'] += (time - point['tail']).seconds ** 2
                time += timedelta(seconds=service_time)
    resp['efficiency'] = (total_volume / (len(paths) * capacity)) if (len(paths) * capacity) != 0 else 0
    resp['efficiency'] *= 100
    return json(resp)


@blu.route('/<hang>/!!!/<algorithm>/<protocols>', methods=['POST', 'GET'])
@blu.route('/<hang>/!!!/<algorithm>', methods=['POST', 'GET'])
@blu.route('/<hang>/!!!/<algorithm>/<protocols>/@fastness=<fastness>', methods=['POST', 'GET'])
@blu.route('/<hang>/!!!/<algorithm>/@fastness=<fastness>', methods=['POST', 'GET'])
@privileges({'a', 'b'})
async def solve(request, payload, hang, algorithm, protocols='', fastness='1'):
    _frees = frees
    if '-expected' in protocols:
        _frees = expected_frees
    fastness = int(fastness)
    if algorithm != '_':
        _frees = await _frees(hang)
        # hot_paths = await config.paths.find(hot_query(hang, int(120 * 60 / fastness))).to_list(None)
        if 'paths' in request.form:
            hot_paths = pathify(request.form['paths'][0], twist=False)
        else:
            hot_paths = await config.paths.find(hot_query(hang, int(120 * 60 / fastness))).sort(
                [('points.0.head', 1)]).limit(int(len(_frees) * p2f[algorithm])).to_list(None)
        print('-- matching {} free porters with {} hot paths, using "{} {}" --'.format(len(_frees), len(hot_paths), algorithm, protocols))
        # import pickle
        # if len(hot_paths) >= 33:
        #     with open('solver/porters.pkl', 'wb') as handle:
        #         pickle.dump(_frees, handle, protocol=pickle.HIGHEST_PROTOCOL)
        #     with open('solver/paths.pkl', 'wb') as handle:
        #         pickle.dump(hot_paths, handle, protocol=pickle.HIGHEST_PROTOCOL)
        if len(_frees) == 0 or len(hot_paths) == 0:
            if '-N' in protocols:
                return json([])
            return json({'SUCCESS': True, 'huli': 'muli'})
        if '-boost' in protocols:
            # family boost
            pass
        now = datetime.now()
        paths_durations, porters_durations = None, None
        if '-filter' in protocols:
            paths_durations, porters_durations = await screaming_durations(hot_paths), \
                                                 await nearest_neighbor(_frees, hot_paths, availability=False)
            hot_paths = [path for idx, path in enumerate(hot_paths) if
                         now + timedelta(seconds=paths_durations[idx][0] + porters_durations[idx]) > path['points'][0]['head']]
        if '-extend' in protocols:
            if not paths_durations or not porters_durations:
                paths_durations, porters_durations = await screaming_durations(hot_paths), \
                                                     await nearest_neighbor(_frees, hot_paths, availability=False)
            for idx, path in enumerate(hot_paths):
                path['points'][0]['tail'] = max(path['points'][0]['tail'],
                                                now + timedelta(seconds=paths_durations[idx][0] + porters_durations[idx] * 1.2))

        matches = await getattr(solver, algorithm)(_frees, hot_paths, fastness=fastness, protocols=protocols)
        # if protocol:
        #     await globals()[protocol](matches)
        if '-N' in protocols:
            matches = await prepare(matches, twist=False)
            print([int(len(m[1][0]['points']) / 2) for m in matches])
            for porter, _ in matches:
                porter['_id'] = str(porter['_id'])
                porter['_date'] = str(porter['_date'])
            # matches[1] = [[list(reversed(str(p['_id']) for p in path['points'])) for path in paths] for paths in
            #               matches[1]]
            # import json as _json
            # print(_json.dumps(matches, indent=2))
            return json(matches)
    else:
        matches = ujson.loads(request.form['matches'][0])
        matches = list(zip(*matches))
        matches[0] = await _frees(hang, matches[0])
        matches[1] = [[[ObjectId(_id) for _id in points] for points in paths] for paths in matches[1]]
        paths = sum(sum([ObjectId(_id) for _id in points] for points in paths) for paths in matches[1])
        paths = await config.paths.find({'points.$._id' in paths})
        points = dict()
        for path in paths:
            for point in reversed(path['points']):
                if point['_id'] not in points:
                    points[point['_id']] = []
                points[point['_id']].append(point)
        points = {{point['_id']: point for point in path} for path in paths}
        for paths in matches[1]:
            for i, _points in enumerate(paths):
                path = {
                    'points': []
                }
                for point in _points:
                    path['points'].append(points['fewfew'])

        matches = list(zip(*matches))
    matches = await prepare(matches)
    await notify(request, hang, matches)
    return json({'SUCCESS': True, 'huli': 'muli'})


async def notify(request, hang, matches):
    promises = []
    protocol = 'http://' if 'http://' in request.url else 'https://'
    for porter, paths in matches:
        paths = ujson.dumps(paths)
        if 'fcm' in porter and porter['fcm']:
            print(" > WTF < ", porter)
            message = Message(
                device_token=porter['fcm'],
                notification={  # optional
                    "title": "OFFER",
                    "body": "new offers received",
                    # "sound": "default"
                    "sound": "refah"
                },
                data={"paths": paths},  # optional
                message_id=str(uuid4()),  # optional
                time_to_live=3,  # optional
                priority=PRIORITY_HIGH,  # optional
            )
            promises.append(config.fcm.send_message(message))
        else:
            promises.append(config.session.post(
                protocol + request.host + '/v0.2/client/sims/{}/{}'.format(hang, porter['porter'])
                , data={'paths': paths}
            ))
    asyncio.ensure_future(promise(promises))


async def promise(promises):
    promises = [promises[i * wrk: min((i + 1) * wrk, len(promises))] for i in range(ceil(len(promises) / wrk))]

    for p in promises:
        try:
            await asyncio.gather(*p)
        except:
            pass


@blu.route('/<hang>/<user>/@messages')
@privileges({'a', 'b', 'o', 'p'})
async def know(request, payload, user, hang):
    ban(payload, user, hang)
    msg = config.notifications.get(user, None)
    msg = [msg] if msg else []
    return text(ujson.dumps(msg, cls=JSONEncoder))

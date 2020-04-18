from scipy.spatial import cKDTree
import numpy as np
import math
from tools.pqdict import pqdict
from sklearn.mixture import GaussianMixture
from datetime import datetime, timedelta
import pickle
from sanic import Blueprint
from sanic.response import html, json
import jinja2
from client import templates
import config
import hdbscan
from multiprocessing import Value
from multiprocessing.managers import BaseManager
from ctypes import c_bool
import matplotlib.pyplot as plt
from collections import namedtuple
from tools import parse_path
import asyncio
from static import osrm_host
import ujson
from geopy.distance import vincenty

np.seterr(all='ignore')
blu = Blueprint(__name__, url_prefix='/v0.2/client/bi')
mus_filename = __file__.split('/')
mus_filename = '/'.join(mus_filename[:mus_filename.index('V') + 1]) + '/static/mus/'


@blu.route('/<hang>/!!')
async def _export_all_dailies(request, hang):
    porters = await config.users.find({
        'hang': hang,
        'privilege': 'p'
    }).to_list(None)
    asyncio.ensure_future(asyncio.gather(*[export_duration(p['user'], hang) for p in porters]))
    return json({'SUCCESS': True})


@blu.route('/<hang>/<porter>/!!')
async def _export_dailies(request, porter, hang):
    await export_duration(porter, hang)
    return json({'SUCCESS': True})


@blu.route('/<hang>/!')
async def export_all(request, hang):
    porters = await config.users.find({
        'hang': hang,
        'privilege': 'p'
    }).to_list(None)
    asyncio.ensure_future(asyncio.gather(*[export_mu(p['user'], hang) for p in porters]))
    return json({'SUCCESS': True})


@blu.route('/<hang>/<porter>/!')
async def _export_mu(request, porter, hang):
    await export_mu(porter, hang)
    return json({'SUCCESS': True})


@blu.route('/<hang>/<porter>')
@blu.route('/<hang>')
async def porter_bi(request, hang, porter=None):
    bi_template = templates.get_template("bi.html")
    return html(
        bi_template.render(meta={'title': hang + "'s BI", 'input': ('@' + porter) if porter else ''}, hang=hang))


@blu.route('/<hang>/<porter>', methods=['POST'])
async def _durations(request, porter, hang):
    paths = await config.paths.find({
        'hang': hang,
        'porters': {
            '$elemMatch': {
                'porter': porter,
                'ack': True,
                '_date': {
                    '$gte': datetime.now() - timedelta(days=10)
                }
            }
        },
        'points.duration': {'$exists': True}
    }, {
        'points.duration': 1,
        'points.exp_duration': 1,
        'points._date': 1,
    }).to_list(None)
    for path in paths:
        del path['_id']
        for p in path['points']:
            if '_date' in p:
                p['_date'] = str(p['_date'])
    return json(paths)


@blu.route('/<hang>/<porter>/<frame>', methods=['GET', 'POST'])
async def _frame(request, porter, hang, frame):
    return json(manager.frame(porter, *parse_path(frame), hang))


async def export_duration(porter, hang):
    locations = await config.locations.find({
        'hang': hang,
        'porter': porter,
        '_date': {
            '$lt': datetime.now(),
            '$gte': datetime.now() - timedelta(days=10)
        },
        # 'points': {'$exists': True}
    }).to_list(None)

    # print(len(locations))
    if len(locations) == 0:
        return
    # set_id = None
    if 'points' not in locations[-1]:
        while 'points' not in locations[-1]:
            locations.pop()
    else:
        set_id = set(p['_id'] for p in locations[-1]['points'])
        while 'points' in locations[-1] and locations[-1]['points'][0]['_id'] in set_id:
            locations.pop()
    if len(locations) == 0:
        return
    if 'points' not in locations[0]:
        while 'points' not in locations[0]:
            locations = locations[1:]
    else:
        set_id = set(p['_id'] for p in locations[0]['points'])
        while 'points' in locations[0] and locations[0]['points'][0]['_id'] in set_id:
            locations = locations[1:]
    # for l in locations:
    #     print(l)

    # print(len(locations))
    # from bson import ObjectId
    # print('**')
    # for i, l in enumerate(locations):
    #     if 'points' in l and l['points'][0]['_id'] == ObjectId('5d3c87b94f517b424ad0a85f'):
    #         print(i)
    # print('**')
    set_id = None
    p_locations = []
    for l in locations:
        if 'points' in l:
            if not set_id or l['points'][0]['_id'] not in set_id:
                set_id = set(p['_id'] for p in l['points'])
                p_locations.append([])
            p_locations[-1].append(l)
        else:
            set_id = None
    lookup = dict()
    for i, paths in enumerate(p_locations):
        for point in paths[0]['points']:
            lookup[point['_id']] = i
    # print(len(p_locations))
    paths = await config.paths.find({
        'hang': hang,
        'points._id': {
            '$in': [paths[0]['points'][0]['_id'] for paths in p_locations]
        }
    }).to_list(None)
    # print(len(paths))
    # for l in p_locations[0]:
    #     print(l)
    for path in paths:
        locations = p_locations[lookup[path['points'][0]['_id']]]
        points = path['points']
        for acked_porter in path['porters']:
            if acked_porter['ack']:
                break
        points.append({'at': acked_porter['_date'], 'location': acked_porter['location']})
        _points = [points.pop()]
        idx = set()
        while points:
            p = points.pop()
            if abs(p['location'][0] - _points[-1]['location'][0]) + abs(
                    p['location'][1] - _points[-1]['location'][1]) > .0001:
                _points.append(p)
            else:
                idx.add(len(points))
        points = _points

        missions = [[]]
        for l in locations:
            while l['_date'] > points[len(missions)]['at']:
                missions.append([])
            missions[-1].append(l)
        for i, mission in enumerate(missions):
            last_point = None
            while mission and abs(mission[-1]['location'][0] - points[i + 1]['location'][0]) + abs(
                    mission[-1]['location'][1] - points[i + 1]['location'][1]) < .0001:
                last_point = mission.pop()
            if last_point:
                # pass
                mission.append(last_point)
        # dist = [(i, abs(l['location'][0] - points[2]['location'][0]) + abs(l['location'][1] - points[2]['location'][1])) for i, l in enumerate(missions[1])]
        # dist = sorted(dist, key=lambda x: x[1])
        # print(dist)
        durations = []
        exp_durations = []
        for m_locations in missions:
            if len(m_locations) <= 100:
                param = ';'.join(['{},{}'.format(l['location'][1], l['location'][0]) for l in m_locations])
                try:
                    async with config.session.get(osrm_host + '/match/v1/driving/' + param) as response:
                        osrm_d = sum(step['duration'] for step in
                                     ujson.loads(await response.text())['matchings'][0]['legs'])
                except KeyError:
                    async with config.session.get(osrm_host + '/route/v1/driving/' + param) as response:
                        osrm_d = sum(step['duration'] for step in
                                     ujson.loads(await response.text())['routes'][0]['legs'])

                ### print(vincenty(m_locations[-1]['location'], m_locations[0]['location']).m)
                exp_durations.append(osrm_d)
                durations.append((m_locations[-1]['_date'] - m_locations[0]['_date']).total_seconds() * 17)

        query = {}
        for i in range(len(durations) + len(idx)):
            if i in idx:
                query['points.{}.duration'.format(i)] = 0
                query['points.{}.exp_duration'.format(i)] = 0
            else:
                query['points.{}.duration'.format(i)] = durations.pop()
                query['points.{}.exp_duration'.format(i)] = exp_durations.pop()
        await config.paths.update_one({'_id': path['_id']}, {'$set': query})


async def export_mu(porter, hang):
    locations = await config.locations.find({
        'hang': hang,
        'porter': porter,
        '_date': {
            '$lt': datetime.now(),
            '$gte': datetime.now() - timedelta(days=10)
        },
        # 'points': {'$exists': True}
    }).to_list(None)
    metas = locations
    for d in metas:
        del d['porter']
        del d['_id']
        del d['hang']
        d['load'] = len(d['points']) if 'points' in d else 0
        if 'points' in d:
            del d['points']

    locations = [l['location'] for l in locations]
    try:
        with open(mus_filename + hang + '.' + porter + '.pkl', 'rb') as pickled:
            pickled = pickle.load(pickled)
            pickled = [datetime.now(), pickled.pop(), pickled]
    except FileNotFoundError:
        pickled = [datetime.now(), None, []]

    # concat
    locations.extend([p['mean'] for p in pickled[2]])
    metas.extend(p for p in pickled[2])  # it is recursive first need to make answer then goto(here)
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min(15, len(locations)), min_samples=min(20, len(locations)))
    labels = clusterer.fit_predict(locations) + 1

    scores = [(i, clusterer.outlier_scores_[i]) for i in range(len(locations))]
    while scores and len(scores) * 3 > len(locations) * 2 and scores[-1][1] > .8:
        scores.pop()

    clusters = len(np.bincount(labels))
    metas = [metas[i] for i, _ in scores]
    locations = [locations[i] for i, _ in scores]
    labels = [labels[i] for i, _ in scores]
    clusters = [[] for _ in range(clusters)]
    # print('size', len(clusters))
    for i, l in enumerate(labels):
        clusters[l].append(i)
        metas[i]['label'] = l
    bubbles = []
    for label, cluster in enumerate(clusters[0:]):
        _locations = [locations[c] for c in cluster]
        clusterer = GaussianMixture(n_components=int(len(set(tuple(l) for l in _locations)) ** .444),
                                    covariance_type='spherical')
        _labels = clusterer.fit_predict(_locations)
        _clusters = len(np.bincount(_labels))
        _clusters = [[] for _ in range(_clusters)]
        for i, l in enumerate(_labels):
            _clusters[l].append(i)
        # print('*', len(_clusters), clusterer.n_components)
        for i in range(len(_clusters)):
            # print(_clusters[i])
            bubbles.append({
                'id': len(bubbles),
                'mean': list(clusterer.means_[i]),
                'covariance': clusterer.covariances_[i],
                'weight': clusterer.weights_[i],
                'label': label,
                'load': (sum(metas[cluster[c]]['load'] for c in _clusters[i]) / len(_clusters[i])) if len(
                    _clusters[i]) else 0
                # **metas
            })
    # for b in bubbles:
    #     plt.scatter(*b['mean'], s=b['covariance'] ** .5 * 10000)
    kd = cKDTree([b['mean'] for b in bubbles])
    bubbles.append(kd)
    # plt.show()
    with open(mus_filename + hang + '.' + porter + '.pkl', 'wb') as pickled:
        pickle.dump(bubbles, pickled, protocol=pickle.HIGHEST_PROTOCOL)
        manager.delete(porter, hang)


class Familiarity:
    def __init__(self):
        self.porters = pqdict(key=lambda node: node[0])

    def delete(self, porter, hang):
        porter = hang + '.' + porter
        if porter in self.porters:
            del self.porters[porter]

    def fame(self, porters, points, hang):  # some options
        responses = []
        for porter in porters:
            porter = hang + '.' + porter
            if porter not in self.porters:
                try:
                    with open(mus_filename + porter + '.pkl', 'rb') as pickled:
                        pickled = pickle.load(pickled)
                        self.porters[porter] = [datetime.now(), pickled.pop(), pickled]
                        if len(self.porters) > 30000:
                            self.porters.pop()
                except FileNotFoundError:
                    self.porters[porter] = [datetime.now(),
                                            namedtuple('cKDTree', 'query n')(query=lambda location, k: ([], []), n=0),
                                            []]

            _, kd, metas = self.porters[porter]
            responses.append([])
            for p in points:
                dist, idx = kd.query(p, k=min(kd.n, 12))
                responses[-1].append(sum(metas[_id]['weight'] for _id in idx))
                responses[-1][-1] /= dist[-1] ** 2 * math.pi if len(dist) else 1
        return responses

    def durations(self, porters, points, hang):
        fame = self.fame(porters, points, hang)
        return [[1 / (1 + math.exp(-x)) * 300 for x in row] for row in fame]

    def frame(self, porter, s_lat, s_lng, t_lat, t_lng, hang):
        porter = hang + '.' + porter
        if porter not in self.porters:
            try:
                with open(mus_filename + porter + '.pkl', 'rb') as pickled:
                    pickled = pickle.load(pickled)
                    self.porters[porter] = [datetime.now(), pickled.pop(), pickled]
                    if len(self.porters) > 30000:
                        self.porters.pop()
            except FileNotFoundError:
                self.porters[porter] = [datetime.now(),
                                        namedtuple('cKDTree', 'query n')(query=lambda location, k: ([], []), n=1), []]
        _, kd, metas = self.porters[porter]
        m_lat = (s_lat + t_lat) / 2
        m_lng = (s_lng + t_lng) / 2
        d_lat = abs(s_lat - t_lat) / 2
        d_lng = abs(s_lng - t_lng) / 2
        for i in range(max(min(3, int(math.log2(kd.n)) - 1), 0), int(math.log2(kd.n)) + 2):
            k = 2 ** i
            # print('k', k)
            dist, idx = kd.query((m_lat, m_lng), k=min(k, kd.n))
            if len(dist) == 0:
                break
            furthest = metas[idx[-1]]['mean']
            # print('f', furthest)
            # print('m', m_lat, m_lng)
            # print('d', d_lat, d_lng)
            if m_lat - d_lat > furthest[0] or m_lat + d_lng < furthest[0]:
                # print('lat')
                break
            if m_lng - d_lng > furthest[1] or m_lng + d_lng < furthest[1]:
                # print('lng')
                break
        return [metas[i] for i in idx]


BaseManager.register('Familiarity', Familiarity)
manager = BaseManager()
manager.start()
manager = manager.Familiarity()

lock = Value(c_bool, False)


# @blu.listener('before_server_start')
# async def test(sanic, _loop):
#     if not lock.value:
#         lock.value = True
#         # print(manager.fame(['lydia'], [[35.742335, 51.384946], [35.7, 51.4]], 'q7'))
#         # print(manager.frame('lydi', 35.742335, 51.384946, 35.7, 51.4, 'q7'))
#         # await export_mu('lydia', 'q7')
#         # await export_duration('ryan', 'x1')

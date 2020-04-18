from random import shuffle
import numpy as np
import config
import asyncio
import ujson as json
from scipy.optimize import linear_sum_assignment
import math
from static import osrm_host
from datetime import datetime, timedelta
from random import random, choice, choices
from copy import deepcopy
import os
from bson import ObjectId
import re
from client.bi import manager as bi

tmp = __file__[:-11] + 'ramdisk/'
"""
for finding ( distance | duration ) matrix ->
    1. brute force
    2. bfs and find all with summation => d(vu) = d(vx) + d(xu) ~ d(vx) + d(xu)

http://download.xuebalib.com/xuebalib.com.13149.pdf

    patching rate
    porter customized for a region
    minimum matching
    release rate
    fcm delay send (for each some alternative)

listen on ...
"""
p2f = {
    'gkh': 2.25,
    'bkh': 2.25,
    'hng': 1.5,
    'grd': 1.5,
}


def homologous(frees, paths):
    if len(frees) > len(paths):
        return frees[:len(paths)], paths
    return frees, paths[:len(frees)]


async def rnd(frees, paths, protocols=''):
    frees, paths = homologous(frees, paths)
    shuffle(paths)
    return [(p, [paths[i]]) for i, p in enumerate(frees)]


async def matrix(frees, paths):
    m = np.zeros((len(frees), len(paths)))

    async def retrieve(f_head, f_tail, p_head, p_tail):
        points = '{};{}'.format(
            ';'.join(['{},{}'.format(f['location'][1], f['location'][0]) for f in frees[f_head:f_tail]]),
            ';'.join(['{},{}'.format(*reversed(p['points'][-1]['location'])) for p in paths[p_head:p_tail]]),
        )
        async with config.session.get(osrm_host + '/table/v1/driving/' + points, params={
            'sources': ';'.join([str(i) for i in range(f_tail - f_head)]),
            'destinations': ';'.join([str(i) for i in range(f_tail - f_head, f_tail - f_head + p_tail - p_head)])
        }) as response:
            m[f_head: f_tail, p_head: p_tail] = np.array(json.loads(await response.text())['durations'])

    chunk = 100
    chunked = lambda chunkee: [min(i * chunk, len(chunkee)) for i in range(1 + math.ceil(len(chunkee) / chunk))]
    nexted = lambda nextee: [(n, nextee[i + 1]) for i, n in enumerate(nextee[:-1])]

    await asyncio.gather(*[retrieve(f_head, f_tail, p_head, p_tail)
                           for f_head, f_tail in nexted(chunked(frees))
                           for p_head, p_tail in nexted(chunked(paths))])
    return m


async def grd(frees, paths, fastness=1, protocols=''):
    rows = []
    shuffle(paths)
    cost = (await matrix(frees, paths)).T
    for i in range(min(len(frees), len(paths))):
        rows.append(min([(i, v) for (i, v) in enumerate(cost[i]) if i not in rows], key=lambda x: x[1])[0])
    # print('greedy', [cost[i][v] for (i, v) in enumerate(rows)])
    return [(frees[rows[i]], [p]) for i, p in enumerate(paths[:min(len(frees), len(paths))])]
    # return [(frees[j], paths[i]) for i, j in enumerate(rows)]


async def hng(frees, paths, fastness=1, protocols=''):
    cost = await matrix(frees, paths)
    cost += bi.durations([f['porter'] for f in frees], [path['points'][-1]['location'] for path in paths], frees[0]['hang'] if frees else paths[0]['hang'])
    row_idx, col_idx = linear_sum_assignment(cost)
    # print('hungarian', cost[row_idx, col_idx].sum())
    return [(frees[row_idx[i]], [paths[col_idx[i]]]) for i in range(min(len(frees), len(paths)))]


def batch(p, q, order, copy=True):
    if order is None:
        order = False
        start = q['points'][-1]['location']
        stop0 = q['points'][0]['location']
        stop1 = p['points'][0]['location']
        if abs(start[0] - stop0[0]) + abs(start[1] - stop0[1]) > abs(start[0] - stop1[0]) + abs(start[1] - stop1[1]):
            order = True
    if copy:
        p = deepcopy(p)
    p['points'].extend(q['points'])
    p['points'][1], p['points'][2] = p['points'][2], p['points'][1]
    p['points'][2], p['points'][3] = p['points'][3], p['points'][2]
    if not order:
        p['points'][0], p['points'][1] = p['points'][1], p['points'][0]
    return p


async def batches(paths, ds, dt):
    def euclidean(v, u):
        return abs(v[0] - u[0]) + abs(v[1] - u[1])

    async def real(path, bs):
        points = '{};{}'.format(
            '{},{};{},{}'.format(*reversed(path['points'][-1]['location']), *reversed(path['points'][0]['location'])),
            ';'.join(['{},{};{},{}'.format(
                *reversed(p['points'][-1]['location']), *reversed(p['points'][0]['location'])
            ) for p, _ in bs]),
        )
        async with config.session.get(osrm_host + '/table/v1/driving/' + points, params={
            'sources': '0;1;' + ';'.join([str(i + 2) for i in range(2 * len(bs))]),
            'destinations': ';'.join([str(i + 2) for i in range(2 * len(bs))]) + ';1'
        }) as response:
            durations = json.loads(await response.text())['durations']
            h = durations[0][-1]
            for i, p in enumerate(bs):
                t = durations[i * 2 + 2][i * 2 + 1]
                ht = durations[0][2 * i]
                cross = durations[i * 2 + 2][-1]
                forward_ht = durations[i * 2 + 3][-1]
                backward_ht = durations[1][i * 2 + 1]
                forward_ht = ht + forward_ht - h + 150 + 150  # + t - t
                backward_ht = ht + cross + backward_ht - (
                        t + h) + 150 + 150  # FIXME 300 is not wrong but not accurate expected to arrive to t
                if forward_ht < backward_ht:
                    p.append(False)
                    p[1] = forward_ht
                else:
                    p.append(True)
                    p[1] = backward_ht

    for h in paths:
        he = euclidean(h['points'][-1]['location'], h['points'][0]['location'])
        h['batches'] = []
        for t in paths:
            if h is not t:
                _h, _t = h['points'], t['points']
                te = euclidean(_t[-1]['location'], _t[0]['location'])
                synergy = euclidean(_h[-1]['location'], _t[-1]['location']) + min(te, euclidean(_t[-1]['location'],
                                                                                                _h[0][
                                                                                                    'location'])) + euclidean(
                    _t[0]['location'], _h[0]['location']) - he - te
                if synergy < .5 * (he + te):  # to .2
                    h['batches'].append([t, synergy])
        h['batches'] = sorted(h['batches'], key=lambda x: x[1])[: min(13, len(h['batches']))]
    k = 13
    await asyncio.gather(*sum([[real(p, p['batches'][i * k:min(i * k + k, len(p['batches']))]) for i in
                                range(math.ceil(len(p['batches']) / k))] for p in paths if p['batches']], []))
    for p in paths:
        p['batches'] = sorted(p['batches'], key=lambda x: x[1])


async def bg(frees, paths, ds=True, dt=True):
    # the greedy algorithm that have batching, priority(emergencies), offers <------> ;)
    # some porters have delay to arrive to their locations .#2 on emergencies
    await batches(paths, ds, dt)
    cost = (await matrix(frees, paths)).T
    for p in frees:
        p['matches'] = [None] * (2 if random() < .5 else 3)
    for i, p in enumerate(paths):
        p['idx'] = i
    # emergency set with .#2 mu of orders
    emergencies = []
    now = datetime.now()
    for p in paths:
        if now - p['points'][-1]['_date'] > timedelta(minutes=p['points'][-1]['priority'] ** 2):
            emergencies.append(p)
    em_ratio = len(paths) / (len(emergencies) + 1)
    while len(paths):
        if random() > len(paths) / (len(paths) + len(emergencies) * em_ratio):
            p = choice(emergencies)
        else:
            p = choice(paths)
        if p in emergencies:
            emergencies.remove(p)
        paths.remove(p)
        candidates = sorted([(frees[i], v) for (i, v) in enumerate(cost[p['idx']]) if not frees[i]['matches'][-1]],
                            key=lambda x: x[1])
        if not candidates:
            break
        candidates = candidates[:min(len(candidates), (2 if random() < .5 else 3))]
        pr = random()
        if pr < .666 and p['batches']:
            pr = 1
            for q, synergy, order in p['batches']:
                if q in paths and synergy < 0:
                    if q in emergencies:
                        emergencies.remove(q)
                    paths.remove(q)
                    for porter, _ in candidates:
                        porter['matches'][porter['matches'].index(None)] = batch(p, q, order, copy=False)
                    pr = 0
                    break
        if pr >= .666:
            for porter, _ in candidates:
                porter['matches'][porter['matches'].index(None)] = p
    response = [(p, [match for match in p['matches'] if match]) for p in frees]
    for p, _paths_ in response:
        for path in _paths_:
            if 'matches' in path:
                del path['matches']
            if 'batches' in path:
                del path['batches']
    th = [0, 0]
    pth = [0, 0]
    for porter, paths in response:
        th[len(paths) - 1] += 1
        for p in paths[:1]:
            pth[int(len(p['points']) / 2) - 1] += 1
        # print(porter['porter'], paths)
        print([len(p['points']) for p in paths])
    print(len(response))
    print(th)
    print(th[0] / (sum(th) + .1))
    print('***')
    print(pth)
    print(pth[0] / (sum(pth) + .1))
    return response


async def bh(frees, paths, ds=True, dt=True):
    # with probability choose
    await batches(paths, ds, dt)
    cost = await matrix(frees, paths)
    batch_cost = cost.copy()
    for i, p in enumerate(paths):
        p['cnt'] = 1 if random() < .2 else 2 if random() < .82 else 3
        batch_cost[:, i] += np.ones(len(batch_cost)) * (
            p['batches'][0][1] if p['batches'] else 2000000)
    for p in frees:
        p['cnt'] = 2
    # batch_cost *= 1.3
    matches = []
    for ite in range(1):
        row_idx, col_idx = linear_sum_assignment(cost)
        matches.extend([(
            frees[row_idx[i]],
            (paths[col_idx[i]],),
            cost[row_idx[i]][col_idx[i]], ite
        ) for i in range(min(len(frees), len(paths)))])
        cost[row_idx, col_idx] += np.ones(len(row_idx)) * 1000000
    for ite in range(1):
        row_idx, col_idx = linear_sum_assignment(batch_cost)
        matches.extend([(frees[row_idx[i]], (
            paths[col_idx[i]],
            paths[col_idx[i]]['batches'][0][0],
            paths[col_idx[i]]['batches'][0][2]),
                         batch_cost[row_idx[i]][col_idx[i]], ite
                         ) for i in range(min(len(frees), len(paths))) if paths[col_idx[i]]['batches']])
        batch_cost[row_idx, col_idx] += np.ones(len(row_idx)) * 1000000
    now = datetime.now()
    matches = sorted(matches, key=lambda match: match[3] * 660 + match[2])
    # - max(
    #     (now - match[1][0]['points'][-1]['_date']).total_seconds() / 60 / match[1][0]['points'][-1]['priority'],
    #     (now - match[1][1]['points'][-1]['_date']).total_seconds() / 60 / match[1][1]['points'][-1]['priority'] if len(match[1]) > 1 else 0
    # ))
    # _matches_ = [(c, i, u['porter'], str(p[0]['_id']), str(p[1]['_id']) if len(p) > 1 else '_') for u, p, c, i in matches]
    # print(len(_matches_))
    for path in paths:
        del path['batches']
    candidates = {}
    for porter, paths, _, _ in matches:
        if (porter['cnt'] and paths[0]['cnt'] and (len(paths) == 1 or paths[1]['cnt'])) or porter[
            'porter'] not in candidates:
            paths[0]['cnt'] -= 1
            porter['cnt'] -= 1
            if porter['porter'] not in candidates:
                candidates[porter['porter']] = (porter, [])
            if len(paths) == 1:
                candidates[porter['porter']][1].append(paths[0])
            else:
                paths[1]['cnt'] -= 1
                candidates[porter['porter']][1].append(batch(*paths))

    # th = [0, 0]
    # pth = [0, 0]
    # for porter, paths in candidates.values():
    #     th[len(paths) - 1] += 1
    #     for p in paths[:1]:
    #         pth[int(len(p['points']) / 2) - 1] += 1
    #     # print(porter['porter'], paths)
    #     print([len(p['points']) for p in paths])
    # print(len(candidates))
    # print(th)
    # print(th[0] / sum(th))
    # print('***')
    # print(pth)
    # print(pth[0] / sum(pth))
    return candidates.values()


async def bgh(frees, paths, ds=True, dt=True):
    # with probability choose
    await batches(paths, ds, dt)
    h = await hng(frees, paths)
    # sort h then see the difference
    matched = set()
    _frees = []
    frees_set = set()
    # for _, porter_paths in h:
    #     matched.add(porter_paths[0]['_id'])
    for porter, porter_paths in h:
        path = porter_paths[0]
        if path['_id'] in matched:
            _frees.append(porter)
            frees_set.add(porter['porter'])
            continue
        matched.add(path['_id'])
        for q, c, o in path['batches']:
            if q['_id'] not in matched and c < 0:
                matched.add(q['_id'])
                porter_paths.append(q)
                porter_paths.append(o)
                break

    h = [(porter, _paths_) for porter, _paths_ in h if porter['porter'] not in frees_set]
    for path in paths:
        del path['batches']
    paths = [p for p in paths if p['_id'] not in matched]
    h.extend(await hng(_frees, paths))
    for _, porter_paths in h:
        if len(porter_paths) == 3:
            path = batch(*porter_paths)
            porter_paths.clear()
            porter_paths.append(path)
    th = [0, 0]
    pth = [0, 0]
    for porter, paths in h:
        th[len(paths) - 1] += 1
        for p in paths[:1]:
            pth[int(len(p['points']) / 2) - 1] += 1
        # print(porter['porter'], paths)
    print(len(h))
    print(th)
    print(th[0] / (sum(th) + 1))
    print('***')
    print(pth)
    print(pth[1] / (sum(pth) + 1))
    return h


async def half_batched(paths, ds, dt):
    async def durations(locations):
        m = np.zeros((len(locations), len(locations)))

        async def retrieve(f_head, f_tail, p_head, p_tail):
            points = '{};{}'.format(
                ';'.join(['{},{}'.format(f[1], f[0]) for f in locations[f_head:f_tail]]),
                ';'.join(['{},{}'.format(p[1], p[0]) for p in locations[p_head:p_tail]]),
            )
            async with config.session.get(osrm_host + '/table/v1/driving/' + points, params={
                'sources': ';'.join([str(i) for i in range(f_tail - f_head)]),
                'destinations': ';'.join([str(i) for i in range(f_tail - f_head, f_tail - f_head + p_tail - p_head)])
            }) as response:
                m[f_head: f_tail, p_head: p_tail] = np.array(json.loads(await response.text())['durations'])

        chunk = 100
        chunked = lambda chunkee: [min(i * chunk, len(chunkee)) for i in range(1 + math.ceil(len(chunkee) / chunk))]
        nexted = lambda nextee: [(n, nextee[i + 1]) for i, n in enumerate(nextee[:-1])]

        await asyncio.gather(*[retrieve(f_head, f_tail, p_head, p_tail)
                               for f_head, f_tail in nexted(chunked(paths))
                               for p_head, p_tail in nexted(chunked(paths))])
        return m

    return await durations([p['points'][-1]['location'] for p in paths]) + \
           await durations([p['points'][-1]['location'] for p in paths])


async def h2(frees, paths, ds=True, dt=True):
    cost = await matrix(frees, paths)
    if len(frees) >= len(paths):
        row_idx, col_idx = linear_sum_assignment(cost)
    else:
        bs = await half_batched(paths, ds, dt)
        row_idx, col_idx = linear_sum_assignment(cost)
        rand_paths_set = set(col_idx)
        others = [i for i in range(len(paths)) if i not in rand_paths_set]  # performance calculate set()each time?
        minimum_cost = cost[row_idx, col_idx].sum()
        _bs = bs[col_idx, :][:, others]
        bs_row_idx, bs_col_idx = linear_sum_assignment(_bs)
        minimum_cost += _bs[bs_row_idx, bs_col_idx].sum()
        for _ in range(72):
            rand_paths = list(range(len(paths)))
            shuffle(rand_paths)
            rand_paths = rand_paths[:len(frees)]
            rand_paths_set = set(rand_paths)
            others = [i for i in range(len(paths)) if i not in rand_paths_set]  # performance calculate set()each time?
            _cost = cost[:, rand_paths]
            _row_idx, _col_idx = linear_sum_assignment(_cost)
            _cost = _cost[_row_idx, _col_idx].sum()
            _bs = bs[rand_paths, :][:, others]
            _bs_row_idx, _bs_col_idx = linear_sum_assignment(_bs)
            _cost += _bs[_bs_row_idx, _bs_col_idx].sum()
            if _cost < minimum_cost:
                minimum_cost = _cost
                print(_cost)
                row_idx = _row_idx
                col_idx = [rand_paths[idx] for idx in _col_idx]
                bs_row_idx = [rand_paths[idx] for idx in _bs_row_idx]
                bs_col_idx = [others[idx] for idx in _bs_col_idx]
        for i, idx in enumerate(bs_row_idx):
            if bs[idx][bs_col_idx[i]] < 456:
                paths[idx] = batch(paths[idx], paths[bs_col_idx[i]], None, copy=False)
    h = [(frees[row_idx[i]], [paths[col_idx[i]]]) for i in range(min(len(frees), len(paths)))]
    th = [0, 0]
    pth = [0, 0]
    for porter, paths in h:
        th[len(paths) - 1] += 1
        for p in paths[:1]:
            pth[int(len(p['points']) / 2) - 1] += 1
    print(pth)
    print(pth[1] / (sum(pth) + 1))
    return h


async def distance(locations):
    m = np.zeros((len(locations), len(locations)))

    async def retrieve(s_head, s_tail, t_head, t_tail):
        points = '{};{}'.format(
            ';'.join(['{},{}'.format(l[1], l[0]) for l in locations[s_head: s_tail]]),
            ';'.join(['{},{}'.format(l[1], l[0]) for l in locations[t_head: t_tail]]),
        )
        async with config.session.get(osrm_host + '/table/v1/driving/' + points, params={
            'sources': ';'.join([str(i) for i in range(s_tail - s_head)]),
            'destinations': ';'.join([str(i) for i in range(s_tail - s_head, s_tail - s_head + t_tail - t_head)])
        }) as response:
            m[s_head: s_tail, t_head: t_tail] = np.array(json.loads(await response.text())['durations'])

    chunk = 100
    chunked = lambda chunkee: [min(i * chunk, len(chunkee)) for i in range(1 + math.ceil(len(chunkee) / chunk))]
    nexted = lambda nextee: [(n, nextee[i + 1]) for i, n in enumerate(nextee[:-1])]

    await asyncio.gather(*[retrieve(f_head, f_tail, p_head, p_tail)
                           for f_head, f_tail in nexted(chunked(locations))
                           for p_head, p_tail in nexted(chunked(locations))])
    return m


async def lkh(paths, vehicles, distance_matrix=None, fastness=1, capacity=40):
    _name = str(ObjectId())
    with open(tmp + '{}.cvrptw'.format(_name), 'w') as f:
        f.write("""NAME : C3
TYPE : CVRPTW
CAPACITY : {capacity}
SERVICE_TIME : {service_time}
SCALE : 10
EDGE_WEIGHT_FORMAT : FULL_MATRIX
DIMENSION : {dimensions}
VEHICLES : {vehicles}
EDGE_WEIGHT_SECTION
""".format(dimensions=len(paths) + 1, vehicles=vehicles, service_time=90 / fastness, capacity=capacity))
        # the base location in one of them
        if distance_matrix is None:
            distance_matrix = await distance(
                [paths[0]['points'][-1]['location']] + [path['points'][0]['location'] for path in paths])
        distance_matrix /= fastness
        for row in distance_matrix:
            f.write(' '.join(str(num) for num in row))
            f.write('\n')
        f.write('DEMAND_SECTION\n')
        f.write('1 0\n')
        for i, path in enumerate(paths):
            f.write('{} {}\n'.format(i + 2, path['points'][-1]['volume']))
        now = min(path['points'][0]['head'] for path in paths)
        max_tail = max(path['points'][0]['tail'] for path in paths)
        f.write('TIME_WINDOW_SECTION\n')
        f.write('{} {} {}\n'.format(1, 0, (max_tail - now).seconds))
        for i, path in enumerate(paths):
            f.write('{} {} {}\n'.format(i + 2, int((path['points'][0]['head'] - now).total_seconds()),
                                        int((path['points'][0]['tail'] - now).total_seconds())))
        f.write("""DEPOT_SECTION
1
-1
EOF\n""")

    with open(tmp + '{}.par'.format(_name), 'w') as f:
        f.write("""SPECIAL
PROBLEM_FILE = {}
MAX_TRIALS = 90
RUNS = 1
TOUR_FILE = {}
TRACE_LEVEL = 120\n""".format(tmp + '{}.cvrptw'.format(_name), tmp + '{}.tour'.format(_name)))
    os.system("LKH {} restart > /dev/null".format(tmp + '{}.par'.format(_name)))
    os.remove(tmp + '{}.par'.format(_name))
    os.remove(tmp + '{}.cvrptw'.format(_name))
    try:
        with open(tmp + '{}.tour'.format(_name), 'r') as f:
            lines = f.readlines()
            while lines[0] != 'TOUR_SECTION\n':
                if 'Length =' in lines[0]:
                    duration = int(lines[0].split('Length =')[1].strip())
                lines = lines[1:]
            lines = lines[1:1 + len(paths) + vehicles]
            lines = [int(line[:-1]) for line in lines]
            tours = {}
            # 2 ... 144
            # 1, 145 ... 153
            aux = None
            for num in lines:
                if 1 < num < len(paths) + 2:
                    tours[aux].append(num)
                else:
                    aux = num
                    tours[aux] = []
        os.remove(tmp + '{}.tour'.format(_name))
        return tours, duration
    except FileNotFoundError:
        return None, None


async def gkh_search(paths, fastness=1, protocols=''):
    capacity = 40
    matches = re.findall(r'-C[0-9]+', protocols)
    if matches: capacity = int(matches[0][2:])
    if len(paths) < 2:
        return None
    head = 1
    tail = min(4, len(paths))
    distance_matrix = await distance(
        [paths[0]['points'][-1]['location']] + [path['points'][0]['location'] for path in paths])
    while True:
        if tail > len(paths):
            return None
        tour, duration = await lkh(paths, tail, distance_matrix=distance_matrix, fastness=fastness, capacity=capacity)
        if tour:
            break
        head = tail
        tail = 2 * tail
    # return tour
    # print(len(tour))

    while tail - head > 1:
        m = int((tail + head) / 2)
        _tour, duration = await lkh(paths, m, distance_matrix=distance_matrix, fastness=fastness, capacity=capacity)
        if _tour:
            tour = _tour
            # print(len(tour))
            tail = m
        else:
            head = m
    return tour


async def ckh_search(paths, fastness=1, protocols=''):
    capacity = 40
    matches = re.findall(r'-C[0-9]+', protocols)
    if matches: capacity = int(matches[0][2:])
    if len(paths) < 2:
        return None
    head = 1
    tail = len(paths)
    distance_matrix = await distance([paths[0]['points'][-1]['location']] + [path['points'][0]['location'] for path in paths])
    best_tour, fitness = await lkh(paths, tail, distance_matrix=distance_matrix, fastness=fastness, capacity=capacity)
    return best_tour


async def bkh_search(paths, fastness=1, protocols='', sigma=1):
    capacity = 40
    matches = re.findall(r'-C[0-9]+', protocols)
    if matches: capacity = int(matches[0][2:])
    if len(paths) < 2:
        return None
    head = 1
    tail = len(paths)
    distance_matrix = await distance([paths[0]['points'][-1]['location']] + [path['points'][0]['location'] for path in paths])
    best_tour, fitness = await lkh(paths, tail, distance_matrix=distance_matrix, fastness=fastness, capacity=capacity)
    # to ensure first one has answer so each fail must have a previous success.
    if not best_tour:
        return None
    fitness = tail * capacity * sigma + fitness
    while tail - head > 1:
        m = int((tail + head) / 2)
        _tour, duration = await lkh(paths, m, distance_matrix=distance_matrix, fastness=fastness, capacity=capacity)
        if _tour:
            tour = _tour
            value = m * capacity * sigma + duration
            if value < fitness:
                fitness = value
                best_tour = tour
            tail = m
        else:
            # foreach path if length of path is long and not fully packed extend further point in path
            # if no major changes in tails:
            head = m
    return best_tour


async def kh(frees, paths, fastness=1, protocols='', lkh_search=lambda paths, fastness: bkh_search(paths, fastness, sigma=1)):
    paths_index = {}
    for path in paths:
        territory = path['points'][1]['territory']
        if territory not in paths_index:
            paths_index[territory] = [path]
        else:
            paths_index[territory].append(path)
    _paths_ = []
    for territory, paths_bulk in paths_index.items():
        tour = await lkh_search(paths_bulk, fastness=fastness)
        if tour:
            for vehicle, route in tour.items():
                if route:
                    path = paths_bulk[route[0] - 2]
                    for num in route[1:]:
                        path['points'] = paths_bulk[num - 2]['points'][0:1] + path['points'] + paths_bulk[num - 2]['points'][1:2]
                    _paths_.append(path)
        else:
            _paths_.extend(paths_bulk)
    return await hng(frees, _paths_)
    # fully packed ones == 1, has a critical point == 2, ordinary == 0 -> hng

bkh = lambda frees, paths, fastness=1, protocols='': kh(frees, paths, fastness, protocols, lambda paths, fastness: bkh_search(paths, fastness, protocols, sigma=1))
bkh = lambda frees, paths, fastness=1, protocols='': kh(frees, paths, fastness, protocols, lambda paths, fastness: ckh_search(paths, fastness, protocols))
gkh = lambda frees, paths, fastness=1, protocols='': kh(frees, paths, fastness, protocols, lambda paths, fastness: gkh_search(paths, fastness, protocols))


async def screaming_durations(paths):
    territories = {}
    for idx, path in enumerate(paths):
        location = path['points'][-1]['location']
        location = (round(location[0], 10), round(location[1], 10))
        if location not in territories:
            territories[location] = []
        territories[location].append((path['points'][0]['location'], idx))

    bulk_size = 99
    distances = [[] for _ in range(len(paths))]
    for (lat, lng), _points_ in territories.items():
        for j in range(math.ceil(len(_points_) / bulk_size)):
            points = _points_[j * bulk_size: min((j + 1) * bulk_size, len(_points_))]
            _points = '{},{};'.format(lng, lat) + ';'.join('{},{}'.format(p[0][1], p[0][0]) for p in points)
            table = await config.session.post(osrm_host + '/table/v1/driving/' + _points + '?sources=0&destinations={}'.format(';'.join(str(_idx_) for _idx_ in range(1, len(points) + 1))))
            table = await table.json()
            table = table['durations'][0]
            for idx, p in enumerate(points):
                distances[p[1]].append(table[idx])
    return distances


async def nearest_neighbor(porters, paths, availability):
    candidates = {}
    for idx, path in enumerate(paths):
        location = path['points'][-1]['location']
        location = (round(location[0], 10), round(location[1], 10))
        if location not in candidates:
            candidates[location] = []
        candidates[location].append((path, idx))

    costs = await matrix(porters, [paths[0][0] for paths in candidates.values()])
    if not availability:
        if costs.shape[0] == 0:
            return []
        min_costs = [min(costs[:, i]) for i in range(costs.shape[1])]
        costs = sum([[(min_costs[idx], path_idx) for _, path_idx in _paths_] for idx, _paths_ in enumerate(candidates.values())], [])
        return [key[0] for key in sorted(costs, key=lambda v: v[1])]
    else:
        occupied = set()
        for idx, _paths_ in enumerate(candidates.values()):
            jj, w = min(((jj, costs[jj, idx]) for jj in costs.shape[0] if jj not in occupied), key=lambda v: v[1])
            occupied.add(jj)


if __name__ == '__main__':
    # let's say we have an end point like /!!!/lkh/<depot> -> [path]
    # lkh in a while or in a random phase set vehicles
    #

    import time
    import pickle
    import aiohttp

    n = time.time()
    with open('porters.pkl', 'rb') as handle:
        _porters = pickle.load(handle)
    with open('paths.pkl', 'rb') as handle:
        _paths = pickle.load(handle)
    config.session = asyncio.get_event_loop().run_until_complete(aiohttp.ClientSession().__aenter__())
    # _matches = asyncio.get_event_loop().run_until_complete(batches(_paths, True, True))
    # values = sorted([(_p, _p['batches'][0][0], _p['batches'][0][1], _p['batches'][0][2]) for _p in _paths], key=lambda x: x[2])
    # # print(len(values))
    # print(values[100][0]['points'])
    # print(values[100][1]['points'])
    # print(len([v for v in values if v[2] < 0]) / len(values))
    # print('time:', time.time() - n)
    # _matches = asyncio.get_event_loop().run_until_complete(h2(_porters[:75], _paths[:]))

    # sc = asyncio.get_event_loop().run_until_complete(screaming_durations(_paths))
    # nn = asyncio.get_event_loop().run_until_complete(nearest_neighbor(_porters, _paths, False))

    print(len(_porters))
    print(len(_paths))
    asyncio.get_event_loop().run_until_complete(bkh(_porters, _paths))

    # for key, value in _tours.items():
    #     print(key, ': ', value)
    asyncio.get_event_loop().run_until_complete(config.session.__aexit__(None, None, None))

from sanic import Blueprint
from sanic.response import json
from sanic.exceptions import abort
from ego import privileges
from ast import literal_eval
import config
from datetime import datetime, timedelta
from bson import ObjectId
from tools import obj2str
import tools

blu = Blueprint('ql', url_prefix='/v0.2/!!')
'''
    graph ql - free users.
    graph ql - unassigned orders
    add hang to ql so can separate hangs /!!/<hang>/<collection>
'''


_hot_query = {
    'hang': None,
    'points.head': {
        '$lte': None
    },
    '$or': [
        {
            'porters.ack': {'$in': [None, False]}
        }, {
            'porters': []
        }
    ],
    'lock': {'$exists': False}
}

hot_query = lambda hang, horizon: _hot_query.update(
    {'hang': hang, 'points.head': {'$lte': datetime.now() + timedelta(seconds=horizon)}}) or _hot_query


@blu.route("/<hang>/paths/@hots", methods=['GET', 'POST'])
@privileges({'a', 'b', 'o'})
async def hot_paths(request, payload, hang):
    paths = await config.paths.find(hot_query(hang)).to_list(None)
    for path in paths:
        path['_id'] = str(path['_id'])
        for p in path['points']:
            p['_id'] = str(p['_id'])
    return json(paths)


__undone_query = {
    'hang': None,
    'points': {
        '$not': {
            '$elemMatch': {
                'volume': {'$exists': False},
                'at': {'$exists': False}
            }
        }
    }
}

_undone_query = {
    'hang': None,
    'points': {
        '$elemMatch': {
            'volume': {'$exists': False},
            'at': {'$exists': False}
        }
    }
}

undone_query = lambda hang: _undone_query.update({'hang': hang}) or _undone_query


@blu.route("/<hang>/paths/@undone", methods=['GET', 'POST'])  # undone
@privileges({'a', 'b', 'o'})
async def undone(request, payload, hang):
    paths = await config.paths.find(undone_query(hang)).to_list(None)
    for path in paths:
        path['_id'] = str(path['_id'])
        if 'lock' in path:
            path['lock'] = str(path['lock'])
        for p in path['points']:
            if 'head' in p and 'tail' in p:
                p['head'] = str(p['head'])
                p['tail'] = str(p['tail'])
            p['_id'] = str(p['_id'])
    return json(paths)


@blu.route("/<hang>/<user>/paths/@undone", methods=['GET', 'POST'])  # undone
@privileges({'a', 'b', 'o', 'p', 'u'})
async def undone(request, payload, hang, user):
    query = undone_query(hang)
    query['points']['$elemMatch']['_author'] = user
    paths = await config.paths.find(query).to_list(None)
    for path in paths:
        path['_id'] = str(path['_id'])
        for p in path['points']:
            p['_id'] = str(p['_id'])
        path['points'] = list(reversed(path['points']))
    return json(paths)


@blu.route("/<hang>/paths/<_id>", methods=['GET', 'POST'])  # undone
@privileges({'a', 'b', 'o', 'p', 'u'})
async def _path(request, payload, hang, _id):
    return json(obj2str(await config.paths.find_one({'hang': hang, 'points._id': ObjectId(_id)})))


@blu.route("/<hang>/~<points>", methods=['GET', 'POST'])
@privileges({'a', 'b', 'o', 'p'})
async def find(request, payload, hang, points):
    path = await config.paths.find_one({'points._id': {'$in': [ObjectId(p.strip()) for p in points.split(';')]}})
    if not path: abort(403)
    path['points'] = list(reversed(path['points']))
    path['_id'] = str(path['_id'])
    for p in path['points']:
        p['_id'] = str(p['_id'])
    return json(path)


@blu.route("/<hang>/@macro", methods=['GET', 'POST'])  # undone
@blu.route("/<hang>/@macro;@fastness=<fastness>", methods=['GET', 'POST'])  # undone
@privileges({'a', 'b', 'o'})
async def report(request, payload, hang, fastness='1'):
    """ add lots of things here then on client side generate then show calculate rate and show <- """
    fastness = int(fastness)
    ud = await config.paths.find(undone_query(hang)).to_list(None)
    return json({
        'hot': await config.paths.count_documents(hot_query(hang, 120 * 60 / fastness)),
        'undone': sum(len([point for point in path['points'] if 'volume' not in point and 'at' not in point]) for path in ud),
        'sum_staged': sum(len([point for point in path['points'] if 'volume' not in point]) for path in ud if path['porters']),
        'num_staged': len([path for path in ud if path['porters']]),
        'nack_undone': len([path for path in ud if not path['porters']]),
        'total': await config.paths.count_documents({'hang': hang}) +
                 await config.paths.count_documents({'hang': hang, 'points': {'$size': 4}})
    })


@blu.route("/<hang>/@micro", methods=['GET', 'POST'])  # undone
@blu.route("/<hang>/@micro;@fastness=<fastness>", methods=['GET', 'POST'])  # undone
@privileges({'a', 'b', 'o'})
async def report(request, payload, hang, fastness='1'):
    fastness = int(fastness)
    ud = await config.paths.find(undone_query(hang)).to_list(None)
    return json({
        'hot': await config.paths.count_documents(hot_query(hang, 120 * 60 / fastness)),
        'undone': sum(len([point for point in path['points'] if 'volume' not in point and 'at' not in point]) for path in ud),
        'nack_undone': len([path for path in ud if not path['porters']]),
        'total': sum(len(path['points']) for path in (await config.paths.find({'hang': hang}).to_list(None))) / 2
    })


@blu.route("/<hang>/@late=<late>;@limit=<seconds>", methods=['GET', 'POST'])  # undone
@blu.route("/<hang>/@limit=<seconds>;@late=<late>", methods=['GET', 'POST'])  # undone
@privileges({'a', 'b', 'o'})
async def _late(request, payload, hang, late, seconds):
    seconds, late = int(seconds), int(late)
    now = datetime.now() - timedelta(seconds=seconds)
    # paths = await config.paths.aggregate([
    # {
    #     'points': {
    #         '$elemMatch': {
    #             'at': {'$gt': now},
    #             'bound': {'$lte': late}
    #         }
    #     }
    # }, {
    #     '$project': {
    #         '_size': {
    #             '$size': {
    #                 '$filter': {
    #                     "input": "$points",
    #                     "as": "point",
    #                     "cond": {
    #                         '$and': [{
    #                             "$gt": ['$$point.at', now]
    #                         }, {
    #                             '$lte': ['$$point.bound', late]
    #                         }]
    #                     }
    #                 }
    #             }
    #         }
    #     }
    # }]).to_list(None)
    # n = sum(p['_size'] for p in paths)
    n = await config.paths.aggregate([{
        "$match": {
            'hang': hang,
            'points': {
                '$elemMatch': {
                    'at': {'$gt': now},
                    'bound': {'$lte': late}
                }
            }
        }
    }, {
        '$unwind': '$points'
    }, {
        '$match': {
            'points.at': {'$gt': now},
            'points.bound': {'$lte': late},
        }
    }, {
        '$group': {
            '_id': None,
            'count': {'$sum': 1}
        }
    }]).to_list(None)
    if not n:
        return json({'late': 0})
    return json({'late': n[0]['count']})


async def expected_frees(hang, porters=None):
    now = datetime.now()
    locations = await config.locations.aggregate([
        {
            '$match': {
                'hang': hang,
                'porter': {'$exists': True},
                **({'porter': {'$in': porters}} if porters else {}),
                '_date': {'$gt': now - timedelta(minutes=8)}
            }
        }, {
            '$sort': {'porter': 1, '_date': 1}
        }, {
            '$group': {
                '_id': "$porter",
                '_date': {'$last': "$_date"},
                'doc': {'$last': '$$ROOT'},
            }
        },
        # {
        #     '$addFields': {
        #         'distance': {
        #             '$ifNull': [{
        #                 '$add': [
        #                     {'$abs': {'$subtract': ['$doc.location.0', '$doc.destination.0']}},
        #                     {'$abs': {'$subtract': ['$doc.location.1', '$doc.destination.1']}}
        #                 ]
        #             }, 0]
        #         }
        #     }
        # }, {
        #     '$match': {
        #         'distance': {'$lt': 0.015}
        #     }
        # }
    ]).to_list(None)
    locations = [last['doc'] for last in locations]
    join = {}
    for l in locations:
        if 'points' in l:
            for p in l['points']:
                join[p['_id']] = l
    paths = await config.paths.find({
        'points._id': {'$in': list(join.keys())},
        '$or': [{
            'points.0.at': {'$exists': False},
            'points.1.at': {'$exists': True}
        }, {'points.0.at': {'$exists': True}}]
    }).to_list(None)
    for p in paths:
        loc = None
        for point in p['points']:
            if point['_id'] in join:
                loc = join[point['_id']]
                break
        if not loc:
            continue
        p_lat, p_lng = p['points'][0]['location']
        l_lat, l_lng = loc['location']
        loc['location'] = [p_lat, p_lng]
        loc['distance'] = abs(p_lat - l_lat) + abs(p_lng - l_lng)  # now just simple euclidean distance
        if 'head' in p['points'][0]:
            loc['head'] = p['points'][0]['head']
    return [l for l in locations if ('points' not in l or ('distance' in l and l['distance'] < 0.015)) and ('head' not in l or l['head'] <= now)]


async def frees(hang, porters=None):
    locations = await config.locations.aggregate([
        {
            '$match': {
                'hang': hang,
                'porter': {'$exists': True},
                # 'points': {'$exists': False},
                **({'porter': {'$in': porters}} if porters else {}),
                '_date': {'$gt': datetime.now() - timedelta(minutes=8)}
            }
        }, {
            '$sort': {'porter': 1, '_date': 1}
        }, {
            '$group': {
                '_id': "$porter",
                '_date': {'$last': "$_date"},
                'doc': {'$last': '$$ROOT'},
            }
        }, {
            '$match': {
                'doc.points': {'$exists': False}
            }
        }
    ]).to_list(None)
    return [last['doc'] for last in locations]


@blu.route('/<hang>/porters/@frees', methods=['POST'])
@privileges({'a', 'b', 'o'})
async def _frees(request, payload, hang):
    free_porters = await frees(hang)
    for porter in free_porters:
        del porter['_id']
    return json({'data': free_porters})


@blu.route('/<hang>/porters/@all', methods=['POST'])
@privileges({'a', 'b', 'o'})
async def _total(request, payload, hang):
    locations = await config.locations.aggregate([
        {
            '$match': {
                'hang': hang,
                'porter': {'$exists': True},
                # 'points': {'$exists': False},
                '_date': {'$gt': datetime.now() - timedelta(minutes=5)}
            }
        }, {
            '$sort': {'porter': 1, '_date': 1}
        }, {
            '$group': {
                '_id': "$porter",
                '_date': {'$last': "$_date"},
                'doc': {'$last': '$$ROOT'},
            }
        }
    ]).to_list(None)
    locations = [last['doc'] for last in locations]
    for doc in locations:
        del doc['_id']
        del doc['_date']
        if 'points' in doc:
            for p in doc['points']:
                p['_id'] = str(p['_id'])
    return json(locations)


@blu.route("/<hang>/<collection>", methods=['DELETE'])
@privileges({'a', 'b', 'o'})
async def delete_many(request, payload, hang, collection):
    return json(await getattr(config, collection).delete_many(literal_eval(
        request.form['q'][0] if 'q' in request.form else request.args['q'][0]
    )))


@blu.route("/<hang>/<collection>", methods=['GET'])
@privileges({'a', 'b', 'o'})
async def find_many(request, payload, hang, collection):
    return json(obj2str(await getattr(config, collection).find(exec(
        request.form['q'][0] if 'q' in request.form else request.args['q'][0]
    )).to_list(None)))


@blu.route("/<hang>/<collection>", methods=['POST'])
@privileges({'a', 'b', 'o'})
async def insert_many(request, payload, hang, collection):
    collection = collection.lower()
    method = collection[:-1] + 'ify'
    objects = getattr(tools, method)(request.form[collection][0]
                                     if collection in request.form
                                     else request.args[collection][0])
    print(objects)
    await getattr(config, collection).insert_many(objects)
    return json({'SUCCESS': True})

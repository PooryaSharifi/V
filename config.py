from motor.motor_asyncio import AsyncIOMotorClient
from sanic import Sanic
from sanic.response import text
import asyncio
import aiohttp
from multiprocessing import Value
from ctypes import c_bool, c_int
# from aiopipe import aiopipe
# from eta import model, feed
from aiofcm import FCM
import numpy as np
import pymongo
import os
from tools.mu import manager as mu
import urllib3
import logging
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

wrk = 3
app = Sanic(__name__)
app.config['RESPONSE_TIMEOUT'] = 600  # bad, very bad, too bad


lock, cnt, cnt_lock = Value(c_bool, False), Value(c_int, 0), Value(c_bool, False)
loop, fcm, session, locations, paths, users, contacts = None, None, None, None, None, None, None
grid = np.load(os.path.dirname(__file__) + '/tools/voronoi.npy')
listeners, etas = {}, {}

# mu = None
# star = [(aiopipe(), aiopipe()) for _ in range(wrk)]
# _server = nested(star)


@app.listener('before_server_start')
async def init(sanic, _loop):
    global session, locations, users, paths, contacts, fcm, loop
    loop = _loop
    fcm = FCM('197435492753', 'AAAALfgSiZE:APA91bHfj1dHgC_KR7ehPTQCrdXo10Js1vWiWwmcAhvMELNcb7_926MB6zHuyIJGO8PgNnkhVuZwNf9chdkgF2xkX3pY3Y9rmSTM6Fxcwpn6f5RySAYQpWGSxx_Pg1H996atVd0VJ9Hk')
    session = await aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)).__aenter__()
    db = AsyncIOMotorClient().express
    locations = AsyncIOMotorClient('mongodb://localhost:27020').express.locations
    locations.create_index([('location', '2d')])
    locations.create_index([('location', '2dsphere')])
    locations.create_index([('_date', 1)])
    locations.create_index([('hang', 1), ('user', 1), ('_date', 1)])
    users = db.users
    users.create_index([('user', pymongo.DESCENDING), ('hang', pymongo.DESCENDING)], unique=True)
    paths = db.paths
    paths.create_index([('hang', 1), ('porters.ack', 1)])
    paths.create_index([('hang', 1)], partialFilterExpression = {'porters': []})
    contacts = db.contacts
    contacts.create_index([('address', 'text')])
    contacts.create_index([('user', 1), ('hang', 1)])
    # model.load_weights('eta.h5py')
    while True:
        if not cnt_lock.value:
            global mu
            cnt_lock.value = True

            # rx, ty = star[cnt.value][0][0], star[cnt.value][1][1]
            # ty = ty.send()
            # mu = Client(await rx.open(loop), await ty.__enter__().open())

            # from client.simulator.v05 import sims_star
            # sims_rx, sims_ty = sims_star[cnt.value][0][0], sims_star[cnt.value][1][1]
            # sims = (await sims_rx.open(loop), await sims_ty.send().__enter__().open())

            cnt.value += 1
            cnt_lock.value = False
            break


@app.listener('before_server_start')
async def init_ones(sanic, loop):
    if not lock.value:
        lock.value = True
        _paths = await paths.find({
            'porters.ack': True
        }).sort([('_date', -1)]).to_list(10000)
        ps = {}
        for path in _paths:
            ps.clear()
            hang = path['hang']
            now = path['porters'][-1]['_date']
            for p in reversed(path['points']):
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
        # print(await mu(0, 'food', [35.747181515, 51.237893783]))

counter = [0]
@app.middleware('request')
async def track_requests(request):
    # Increase the value for each request
    counter[0] += 1


@app.listener('after_server_stop')
async def after_server_stop(sanic, loop):
    await session.__aexit__(None, None, None)
    # await client.bye()
    # await feed()
    print(counter[0])
    await asyncio.sleep(0)
    from tools.weather import weathers
    weathers.close()

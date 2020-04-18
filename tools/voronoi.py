from tools.maths import rnd, rectangle, grid_points, inside
from static import tehran
import aiohttp
import time
import asyncio
import uvloop
import math
from scipy.spatial import cKDTree
import numpy as np
import cv2
import config
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

n = time.time()


res = .005
teh_rec = rectangle(tehran)
# _bases = [rnd(tehran) for _ in range(3)]
# _bases = [[35.742913, 51.458071], [35.721913, 51.301383], [35.684991, 51.413950]]
_bases = [[35.6292, 51.47], [35.721913, 51.301383], [35.7832, 51.49]]
_extra_base = [sum(base[0] for base in _bases) / 3, sum(base[1] for base in _bases) / 3]
"""colors = [[255 / 255.0, 255 / 255.0, 255 / 255.0], [127 / 255.0, 255 / 255.0, 127 / 255.0], [255 / 255.0, 127 / 255.0, 127 / 255.0], [127 / 255.0, 127 / 255.0, 255 / 255.0]]

grid = grid_points(teh_rec, resolution=res)
_points = sum([[[p[0], p[1]] for p in row if inside(p[0], p[1], tehran)] for row in grid], [])
print(len(_points))
# _points = [[35.78370100000001, 51.49150000000001], [35.6291, 51.471]]
tree = cKDTree(_points)


async def vor(bases):
    session = await aiohttp.ClientSession().__aenter__()
    sources = ';'.join(str(i) for i in range(len(bases)))
    semi_bases = ';'.join(['{},{}'.format(location[1], location[0]) for location in bases])

    async def table(points):
        destinations = ';'.join(str(i) for i in range(len(bases), len(points) + len(bases)))
        points = ';'.join(['{},{}'.format(location[1], location[0]) for location in points])
        r = await session.get('http://localhost:6000/table/v1/driving/' + semi_bases + ';' + points, params={
            'sources': sources,
            'destinations': destinations
        })
        return (await r.json())['durations']

    _n = 100 - len(bases)
    functions = [table(_points[i * _n: i * _n + (_n if i < int(len(_points) / _n) else len(_points) % _n)]) for i in range(math.ceil(len(_points) / _n))]
    gather = []
    while functions:
        gather.extend(await asyncio.gather(*functions[:min(len(functions), 64)]))
        functions = functions[min(len(functions), 64):]
    # gather.extend(await asyncio.gather(*functions))
    await session.__aexit__(None, None, None)
    _vor = []
    for bulk in gather:
        bulk = zip(*bulk)
        for p in bulk:
            _vor.append(min(enumerate(p), key=lambda x: x[1])[0])
    return _vor

loop = asyncio.get_event_loop()
__vor = loop.run_until_complete(vor(_bases))
# print(__vor)

index = {(p[0], p[1]): __vor[i] for i, p in enumerate(_points)}
# for key, value in index.items():
#     print(key, value)

print(len(grid))
print(len(grid[0]))

for row in grid:
    for j, (lat, lng, _) in enumerate(row):
        if (lat, lng) not in index:
            row[j] = 0
        else:
            row[j] = index[(lat, lng)] + 1
        # # row[j] = colors[__vor[tree.query((lat, lng), k=1)[1]]]
        # row[j] = colors[0 if (lat, lng) not in index else index[(lat, lng)]]

grid = np.array(grid)

np.save('voronoi.npy', grid)"""
# grid = grid[::-1]


def territory(lat, lng):
    _territory = config.grid[min(round((lat - teh_rec[0][0]) / res), len(config.grid) - 1), min(round((lng - teh_rec[0][1]) / res), len(config.grid[0]) - 1)]
    return _bases[_territory - 1], _territory

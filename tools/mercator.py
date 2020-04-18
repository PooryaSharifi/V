import math
from PIL import Image
from io import BytesIO
from stem import Signal
from stem.control import Controller
import math
import requests
import aiohttp
import asyncio
from aiohttp_socks import SocksConnector, SocksVer
import time
from static import osm_dir
import numpy as np
from scipy.spatial import cKDTree
"""
h = roads only
m = standard roadmap
p = terrain
r = somehow altered roadmap
s = satellite only
t = terrain only
y = hybrid
lyrs=s@221097413
"""


def tile2lng(x, z):
    return x / 2 ** z * 360 - 180


def tile2lat(y, z):
    n = math.pi - 2 * math.pi * y / 2 ** z
    return 180 / math.pi * math.atan(0.5 * (math.exp(n) - math.exp(-n)))


def ll2p(lat, lng):
    siny = min(max(math.sin(lat * (math.pi / 180)), -.9999), .9999)
    return 128 + lng * (256 / 360), 128 + 0.5 * math.log((1 + siny) / (1 - siny)) * -(256 / (2 * math.pi))


def ll2t(lat, lng, z):
    t = 2 ** z
    s = 256 / t
    lat, lng = ll2p(lat, lng)
    return math.floor(lng / s), math.floor(lat / s)


def ll2px(lat, lng, z):
    t = 2 ** z
    s = 256 / t
    lat, lng = ll2p(lat, lng)
    (xp, x), (yp, y) = math.modf(lng / s), math.modf(lat / s)
    xp = min(math.floor(256 * xp), 255)
    yp = min(math.floor(256 * yp), 255)
    return (int(x), xp), (int(y), yp)


def new_session():
    with Controller.from_port(port=9051) as controller:
        controller.authenticate(password='your password set for tor controller port in torrc')
        controller.signal(Signal.NEWNYM)

    session = requests.session()
    session.proxies = {'http': 'socks5://127.0.0.1:9050',
                       'https': 'socks5://127.0.0.1:9050'}
    return session


def async_session():
    with Controller.from_port(port=9051) as controller:
        controller.authenticate(password='your password set for tor controller port in torrc')
        controller.signal(Signal.NEWNYM)

    connector = SocksConnector.from_url('socks5://127.0.0.1:9050')
    return asyncio.get_event_loop().run_until_complete(aiohttp.ClientSession(connector=connector).__aenter__()), connector


url_template = "http://mt1.google.com/vt?hl=en&lyrs=%s,traffic|seconds_into_week:%i&x=%i&y=%i&z=%i&style=15&s=Ga&hl=pl"
places = {
    'tehran': {
        'padding': 17,
        'zoom': 15,
        'center': [35.715015, 51.380076]
    }
}


async def big_picture(area, sessions, place=None, layer='s'):
    if not place:
        place = places[area]
    padding = place['padding']
    zoom = place['zoom']
    y, x = ll2t(*place['center'], zoom)
    images = []

    async def retrieve(_j, _i, session):
        response = await session.get(url_template % (layer, 3600 * 7, x + _i, y + _j, zoom))
        images[padding + _j][padding + _i] = Image.open(BytesIO(await response.read()))
        print(_i, _j)

    for j in range(-padding, padding + 1):
        images.append([])
        for i in range(-padding, padding + 1):
            images[-1].append(None)

    tasks = []
    for j in range(-padding, padding + 1):
        for i in range(-padding, padding + 1):
            tasks.append(retrieve(j, i, sessions[(j * (2 * padding + 1) + i) % len(sessions)][0]))
            if len(tasks) > len(sessions) - 1:
                await asyncio.gather(*tasks)
                tasks.clear()
    await asyncio.gather(*tasks)
    new_im = Image.new('RGB' + ('' if layer == 's' else 'A'), (256 * (padding * 2 + 1), 256 * (2 * padding + 1)))

    for j, row in enumerate(images):
        for i, im in enumerate(row):
            new_im.paste(im, (i * 256, 256 * j))

    return new_im


def indices(image, color, std):
    yellow = np.array(color)
    yellows = np.array([np.ones(image.shape[0: 2]) * yellow[0],
                        np.ones(image.shape[0: 2]) * yellow[1],
                        np.ones(image.shape[0: 2]) * yellow[2]])
    yellows = yellows.reshape(image.shape)
    yellows -= image
    yellows = np.square(yellows)
    yellows = np.sum(yellows, axis=2)
    yellows = np.power(yellows, .5)
    return np.argwhere(yellows < std)


def kd(name):
    image = Image.open(osm_dir + 'tehran.png')
    image = np.array(image)

    green = np.array([96.9, 214.7, 102])
    yellow = np.array([253.3, 149.7, 74.3])
    red = np.array([242, 58.3, 48.1])

    green_std = 15.14 / 1.5
    yellow_std = 5.45 * 1.1
    red_std = 8.78

    greens = indices(image, green, green_std)
    yellows = indices(image, yellow, yellow_std)
    reds = indices(image, red, red_std)
    return cKDTree(np.concatenate((greens, yellows, reds), axis=0)), len(greens), len(greens) + len(yellows)


def colors(ways, name, _kd=None):
    if not _kd:
        _kd = kd(name)
    tree, green_threshold, yellow_threshold = _kd
    xc, yc = ll2t(*places[name]['center'], places[name]['zoom'])
    xc -= places[name]['padding']
    yc -= places[name]['padding']

    all = 0
    m = 0
    for key, value in ways.items():
        if isinstance(key, tuple):
            n0, n1 = key
            (x, xp), (y, yp) = ll2px(*ways[n0], places[name]['zoom'])
            sx = (x - xc) * 256 + xp
            sy = (y - yc) * 256 + yp
            (x, xp), (y, yp) = ll2px(*ways[n1], places[name]['zoom'])
            tx = (x - xc) * 256 + xp
            ty = (y - yc) * 256 + yp
            all += 1
            d, idx = tree.query([sx, sy], k=1)
            if d < 5:
                value['color'] = 1 if idx < green_threshold else 2 if idx < yellow_threshold else 3
                continue
            d, idx = tree.query([tx, ty], k=1)
            if d < 5:
                value['color'] = 1 if idx < green_threshold else 2 if idx < yellow_threshold else 3
                continue
            d, idx = tree.query([int((sx + tx) / 2), int((sy + ty) / 2)], k=1)
            if d < 5:
                value['color'] = 1 if idx < green_threshold else 2 if idx < yellow_threshold else 3
                continue
            m += 1
            value['color'] = 0
    print(all, all - m)
    return ways


# n_image = image[x - 512: x + 512, y - 512: y + 512]
# n_image = Image.fromarray(np.uint8(n_image))
# n_image.save('colors.png')
# n_image.show(command='fim')

"""
s = satellite only
h = roads only
m = standard roadmap
p = terrain
r = somehow altered roadmap
t = terrain only
y = hybrid
lyrs=s@221097413
"""
if __name__ == 'main__':
    # import pickle
    # _kd = kd('tehran')
    # with open(osm_dir + 'tehran.colors' + '.pkl', 'wb') as f:
    #     pickle.dump(_kd, f, pickle.HIGHEST_PROTOCOL)
    pass

if __name__ == '__main__':
    sessions = [async_session() for _ in range(32)]

    async def job():
        picture = await big_picture('_', sessions, place={
            'padding': 5,
            'zoom': 15,
            'center': [35.715015, 51.380076]
        }, layer='h')
        # picture.save(_dir + '{}_{}-{}-{}_{}:00.png'.format(area, now.year, now.month, now.day, now.hour))
        picture.save('/home/poorya/' + '{}.png'.format('tehran_h'))
        for session, conn in sessions:
            await conn.close()
            await session.__aexit__(None, None, None)
    asyncio.get_event_loop().run_until_complete(job())

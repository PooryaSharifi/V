from multiprocessing.managers import BaseManager
from tools.mu.v02 import Mu as Core
import ujson as json
from datetime import datetime


class Mu:
    def __init__(self):
        self.hangs = {}

    def observe(self, value, _id, hang, location, date, type=2, **kwargs):
        if hang not in self.hangs:
            self.hangs[hang] = (Core(), Core(), Core(), [], {})
        self.hangs[hang][type].observe(_id, *location, value)
        if type == 2:
            kwargs['location'] = location
            kwargs['_date'] = date
            self.hangs[hang][4][_id] = kwargs

    def __call__(self, type, hang, location):
        if hang not in self.hangs:
            self.hangs[hang] = (Core(), Core(), Core(), [], {})
        return self.hangs[hang][type](location)

    def macro(self, hang, pop):
        if hang not in self.hangs:
            self.hangs[hang] = (Core(), Core(), Core(), [], {})
        return mu(self.hangs[hang][3], pop)

    def x(self, hang, location, pop):
        if hang not in self.hangs:
            self.hangs[hang] = (Core(), Core(), Core(), [], {})
        porters = [list(o.object[0:2]) for o in self.hangs[hang][2].knn(*location, k=7)]
        muses = [self.hangs[hang][i](*location) for i in range(3)]
        density = mu(self.hangs[hang][3], pop)
        return porters, muses, density

    def reverse(self, _id, hang):
        if hang not in self.hangs:
            self.hangs[hang] = (Core(), Core(), Core(), [], {})
        return self.hangs[hang][4].get(_id, None)

    # def territory(self, lat, lng):
    #     self.send(json.dumps({
    #         'voronoi': [lat, lng]
    #     }))
    #     return int(await self.recv())


def mu(l, pop=False):
    now = datetime.now()
    m = 0
    for time in l:
        m += (now - time).total_seconds()
    if pop:
        l.append(now)
        if len(l) > 40:
            l.pop(0)
    if m == 0 or not l:
        return 0
    return m / (now - l[0]).total_seconds() ** 2


BaseManager.register('Mu', Mu)
manager = BaseManager()
manager.start()
manager = manager.Mu()

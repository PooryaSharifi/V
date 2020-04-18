from rtree import index


class Mu:
    def __init__(self, n=2):
        self.idx = index.Index()
        self.n_distance = n
        self.ids = {}

    def observe(self, id, lat, lng, value=0):
        _id = hash(id)
        if id in self.ids:
            _lat, _lng = self.ids[id]
            self.idx.delete(_id, (_lat, _lng, _lat, _lng))
        else:
            self.ids[id] = (lat, lng)
        self.idx.insert(_id, (lat, lng, lat, lng), obj=(lat, lng, value))
        # add to pqdict
        # if max delete least lru

    def knn(self, lat, lng, k=1):
        return self.idx.nearest((lat, lng, lat, lng), min(k, len(self.ids)), objects=True)  # =>

    def __call__(self, lat, lng, k=5, value=False):
        points = list(self.idx.nearest((lat, lng, lat, lng), min(k, len(self.ids)), objects=True))
        s = 0
        if not points:
            return s
        for _value in points:
            _lat, _lng, _value = _value.object
            s += _value if _value else 1
        s /= ((lat - _lat) ** 2 + (lng - _lng) ** 2) ** .5
        return s

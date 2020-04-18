from random import random, randint
from bson import ObjectId
_e = {}


class Node:
    def __init__(self, lat, lng):
        self.location = [lat, lng]
        self.id = ObjectId()

    def w(self, u):
        if (self.id, u.id) not in _e:
            _e[(self.id, u.id)] = ((self.location[0] - u.location[0]) ** 2 + (self.location[1] - u.location[1]) ** 2) ** .5
        return _e[(self.id, u.id)]


if __name__ == '__main__':
    n = 100
    t = []
    E = {}
    for _ in range(n):
        t.append(Node(random() * 100, random() * 100))

    def s(tour):
        return sum([tour[index].w(tour[(index + 1) % len(tour)]) for index in range(len(tour))])

    n = 0

    def track(tour, stack, price, money):
        global n
        n += 1
        if n % 100 == 0:
            print(n)
        for i in range(0, len(tour)):
            tour[i:] = reversed(tour[i:])
            gain = price - s(tour)
            # track
            #
            if gain > 1:
                stack.append((i, gain))
                track(tour, stack, price - gain, money + gain)
                stack.pop()

            tour[i:] = reversed(tour[i:])
        return False


    print(n)
    track(t, [], s(t), 0)

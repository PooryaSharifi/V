from scipy.spatial import cKDTree
import random
import numpy as np
import math
from datetime import datetime
import time


class Mu:
    def __init__(self, n_distance):
        self.X = []
        self.W = {}
        self.tree = None
        self.n_distance = n_distance

    def distance(self, v, u):
        return (abs(v[0] - u[0]) ** self.n_distance + abs(v[1] - u[1]) ** self.n_distance) ** float(1 / self.n_distance)

    def extend(self, X):
        for x in X:
            (w, idx) = self.W.get(tuple(x), (0, len(self.W)))
            w += 1
            if idx == len(self.W):
                self.X.append(x)
            self.W[tuple(x)] = (w, idx)
            self.X[idx] = x
        self.tree = cKDTree(self.X)

    def query(self, x):
        dist, idx = self.tree.query(x, k=min(23, self.tree.n))
        s = 0
        for i in idx:
            s += self.W[tuple(self.X[i])][0]
        s /= self.distance(x, self.X[idx[-1]]) ** self.n_distance * math.pi
        return s

    def nearest(self, x):
        dist, idx = self.tree.query(x, k=12)
        return [tuple(self.X[i]) for i in idx]


def main():
    mu = Mu(2)
    n = 3
    X = np.random.random((n, 2))
    mu.extend(X)
    x = np.random.random((2))
    y = mu.query(x)
    return x, y


if __name__ == '__main__':
    print(main())

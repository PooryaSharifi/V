import numpy as np
from scipy.optimize import linear_sum_assignment
from random import random
import time

m = 200
inf = 1000

l = [(random(), random()) for _ in range(m)]
distance = lambda p, q: ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** .5

l = [[distance(l[i], l[j]) if i != j else inf for j in range(m)] for i in range(m - 2)]
# l = [[random() for _ in range(m)] for _ in range(m)]
# print(l)
cost = np.array(l)

n = time.time()
row_idx, col_idx = linear_sum_assignment(cost)
print('hungarian', cost[row_idx, col_idx].sum())
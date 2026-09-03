# -*- coding: utf-8 -*-
from __future__ import print_function
# 推导式与生成器表达式
print([x * x for x in range(6)])
print([x for x in range(20) if x % 3 == 0])
print([(x, y) for x in range(2) for y in range(2) if x != y])
print([[y for y in row] for row in ((1, 2), (3, 4))])
d = {'a': 1, 'b': 2}
print(sorted([k for k in d]))
try:
    print(sorted({k: v * 10 for k, v in d.items()}.items()))
    print(sorted({v for v in d.values()}))
    print(sorted({'%s=%s' % (k, v) for k, v in d.items()}))
except SyntaxError:
    print('no comp literals')
g = (x * 2 for x in range(4))
print(list(g))
print(sum(x * x for x in range(5)))
print(all(x > 0 for x in [1, 2]), any(x > 1 for x in [1, 2]))
pairs = [('a', 1), ('b', 2)]
print([k + str(v) for k, v in pairs])
print([x for x in [y * 2 for y in range(4)] if x > 2])
matrix = [[1, 2], [3, 4]]
flat = [v for row in matrix for v in row]
print(flat)
print(sorted([(v, k) for k, v in pairs]))

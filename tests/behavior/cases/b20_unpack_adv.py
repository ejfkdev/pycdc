# -*- coding: utf-8 -*-
from __future__ import print_function
# 解包进阶：链式赋值、多重 del、下标/属性增量、for 目标解包、
# zip/字典遍历、返回多值、嵌套生成器解包

a = b = c = [1]
a.append(2)
print(a, b, c, a is b)

pairs = [(1, 'a'), (2, 'b'), (3, 'c')]
for k, v in pairs:
    print(k, v)

for (x, (y, z)) in [(1, (2, 3)), (4, (5, 6))]:
    print(x + y + z)

def multi():
    return 1, [2, 3], {'k': 4}

m, (n, o), p = multi()
print(m, n, o, sorted(p.items()))

d = {}
d['x'] = 0
d['x'] += 5
d['y'] = d['x'] * 2
print(sorted(d.items()))

class Box(object):
    def __init__(self):
        self.n = 0
        self.items = []

box = Box()
box.n += 3
box.items.append(box.n)
box.items.extend([1, 2])
print(box.n, box.items)

del box.items[0]
print(box.items)

t = [1, 2, 3, 4]
del t[1:3]
print(t)

u, v = 1, 2
u, v = v, u + v
print(u, v)

w = [0]
q = w
w = w + [1]
print(w, q)

r = [0]
s = r
r += [1]
print(r, s, r is s)

first, rest = pairs[0], pairs[1:]
print(first, rest)

gen = ((i, i * i) for i in range(3))
g1, g2, g3 = gen
print(g1, g2, g3)

kv = dict((k, v) for k, v in [('a', 1), ('b', 2)])
print(sorted(kv.items()))

for i, (key, val) in enumerate(sorted(kv.items())):
    print(i, key, val)

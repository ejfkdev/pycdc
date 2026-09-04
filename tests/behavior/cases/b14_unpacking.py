# -*- coding: utf-8 -*-
from __future__ import print_function
# 解包：嵌套、循环、交换、函数返回、dict 项
a, (b, c) = 1, (2, 3)
print(a, b, c)

(d, e), f = ([4, 5], 6)
print(d, e, f)

x, y = 10, 20
x, y = y, x
print(x, y)

def pair():
    return 1, 2

p, q = pair()
print(p, q)

for i, (j, k) in enumerate([(1, 2), (3, 4)]):
    print(i, j, k)

t = ((1, 2), (3, 4))
for (m, n) in t:
    print(m + n)

lst = [1, 2, 3]
g, h, i2 = lst
print(g, h, i2)

s1 = 'ab'
c1, c2 = s1
print(c1, c2)

dd = {'k1': 1, 'k2': 2}
for key, val in sorted(dd.items()):
    print(key, val)

def multi():
    return [1, (2, 3), {'z': 26}]

u1, (u2, u3), u4 = multi()
print(u1, u2, u3, sorted(u4.items()))

a = b = c = 0
a = b = 7
print(a, b, c)

n1, n2 = [[1], [2]]
print(n1, n2)

def kwtarget(**kw):
    (ka, va), (kb, vb) = sorted(kw.items())
    return ka, va, kb, vb

print(kwtarget(apple=1, banana=2))

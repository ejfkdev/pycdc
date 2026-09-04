# -*- coding: utf-8 -*-
from __future__ import print_function
# 切片、下标、删除
l = list(range(10))
print(l[2:5], l[:3], l[7:], l[::3], l[::-1], l[-3:])
l2 = l[:]
l2[0] = -1
print(l[0], l2[0])
m = [1, 2, 3, 4, 5]
m[1:3] = [9]
print(m)
del m[0]
print(m)
t = (1, [2, 3], {'k': 'v'})
print(t[0], t[1][1], t[2]['k'])
d = {'a': 1}
d['b'] = d.get('a', 0) + 1
print(sorted(d.items()), d.get('z', 'miss'), 'a' in d)
del d['a']
print(sorted(d.items()))
class Sub(object):
    def __init__(self):
        self.data = list(range(5))
    def __getitem__(self, i):
        return ('get', i)
    def __setitem__(self, i, v):
        self.data.append((i, v))
    def __delitem__(self, i):
        self.data.append(('del', i))
s = Sub()
print(s[2])
s[1] = 'x'
del s[0]
print(s.data)
n1, n2 = 10, 3
print(n1 // n2, n1 % n2, divmod(n1, n2))
mat = [[1, 2], [3, 4]]
print(mat[1][0], [row[1] for row in mat])

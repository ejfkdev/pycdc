# -*- coding: utf-8 -*-
from __future__ import print_function
# 运算符优先级/求值序/增强赋值：全用打印揭示语义
print(-2 ** 2, (-2) ** 2, -(2 ** 2))
print(2 ** 3 ** 2)
print(not 1 == 2, (not 1) == 2)
print(1 + 2 * 3 - 4 // 2 % 3)
print(-7 // 2, -7 % 2, 7 // -2, 7 % -2)
print(5 & 3 | 8 ^ 2, 1 << 3 >> 1)
print(True + True, False * 5, True == 1, False is not None)
print('a' * 3 + 'b', (1, 2) + (3,), [1] * 2)
print(1 < 2 == 2 >= 1 != 3)

calls = []
def side(name, val):
    calls.append(name)
    return val

r = side('a', 1) < side('b', 2) < side('c', 3)
print(r, calls)

calls2 = []
r2 = side('x', True) and side('y', False) and side('z', True)
print(r2, calls2)

calls3 = []
r3 = side('p', '') or side('q', 0) or side('r', 'hit')
print(r3, calls3)

d = {'k': 1}
d['k'] += 5
d['j'] = d.get('k', 0) * 2
print(sorted(d.items()))

l = [1, 2, 3]
l[1] *= 3
l[-1] -= 1
l += [9]
print(l)

class Acc(object):
    def __init__(self):
        self.v = 1
    def bump(self, n):
        self.v += n
        return self

o = Acc()
o.bump(2).bump(3)
print(o.v)
o.v //= 2
print(o.v)

s = 'hello'
t = s
s += '!'
print(s, t)

m = [1, 2]
n = m
m = m + [3]
n += [4]
print(m, n)

print(complex(1, 2) + complex(0, -1), abs(complex(3, 4)))
print(divmod(17, 5), pow(2, 10), pow(2, 10, 100))
print(round(2.675, 2), int('42'), float('1.5e2'))
print(max([1, 5, 3]), min(4, 2, 9), sum([1, 2], 10))
print((1, 2) == (1, 2), [1] < [2], 'abc' < 'abd')
print(~5, -(-5), +('3' and 3))
print(0.1 + 0.2 == 0.3, abs(0.1 + 0.2 - 0.3) < 1e-9)
print(1 if None else 2, 'y' if [] else 'n', (1, 2)[True])
a = 5
a ^= 3
a <<= 1
a >>= 2
print(a)
print('end-ops')

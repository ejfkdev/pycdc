# -*- coding: utf-8 -*-
from __future__ import print_function
# 基础表达式与数据类型
print(1 + 2 * 3 - 4 // 2, 7 % 3, 2 ** 10, -5 // 2, abs(-3))
print(7 / 2 if True else 0)
s = 'hello'
print(s + ' ' + 'world', s * 2, len(s), s.upper(), s[1:3], s[-2:])
t = (1, 2, 3)
l = [1, 2, 3]
d = {'a': 1, 'b': 2}
print(t[0], t[-1], len(t), l[1:], d['a'], sorted(d.keys()))
a, b = 1, 2
a, b = b, a
print(a, b)
x = y = z = 0
x += 5
x -= 1
x *= 2
x //= 3
print(x, y, z)
print(1 < 2 < 3, 3 > 2 > 1, 1 == 1.0, 1 is 1, 'a' in 'abc', 5 not in [1, 2])
print(True and False, True or False, not True, bool(''), bool([0]))
n = None
print(n is None, n is not None)
big = 12345678901234567890
print(big + 1)
print(3.14, 1e10, complex(1, 2))
print((1, 2) == (1, 2), [1] != [2], frozenset([1, 2]) == frozenset([2, 1]))

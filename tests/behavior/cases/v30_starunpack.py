# -*- coding: utf-8 -*-
# MIN_VERSION: 3.0
# 星号解包与显示
a, *b = [1, 2, 3, 4]
print(a, b)

*c, d = range(4)
print(c, d)

e, *f, g = 'abcdef'
print(e, f, g)

h, *i3 = [1]
print(h, i3)

def head_tail(seq):
    head, *tail = seq
    return head, tail

print(head_tail([1, 2, 3]), head_tail([9]))

lst = [1, 2]
combined = [0, *lst, 3]
print(combined)

tup = (1, *lst)
print(tup)

def varargs(*args):
    return sum(args)

print(varargs(*lst, *lst))

pairs = [(1, 2), (3, 4)]
for x, y in pairs:
    print(x * y)

nested = [[1, [2, 3]], [4]]
(n1, n2), n3 = nested
print(n1, n2, n3)

*init, last = iter([1, 2, 3])
print(init, last)

def kw(a, b, c):
    return a * 100 + b * 10 + c

vals = [1, 2, 3]
print(kw(*vals))

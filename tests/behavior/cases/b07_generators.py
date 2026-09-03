# -*- coding: utf-8 -*-
from __future__ import print_function
# 生成器：yield、send、嵌套、close、finally（next() 需要 2.6+）
def gen(n):
    i = 0
    while i < n:
        yield i
        i += 1

print(list(gen(4)))

def acc():
    total = 0
    while True:
        v = yield total
        if v is None:
            break
        total += v

a = acc()
next(a)
print(a.send(5))
print(a.send(7))
a.close()

def tree(items):
    for it in items:
        if isinstance(it, list):
            for sub in tree(it):
                yield sub
        else:
            yield it

print(list(tree([1, [2, [3, 4]], 5])))

def limited():
    yield 1
    yield 2

print([x for x in limited()])

g2 = gen(100)
print(next(g2))
first = []
for v in g2:
    first.append(v)
    if len(first) == 3:
        break
print(first)

def with_finally():
    try:
        yield 'a'
        yield 'b'
    finally:
        print('gen finally')

gf = with_finally()
print(next(gf))
gf.close()

def delegating():
    for v in gen(2):
        yield v * 10

print(list(delegating()))

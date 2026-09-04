# -*- coding: utf-8 -*-
# MIN_VERSION: 3.5
# 字典/集合解包与合并
a = {'x': 1}
b = {'y': 2}
merged = {**a, **b}
print(sorted(merged.items()))

override = {**a, 'x': 9, **{'z': 3}}
print(sorted(override.items()))

def show(**kw):
    return sorted(kw.items())

print(show(**a, **b))
print(show(**a, extra=1))

u = [*a, *b]
print(sorted(u))

s = {*[1, 2], *[2, 3]}
print(sorted(s))

def pos(a, b, *rest, **kw):
    return (a, b, rest, sorted(kw.items()))

args = [1, 2, 3]
print(pos(*args, **b))

c = {'deep': {'k': 1}}
d2 = {**c['deep'], 'j': 2}
print(sorted(d2.items()))

empty = {**{}}
print(empty)

chain = {**a}
chain.update(b)
print(sorted(chain.items()), sorted({**a, **b}.items()))

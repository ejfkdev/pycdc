# -*- coding: utf-8 -*-
# MIN_VERSION: 3.0
# keyword-only 参数与调用形态
def f(a, *, b=2, c=3):
    return (a, b, c)

print(f(1), f(1, c=30), f(1, b=20, c=30))

def g(*args, key=None, **kw):
    return (args, key, sorted(kw.items()))

print(g(1, 2, key='K'), g(1, key='K2', z=9))

def h(a, b=1, *args, key, **kw):
    return (a, b, args, key, sorted(kw.items()))

print(h(0, key='only'), h(0, 1, 2, 3, key='k', extra='e'))

def many(*, p=1, q=2, r=3):
    return p + q + r

print(many(), many(q=20), many(p=100, q=200, r=300))

def call_kw(**kw):
    return f(1, **kw)

print(call_kw(b=8, c=9))

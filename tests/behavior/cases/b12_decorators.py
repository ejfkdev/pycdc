# -*- coding: utf-8 -*-
from __future__ import print_function
import functools
# 装饰器：函数/带参/叠加/类装饰
def deco(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        print('before', fn.__name__)
        r = fn(*a, **k)
        print('after', fn.__name__)
        return r
    return wrapper

@deco
def target(x):
    return x + 1

print(target(1))

def times(n):
    def wrap(fn):
        def inner(*a):
            return fn(*a) * n
        return inner
    return wrap

@times(3)
def val(x):
    return x

print(val(2))

def d1(fn):
    def w(*a):
        return 'd1(' + fn(*a) + ')'
    return w

def d2(fn):
    def w(*a):
        return 'd2(' + fn(*a) + ')'
    return w

@d1
@d2
def base():
    return 'core'

print(base())

def class_deco(cls):
    cls.marked = True
    return cls

@class_deco
class Marked(object):
    pass

print(Marked().marked, Marked.marked)

class as_deco(object):
    def __init__(self, fn):
        self.fn = fn
    def __call__(self, *a):
        return 'cls-deco:' + str(self.fn(*a))

@as_deco
def plain(x):
    return x

print(plain(5))

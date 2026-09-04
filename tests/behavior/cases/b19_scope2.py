# -*- coding: utf-8 -*-
from __future__ import print_function
# 作用域进阶：嵌套闭包修改、类/方法作用域、函数属性、
# property/classmethod/staticmethod、super、getattr 家族

counter = 0

def bump():
    global counter
    counter += 1
    return counter

print([bump(), bump(), counter])

def outer():
    val = [0]
    def mid():
        def inner():
            val[0] += 1
            return val[0]
        return inner, val
    f, cell = mid()
    a = f()
    b = f()
    return a, b, cell[0]

print(outer())

def defaults_capture():
    fns = []
    for i in range(3):
        def cap(j=i):
            return j * 10
        fns.append(cap)
    return [g() for g in fns]

print(defaults_capture())

def func_attrs():
    def f():
        f.calls += 1
        return f.calls
    f.calls = 0
    return [f(), f(), f.calls]

print(func_attrs())

class Base(object):
    kind = 'base'

    def __init__(self, v):
        self.v = v

    def describe(self):
        return '%s:%s' % (self.kind, self.v)

    @property
    def doubled(self):
        return self.v * 2

    @classmethod
    def make(cls, v):
        return cls(v + 1)

    @staticmethod
    def helper(x):
        return x * 100

class Child(Base):
    kind = 'child'

    def __init__(self, v, extra):
        super(Child, self).__init__(v)
        self.extra = extra

    def describe(self):
        return Base.describe(self) + '+' + str(self.extra)

c = Child(5, 'e')
print(c.describe())
print(c.doubled)
print(Base.make(5).describe())
print(Base.helper(2))

class Attrs(object):
    def __init__(self):
        self.a = 1
        self._b = 2

o = Attrs()
print(getattr(o, 'a'), hasattr(o, '_b'), getattr(o, 'zz', 'dflt'))
setattr(o, 'a', 10)
delattr(o, '_b')
print(o.a, hasattr(o, '_b'))

def shadow_builtin():
    list_ = [1, 2]
    def inner():
        return len(list_)
    return inner()

print(shadow_builtin())

def late_bound_default(x=[]):
    x.append(1)
    return len(x)

print([late_bound_default(), late_bound_default()])

def nested_scopes():
    x = 'outer'
    def f():
        x = 'f'
        def g():
            return x
        return g()
    return f(), x

print(nested_scopes())

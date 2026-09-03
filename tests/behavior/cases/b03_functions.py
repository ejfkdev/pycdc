# -*- coding: utf-8 -*-
from __future__ import print_function
# 函数：默认参数、*args/**kwargs、lambda、闭包、递归、global
def f(a, b=2, *args, **kw):
    return (a, b, args, sorted(kw.items()))

print(f(1))
print(f(1, 20, 30, 40, z=1, y=2))

def outer(x):
    def inner(y):
        return x + y
    return inner

print(outer(10)(5))

def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

print([fib(i) for i in range(10)])

sq = lambda v: v * v
add = lambda a, b=100: a + b
print(sq(7), add(1), add(1, 2))

counter = 0
def bump():
    global counter
    counter += 1
    return counter

print(bump(), bump(), counter)

def docfn():
    """Docstring here."""
    return docfn.__doc__

print(docfn())

def defaults_mutable(x, acc=[]):
    acc.append(x)
    return acc

print(defaults_mutable(1), defaults_mutable(2))

def varargs_only(*args):
    return sum(args)

print(varargs_only(1, 2, 3), varargs_only())

def kw_only(**kw):
    return len(kw)

print(kw_only(a=1, b=2, c=3))

def call_it(fn, *a, **k):
    return fn(*a, **k)

print(call_it(f, 9, 8, q=7))

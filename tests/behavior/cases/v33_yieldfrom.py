# -*- coding: utf-8 -*-
# MIN_VERSION: 3.3
# yield from / nonlocal / raise from
def sub():
    yield 1
    yield 2

def main():
    yield 0
    yield from sub()
    yield 3

print(list(main()))

def counter():
    n = 0
    def inc():
        nonlocal n
        n += 1
        return n
    return inc, lambda: n

inc, get = counter()
print(inc(), inc(), get())

class E(Exception):
    pass

try:
    try:
        raise ValueError('inner')
    except ValueError as ve:
        raise E('outer') from ve
except E as e:
    print(type(e).__cause__ is not None, e.__cause__.args)

def delegating_gen():
    g = sub()
    v = yield from g
    print('returned', v)

dg = delegating_gen()
print(list(dg))

def with_return():
    yield from sub()
    return 'ret'

wg = with_return()
print(list(wg))

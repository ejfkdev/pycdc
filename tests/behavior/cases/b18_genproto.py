# -*- coding: utf-8 -*-
from __future__ import print_function
# 生成器协议深水区：yield 于 try/finally/except、throw、close 时机、
# 手动委托、genexp 位置、send 序列

def fin_gen():
    log = []
    def g():
        try:
            yield 1
            log.append('past1')
            yield 2
        finally:
            log.append('fin')
    it = g()
    log.append(next(it))
    log.append(next(it))
    try:
        next(it)
    except StopIteration:
        log.append('stop')
    return log

print(fin_gen())

def throw_gen():
    log = []
    def g():
        while True:
            try:
                v = yield 'ready'
                log.append(('got', v))
            except ValueError as e:
                log.append(('caught', str(e)))
                yield 'recovered'
    it = g()
    log.append(next(it))
    log.append(it.send(1))
    try:
        it.throw(ValueError, 'boom')
    except StopIteration:
        log.append('stopped')
    return log

print(throw_gen())

def close_gen():
    log = []
    def g():
        try:
            yield 1
            yield 2
        finally:
            log.append('closed')
    it = g()
    log.append(next(it))
    it.close()
    log.append('after-close')
    try:
        next(it)
        log.append('resumed?!')
    except StopIteration:
        log.append('dead')
    return log

print(close_gen())

def manual_delegate():
    def inner(n):
        for i in range(n):
            yield i * i
    def outer(n):
        total = 0
        for v in inner(n):
            total += v
            yield total
    return list(outer(4))

print(manual_delegate())

print(sum(x * 2 for x in range(5)))
print([c for c in 'abc' if c != 'b'])
print(list(map(lambda t: t[0] + t[1], zip([1, 2], [10, 20]))))

def gen_in_call():
    def f(*args):
        return [list(a) for a in args]
    return f((x for x in range(3)))

print(gen_in_call())

def bidir():
    def g():
        x = yield 'init'
        y = yield x + 1
        yield (x, y)
    it = g()
    out = [next(it), it.send(10), it.send(20)]
    try:
        next(it)
    except StopIteration:
        out.append('done')
    return out

print(bidir())

def nested_finally():
    log = []
    def g():
        try:
            try:
                yield 'in'
            finally:
                log.append('inner-fin')
        finally:
            log.append('outer-fin')
    it = g()
    log.append(next(it))
    it.close()
    return log

print(nested_finally())

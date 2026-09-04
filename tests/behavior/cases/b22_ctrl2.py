# -*- coding: utf-8 -*-
from __future__ import print_function
# 控制流进阶：while/for-else 组合、elif 链、三元链、短路副作用、
# 循环内 try-else-continue/break 交叉

def while_else_break(n):
    out = []
    i = 0
    while i < n:
        i += 1
        if i == 3:
            out.append('brk')
            break
        out.append(i)
    else:
        out.append('else')
    return out

print(while_else_break(5))
print(while_else_break(2))

def for_else_cont(seq):
    out = []
    for x in seq:
        if x % 2:
            out.append('skip')
            continue
        out.append(x)
    else:
        out.append('no-break')
    return out

print(for_else_cont([1, 2, 3, 4]))

def elif_chain(v):
    if v < 0:
        r = 'neg'
    elif v == 0:
        r = 'zero'
    elif v < 10:
        r = 'small'
    elif v < 100:
        if v % 7 == 0:
            r = 'seven-ish'
        else:
            r = 'mid'
    else:
        r = 'big'
    return r

print([elif_chain(x) for x in (-1, 0, 5, 14, 20, 1000)])

def ternaries(v):
    a = 'pos' if v > 0 else 'nonpos'
    b = ('even' if v % 2 == 0 else 'odd') if v else 'zero'
    c = v if v < 5 else (10 if v < 20 else 30)
    return (a, b, c)

print([ternaries(x) for x in (0, 3, 8, 25)])

def short_circuit():
    log = []
    def t(name, val):
        log.append(name)
        return val
    r1 = t('a', False) and t('b', True)
    r2 = t('c', True) or t('d', False)
    r3 = t('e', 1) and t('f', 2)
    r4 = t('g', 0) or t('h', 3)
    return r1, r2, r3, r4, log

print(short_circuit())

def loop_try_mix(seq):
    out = []
    for x in seq:
        try:
            if x == 2:
                raise ValueError(x)
            out.append(('ok', x))
        except ValueError:
            out.append(('err', x))
            if x == 2:
                continue
        else:
            out.append(('else', x))
        finally:
            out.append(('fin', x))
        out.append(('post', x))
    return out

print(loop_try_mix([1, 2, 3]))

def nested_loops_break():
    out = []
    for i in range(3):
        for j in range(3):
            if i + j > 2:
                out.append('x')
                break
            out.append((i, j))
        else:
            out.append('inner-else')
    return out

print(nested_loops_break())

def deep_nest(a, b, c):
    if a:
        if b:
            if c:
                return 'abc'
            return 'ab'
        elif c:
            return 'ac'
        return 'a'
    elif b:
        return 'b'
    return 'none'

print([deep_nest(*t) for t in ((1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0), (0, 1, 0), (0, 0, 0))])

i = 0
while True:
    i += 1
    if i >= 3:
        break
print('while-true', i)

for k in range(10):
    if k == 2:
        continue
    if k == 4:
        break
print('for-broke-at', k)

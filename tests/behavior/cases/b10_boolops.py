# -*- coding: utf-8 -*-
from __future__ import print_function
# 布尔逻辑与短路（含副作用验证）
log = []
def t(name, val):
    log.append(name)
    return val

if t('a', True) and t('b', False):
    print('both')
elif t('c', True) or t('d', False):
    print('or branch')
print(''.join(log))

log = []
x = t('p', False) or t('q', 'Q') or t('r', 'R')
print(x, ''.join(log))

log = []
y = t('m', 'M') and t('n', 'N') and t('o', 0)
print(y, ''.join(log))

def check(a, b, c):
    if a or b or c:
        return 'any'
    return 'none'

print(check(0, 0, 0), check(0, 1, 0), check(1, 0, 0))

def check2(a, b):
    if not a and not b:
        return 'neither'
    return 'some'

print(check2(0, 0), check2(1, 0), check2(0, 1))

def check3(a, b):
    if a and not b:
        return 'only-a'
    return 'other'

print(check3(1, 0), check3(1, 1), check3(0, 0))

v = None
print(v or 'default', v if v is not None else 'fallback')
print(bool([] or [1]), bool({} and 1), not not 5)
while_val = 3
while not (while_val <= 0):
    while_val -= 1
    if while_val == 1 and not (while_val > 5 or while_val < 0):
        print('inner cond at', while_val)
print('done', while_val)
print((1 == 1) != (2 == 3), (1 < 2) == True)

# nested if/else inside an if without else — py2.6 peek-jump chain fold
# must NOT merge this into `if a and b: X else: Y` (regression: the
# merged else fires when the outer condition is false)
def nest(a, b, log):
    if a:
        if b:
            log.append('both')
        else:
            log.append('a-only')
    log.append('end')
    return log

print(nest(1, 1, []), nest(1, 0, []), nest(0, 0, []))

def nest_raise(x, fallback):
    if x is None:
        if fallback is not None:
            x = fallback
        else:
            raise ValueError('missing')
    return x

print(nest_raise('given', None), nest_raise(None, 'fb'))
try:
    nest_raise(None, None)
except ValueError:
    print('VE')

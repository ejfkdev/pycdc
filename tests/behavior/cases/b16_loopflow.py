# -*- coding: utf-8 -*-
from __future__ import print_function
# 循环控制流：嵌套 break/continue、while-else、for-else、return 出循环
def nested_break():
    out = []
    for i in range(3):
        for j in range(3):
            if j == 2:
                break
            if i == 1 and j == 1:
                out.append('skip')
                continue
            out.append((i, j))
        if i == 2:
            break
    return out

print(nested_break())

def while_else_break():
    n = 0
    while n < 10:
        n += 1
        if n == 3:
            break
    else:
        return 'else-ran'
    return 'broke-at-%d' % n

print(while_else_break())

def while_else_normal():
    n = 3
    while n > 0:
        n -= 1
    else:
        return 'else-ran-%d' % n
    return 'broke'

print(while_else_normal())

def for_else_ret():
    for i in range(3):
        if i == 2:
            return 'ret-in-loop'
    else:
        return 'for-else'

print(for_else_ret())

def for_else_pass():
    out = []
    for i in range(2):
        out.append(i)
    else:
        out.append('else')
    return out

print(for_else_pass())

def ret_from_nested():
    for i in range(2):
        for j in range(2):
            if i == j == 1:
                return (i, j)
    return None

print(ret_from_nested())

def cont_outer():
    out = []
    for i in range(3):
        if i == 1:
            continue
        for j in range(2):
            if j == 0 and i == 2:
                continue
            out.append((i, j))
    return out

print(cont_outer())

def while_nested_cont():
    out = []
    i = 0
    while i < 3:
        i += 1
        j = 0
        while j < 3:
            j += 1
            if j == i:
                continue
            if j > i:
                break
            out.append((i, j))
    return out

print(while_nested_cont())

def loop_over_iters():
    out = []
    for a, b in zip([1, 2, 3], 'abc'):
        out.append((a, b))
    for i, v in enumerate(['x', 'y'], 1):
        out.append((i, v))
    for v in reversed([1, 2]):
        out.append(v)
    for v in sorted([3, 1, 2], reverse=True):
        out.append(v)
    return out

print(loop_over_iters())

def break_in_else_of_loop():
    out = []
    for i in range(2):
        out.append(i)
    else:
        n = 0
        while True:
            n += 1
            if n > 2:
                break
            out.append('w%d' % n)
    return out

print(break_in_else_of_loop())

def two_loops_same_fn():
    out = []
    for i in range(2):
        out.append(('a', i))
    for j in range(2):
        if j == 1:
            break
        out.append(('b', j))
    else:
        out.append('b-else')
    return out

print(two_loops_same_fn())

# backward cond-jump to loop top with the loop's real back edge AFTER a
# terminating block: 3.8/3.9 compile `if not x: raise` at the loop tail
# as PJIT-to-top (continue-equivalent) + raise + dead JABS. Misread as a
# rotated-while back edge, the loop closes early and the raise hoists
# out (chunk.skip family).
def tail_raise(items):
    out = []
    i = 0
    while i < len(items):
        dummy = items[i]
        i = i + 1
        if not dummy:
            raise ValueError('zero')
        out.append(dummy)
    return out

print(tail_raise([1, 2, 3]))
try:
    tail_raise([1, 0, 3])
except ValueError:
    print('VE')

def mid_continue(n):
    out = []
    i = 0
    while i < n:
        i = i + 1
        if i % 2 == 0:
            continue
        out.append(i)
    return out

print(mid_continue(6))

# 3.12 for-else + and-chain break: the compiler turns `if a and b: break`
# into guard links (PJIT next / JUMP_BACKWARD continue) and the break
# becomes POP_TOP + JUMP_FORWARD over the else to the merge - a merge
# the else body's own guards also target. The registration must accept
# those in-region sources or the break is lost (loop always exhausts).
def for_else_break(source, symbol):
    for line in source.split('\n'):
        line = line.strip()
        if line and line[0] != '#':
            break
    else:
        if symbol != 'eval':
            source = 'pass'
    return source.upper()

print(for_else_break('a\nb', 'x'), for_else_break('#c\n', 'exec'), for_else_break('#c\n', 'eval'))

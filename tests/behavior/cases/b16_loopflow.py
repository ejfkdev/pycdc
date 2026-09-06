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

# 3.11+ `while True: if A: ...; if x: break; ...; else: ...` + loop-level
# tail statement: the break jump flies over the enclosing branch's whole
# remainder to the loop exit - it must not (a) close the enclosing if
# (degenerate-break close must stop at the break's own block) nor
# (b) mark the branch's else_end at the loop exit (which stretched the
# else over the loop tail). (_compression.read family.)
def comp_read(items, limit):
    out = []
    data = None
    while True:
        if items:
            data = items.pop(0)
            if data > limit:
                break
            out.append(('head', data))
        else:
            out.append(('empty',))
            break
        if data:
            out.append(('tail', data))
            if len(out) > 6:
                break
    return out

print(comp_read([1, 2, 30, 4], 10))
print(comp_read([], 10))
print(comp_read([5, 6], 10))

# or-continue chain: 3.10+ threads `if a or b: continue` onto the loop
# back edge (PJIT operand1 -> back-edge/top, PJIF operand2 -> body).
# Mis-merged polarity (not A or B) or a lost continue re-runs the body
# for skipped elements (_pylong.compute_powers family).
def or_continue(vals, seen):
    out = []
    for w in vals:
        if w in seen or w <= 0:
            continue
        out.append(w)
    return out

def or_continue_while(n):
    out = []
    i = 0
    while i < n:
        i += 1
        if i % 2 == 0 or i % 3 == 0:
            continue
        out.append(i)
    return out

print(or_continue([1, -2, 3, 0, 5, 3], set([3, 5])))
print(or_continue_while(12))

# while with a two-operand And condition: both links exit to the loop
# exit. 3.8+ folds via split_cond; SETUP_LOOP-era (2.7-3.7) needs the
# While-cond And-merge arm (the second link is NOT a rotated-while
# duplicate - its operand run differs). Mis-handling nests the second
# operand as an inner if and can infinite-loop (bdb family).
def while_and(frame, stopframe, out):
    i = 0
    while frame is not stopframe and frame is not None:
        out.append(i)
        i += 1
        if i > 3:
            frame = None
    return out

def while_and_call(s):
    end = s.find(';')
    while end > 0 and (s.count('"', 0, end) - s.count('x', 0, end)) % 2:
        end = s.find(';', end + 1)
    return end

print(while_and(1, 2, []), while_and(2, 2, []))
print(while_and_call('a;b'), while_and_call('x"x;x'))

def for_and_not_break(items):
    # `if A and not B: break`：混合极性链全部跳循环顶，不得并成
    # `if A or B: break`（极性反转，copyreg._reduce_ex 教训）
    out = []
    for it in items:
        out.append(it)
        if it % 2 == 0 and not it < 0:
            break
    else:
        out.append('else')
    return out

print(for_and_not_break([-3, 2, 4]))
print(for_and_not_break([-3, -5]))
print(for_and_not_break([3, 2]))

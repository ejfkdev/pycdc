# -*- coding: utf-8 -*-
from __future__ import print_function
# try/finally 控制流交叉：return-break-continue 与 finally 的交互
def ret_in_try():
    try:
        return 'try-ret'
    finally:
        print('fin1')

print(ret_in_try())

def ret_in_finally():
    try:
        return 'try-ret'
    finally:
        return 'fin-ret'

print(ret_in_finally())

def ret_both_nested():
    try:
        try:
            return 'inner'
        finally:
            print('inner-fin')
    finally:
        print('outer-fin')

print(ret_both_nested())

def break_in_try(seq):
    out = []
    for v in seq:
        try:
            if v == 2:
                break
            out.append(v)
        finally:
            out.append('f%d' % v)
    out.append('after')
    return out

print(break_in_try([1, 2, 3]))

def cont_in_except(seq):
    out = []
    for v in seq:
        try:
            if v % 2 == 0:
                raise ValueError(v)
            out.append(v)
        except ValueError:
            out.append('skip%d' % v)
            continue
        out.append('ok%d' % v)
    return out

print(cont_in_except([1, 2, 3, 4]))

def else_runs():
    out = []
    try:
        out.append('body')
    except ValueError:
        out.append('handler')
    else:
        out.append('else')
    finally:
        out.append('finally')
    return out

print(else_runs())

def else_skipped():
    out = []
    try:
        raise KeyError('k')
    except KeyError:
        out.append('handler')
    else:
        out.append('else')
    finally:
        out.append('finally')
    return out

print(else_skipped())

def reraise_bare():
    try:
        try:
            raise IndexError('ix')
        except IndexError:
            raise
    except IndexError as e:
        return 'caught %s' % e

print(reraise_bare())

def raise_in_except():
    try:
        raise ValueError('v1')
    except ValueError:
        raise TypeError('t1')

try:
    raise_in_except()
except TypeError as e:
    print('chained:', e)

def finally_loop():
    out = []
    for i in range(2):
        try:
            out.append(i)
        finally:
            out.append('f')
    return out

print(finally_loop())

def exc_in_finally():
    try:
        raise ValueError('orig')
    finally:
        print('fin-runs')

try:
    exc_in_finally()
except ValueError as e:
    print('propagated:', e)

def nested_handlers():
    out = []
    try:
        try:
            try:
                raise ValueError('deep')
            except TypeError:
                out.append('wrong1')
        except ValueError:
            out.append('mid')
            raise
    except ValueError:
        out.append('outer')
    return out

print(nested_handlers())

def while_try_break():
    out = []
    n = 0
    while n < 5:
        n += 1
        try:
            if n == 3:
                break
            out.append(n)
        finally:
            out.append(-n)
    out.append('end%d' % n)
    return out

print(while_try_break())

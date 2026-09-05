# -*- coding: utf-8 -*-
from __future__ import print_function
# 异常：try/except/else/finally、多 handler、as、raise、自定义异常、嵌套
class MyError(Exception):
    def __init__(self, code):
        Exception.__init__(self, 'my error %s' % code)
        self.code = code


class SubError(MyError):
    pass


def t1():
    try:
        raise MyError(7)
    except SubError:
        return 'sub'
    except MyError as e:
        return 'my %s' % e.code
    except Exception:
        return 'generic'

def t2():
    try:
        x = 1
    except ValueError:
        return 'err'
    else:
        return 'else'
    finally:
        pass

def t3():
    log = []
    try:
        try:
            raise KeyError('k')
        except KeyError:
            log.append('inner')
            raise ValueError('v')
    except ValueError:
        log.append('outer')
    finally:
        log.append('finally')
    return log

def t4():
    try:
        return 'try-return'
    finally:
        pass

def t5():
    log = []
    try:
        log.append('body')
        raise IndexError()
    except IndexError:
        log.append('handler')
    else:
        log.append('not-run')
    return log

def t6():
    try:
        {}['x']
    except (KeyError, IndexError) as e:
        return type(e).__name__
    return 'none'

def t7():
    try:
        int('x')
    except ValueError:
        try:
            int('y')
        except ValueError:
            return 'nested-handled'
    return 'no'

def t8():
    for i in range(3):
        try:
            if i == 1:
                raise RuntimeError(i)
        except RuntimeError:
            continue
        else:
            pass
    return 'loop-done'

def bare_raise():
    try:
        raise TypeError('t')
    except TypeError:
        try:
            raise
        except TypeError as e2:
            return 're-raised %s' % e2

print(t1(), t2(), t3(), t4(), t5(), t6(), t7(), t8(), bare_raise())

try:
    raise SubError(1)
except MyError as e:
    print('caught as parent:', e.code)

# assert with negated test: PJIF over a fall-through raise block
# (mirror polarity of the canonical PJIT assert shape)
def assert_not(x):
    assert not x
    assert not x, 'neg-msg'
    return 'ok'

print(assert_not(False))
try:
    assert_not(True)
except AssertionError:
    print('AE')

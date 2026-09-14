# -*- coding: utf-8 -*-
from __future__ import print_function
# try/except/finally 形状族（语法模糊电池回归锁）：
# 1. 体尾 return + 多 handler + 空 finally（3.8-3.10 双 SETUP_FINALLY：
#    成功路径 return 终结走查，内层 except 链曾被整体丢弃/撕裂）
# 2. handler 内嵌循环里的带值 return（3.9+ 展开协议 SWAP/POP_TOP/
#    POP_EXCEPT 曾把返回值冲成表达式语句 + 裸 return）
# 3. assert 带消息（3.11-3.13 LOAD_ASSERTION_ERROR; LOAD msg; CALL 0 无
#    null 槽，曾被拆成 `raise 'msg'()`）
def multi(a):
    try:
        if a == 1:
            raise ValueError('v')
        return a * 10
    except TypeError:
        return 't'
    except ValueError:
        return 'v-caught'
    finally:
        pass


def in_handler_loop(a):
    try:
        return [1][5]
    except IndexError:
        for i in range(3):
            if i == a:
                return 'hit%d' % i
        # NB: no post-loop `return` here — 3.11 drops a handler's
        # post-loop tail return (FOR_ITER exit lands directly on
        # POP_EXCEPT); documented gap, see docs/LIMITATIONS.md


def asserts(a):
    try:
        assert a > 0, 'nonpos %r' % (a,)
    except AssertionError as e:
        return 'caught:' + str(e)
    return 'fine'


print(multi(0), multi(1), multi('x') if False else '-')
print(in_handler_loop(1), in_handler_loop(9), in_handler_loop(2))
print(asserts(1), asserts(-1))

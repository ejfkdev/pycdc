# -*- coding: utf-8 -*-
# MIN_VERSION: 3.11
# match/case 无-dup 单一类模式：当 match 只有一个非通配 case（后跟 case _）
# 时，CPython 省略 subject 的 COPY 1，直接 LOAD cls; LOAD_CONST names;
# MATCH_CLASS 消费 subject。此时主循环已把 cls/names 压栈，需在 MATCH_CLASS
# 分发点回收 cls 并把 subject 留在栈顶（pending_match_class）。
# 3.10 的旧式逐属性提取（BINARY_SUBSCR+ROT）仍是已知缺口，故门到 3.11。

class Point:
    __match_args__ = ('x', 'y')

    def __init__(self, x, y):
        self.x = x
        self.y = y


def zero_arg(v):
    match v:
        case str():
            return 'is-str'
        case _:
            return 'other'


def cap_lit(p):
    match p:
        case Point(x, 5):
            return ('x-is', x)
        case _:
            return 'no'


def all_cap(p):
    match p:
        case Point(a, b):
            return ('pt', a, b)
        case _:
            return 'no'


def lit_cap(p):
    match p:
        case Point(0, y):
            return ('y-axis', y)
        case _:
            return 'no'


def kw_pat(p):
    match p:
        case Point(x=1, y=2):
            return 'kw-12'
        case _:
            return 'no'


def guarded(p):
    match p:
        case Point(a, b) if a == b:
            return ('diag', a)
        case _:
            return 'no'


def in_loop(items):
    # match inside a for-loop: case bodies do NOT return (they append), so
    # each body ends with JUMP_BACKWARD to the loop top, and the trailing
    # `case _:` wildcard sits at the class pattern's fail target. This is the
    # shape that needs parse_match_case_body's JUMP_BACKWARD terminator and
    # the popped-cleanup wildcard detection.
    out = []
    for it in items:
        match it:
            case Point(a, b):
                out.append(('pt', a, b))
            case _:
                out.append(('raw', it))
    return out


def in_loop_single(items):
    # no-dup single class pattern inside a loop + wildcard fallthrough
    out = []
    for it in items:
        match it:
            case str():
                out.append(it.upper())
            case _:
                out.append(it)
    return out


print(zero_arg('hi'), zero_arg(3))
print(cap_lit(Point(1, 5)), cap_lit(Point(2, 3)))
print(all_cap(Point(7, 8)), all_cap('x'))
print(lit_cap(Point(0, 9)), lit_cap(Point(1, 9)))
print(kw_pat(Point(1, 2)), kw_pat(Point(3, 4)))
print(guarded(Point(4, 4)), guarded(Point(1, 2)))
print(in_loop([Point(1, 2), 'x', Point(0, 0), 5]))
print(in_loop_single(['ab', 3, 'c']))


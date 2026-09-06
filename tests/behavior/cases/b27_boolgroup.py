# -*- coding: utf-8 -*-
from __future__ import print_function
import sys
# 分组 boolop 形状回归用例（本项目语义反转回归高发区）。
# 本用例只固化【当前各版本已正确】的形状，任何误折、丢操作数或
# DeMorgan 反转都会改变真值表输出：
#   (a or b) and c      —— shape-A 共享出口（2.7+）
#   not a or b + 嵌套    —— configparser _validate 反转形（折叠 not 的
#                          PJIF 直达 body，嵌套守卫不得被吞为链操作数）
#   (a and b) or c      —— 3.5-3.13 语句级 strict-first 合并
#                          （or_cond 曾误折成 `if not a or not b: if c:`）
#   `while a or b:`     —— 3.5-3.7 多跳旋转条件曾退化成
#                          `while True: if a or b:`（条件假时运行期死循环）
#   循环内 `A or B: 末语句`（全版本）—— <3.8 融合 skip+continue；
#     3.8-3.11 fused 合并；3.12+ or-join（双操作数同极性跳 body +
#     假路径 continue 蹦床在 body 之前）
#   循环内 `A or (B and C)`（3.5-3.11）—— fused try_or_and_chain
#   DNF `(A1 and A2) or (B1 and B2)`（2.7+）—— try_or_group_chain
#     （codecs StreamReader.read 形；or_cond 曾折成
#      `not A1 or not A2: if B1 and B2:` 反转）
#   值位 `a and b or c`（仅 <3.14）—— try_and_or_value_chain
#   链式比较 `a <= b < c`（全版本）—— SCC body_end 曾越过 skip 标签
#     把下一条语句的 JF 当 body 末端，链被否决、body 甩出守卫
#
# 已知缺口（各自独立 bug，另行处理，勿在本用例覆盖）：
#   * 2.6 DNF `(A1 and A2) or (B1 and B2)`（py2 值保留链）折成
#     `if A1: if A2 or (B1 and B2):`。
#   * 2.6 语句级 `(a and b) or c`（py2 JUMP_IF_* 值保留链）。
#   * 2.6 `(a or b) and c` / `not a or b` 嵌套分组错（同族值保留链）。
#   * 2.6 值位 `a and b or c` 分组错（同族）。
#   * 3.12+ 循环内 or 家族（TO_BOOL/COPY 新布局）：`if flag or x>1:`
#     DeMorgan 反转成 `if not flag and not x>1:`；`A or (B and C)` 反转。
#   * 3.8+ 退化形 `if A or B: continue`（循环末语句、无后继）仍折成
#     `if not A: if B: pass`（语义等价的 no-op，仅不保真）。
#   * 3.14 值位 boolop 重新分组：`a and b or c` 折成 `a and (b or c)`；
#     3.14 语句级 (a and b) or c 同样反转。
# 版本门控刻意用「先算 0/1 变量 + 单比较 if」的防呆形状——门控自身
# 若用链式/and-or 比较会被上述缺口吃掉，导致各版本行数错位。

V = sys.version_info

NOT26 = 0
if (2, 7) <= V:
    NOT26 = 1
GE35 = 0
if (3, 5) <= V:
    GE35 = 1
LT38 = 0
if V < (3, 8):
    LT38 = 1
LT312 = 0
if V < (3, 12):
    LT312 = 1
LT314 = 0
if V < (3, 14):
    LT314 = 1
VAL27_313 = NOT26 * LT314
B35_37 = GE35 * LT38
B35_313 = GE35 * LT314

def g_or_and(a, b, c):
    if (a or b) and c:
        return 1
    return 0

def g_not_or(a, b, c):
    if not a or b:
        if not c:
            return 'inner'
        return 'outer'
    return 'none'

def g_dnf(data, suffix):
    out = []
    if (isinstance(data, str) and data.endswith(suffix)) or \
       (isinstance(data, bytes) and data.endswith(suffix)):
        out.append(1)
    return out

def g_loop_and_or(items, flag, lim):
    out = []
    for x in items:
        if flag is None or (x > 0 and x < lim):
            out.append(x)
    return out

def g_chain(V, x):
    out = []
    if (3, 5) <= V[:2] < (3, 14):
        out.append(1)
    if 0 < x < 10:
        out.append(2)
    return out

def g_while_or(a, b):
    n = 0
    while a or b:
        n += 1
        a = 0
        b = 0
    return n

def g_and_or(a, b, c):
    if (a and b) or c:
        return 1
    return 0

def g_val(a, b, c):
    return a and b or c

def g_loop_or(items, flag):
    out = []
    for x in items:
        if flag or x > 1:
            out.append(x)
    return out

if NOT26:
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                print(g_or_and(a, b, c), g_not_or(a, b, c))

if B35_313:
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                print(g_and_or(a, b, c))

if B35_37:
    print(g_while_or(1, 0), g_while_or(0, 0))

if VAL27_313:
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                print(g_val(a, b, c))

print(g_loop_or([0, 1, 2, 3], 0))
print(g_loop_or([0, 1, 2, 3], 1))

B35_311 = GE35 * LT312
if B35_311:
    print(g_loop_and_or([0, 1, 2, 3], None, 3))
    print(g_loop_and_or([0, 1, 2, 3], 0, 3))

print(g_chain((3, 6), 5), g_chain((3, 16), 5), g_chain((2, 6), 50))

if NOT26:
    print(g_dnf('ar', 'r'), g_dnf('x', 'r'), g_dnf(b'rb', b'r'), g_dnf(b'q', b'r'))

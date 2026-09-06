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
#   循环内 `A or B: 末语句`（仅 <3.8）—— 融合 skip+continue
#   值位 `a and b or c`（仅 <3.14）—— try_and_or_value_chain
#
# 已知缺口（各自独立 bug，另行处理，勿在本用例覆盖）：
#   * `(a and b) or (c and d)`（codecs StreamReader.read 形，全版本）：
#     or_cond 把右侧两个 and 操作数误折成 `not a or not b: if c and d:`。
#   * 2.6 语句级 `(a and b) or c`（py2 JUMP_IF_* 值保留链）。
#   * 2.6 `(a or b) and c` / `not a or b` 嵌套分组错（同族值保留链）。
#   * 2.6 值位 `a and b or c` 分组错（同族）。
#   * 3.8+ 循环内 or 家族：3.8/3.9 `if flag or x>1:` 反转成
#     `if not flag: if x>1:`；3.10+ `flag is None or (B and C)` 丢 body；
#     3.12+ 循环内简单 or 丢 body。
#   * 3.14 值位 boolop 重新分组：`a and b or c` 折成 `a and (b or c)`；
#     3.14 语句级 (a and b) or c 同样反转。
#   * 3.10+ 链式比较 if（`(3,5) <= V[:2] < (3,14)`）的 body 被甩出守卫
#     （条件折成 `if A: if B: pass` + body 无条件执行）。
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

if LT38:
    print(g_loop_or([0, 1, 2, 3], 0))
    print(g_loop_or([0, 1, 2, 3], 1))

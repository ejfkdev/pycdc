# -*- coding: utf-8 -*-
from __future__ import print_function
# 推导式形状族（语法模糊电池回归锁）：
# 1. 元素三元（else 臂 UNARY_NEGATIVE 曾被推导式 walk 静默忽略 → `else x`）
# 2. py2 双层内联推导式（内层 BUILD_LIST 前的 CALL 曾让 has_build_prologue
#    误判成同推导式的第二个 for 子句 → 嵌套被扁平化）
# 3. genexpr 否定过滤器（3.12+ PJIF-前跳至 emit 块 / py2.6 JUMP_IF_TRUE
#    前跳至 POP_TOP+JABS 跳板，两种极性翻转形状都曾丢失 not）
# 4. lambda 元素的 3.12+ 内联推导式（MAKE_CELL 前导 + 闭包 MAKE_FUNCTION）
cond = [x if x % 2 else -x for x in range(6)]
nest = [[i * j for j in range(3)] for i in range(3)]
keys = ['_a', 'b', '_c', 'd']
pos = sorted(k for k in keys if k.startswith('_'))
neg = sorted(k for k in keys if not k.startswith('_'))
lat = [f() for f in [(lambda: i) for i in range(3)]]
tot = sum(v for v in [1, 2, 3] if not v % 2)
print(cond, nest, pos, neg, lat, tot)

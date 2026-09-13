# -*- coding: utf-8 -*-
from __future__ import print_function
# finally 族形状（全版本）：
# 1. 嵌套空 finally + return（3.11+ 清理路径 SWAP/POP 舞步会撕裂成
#    [Expr(X), Return(None)] + 兄弟 Return(X)，需重折叠；<=3.10 空
#    finalbody 渲染为 try/finally: pass 而非平铺占位）。
# 2. finally 吞没式 return（`finally: return -9`）：异常路径也返回 -9。
#    <=3.10 判别：return 材料位于 SETUP_FINALLY 清理区 END_FINALLY 之前
#    → 属于 finally 体；控制组 fin_then_return 的真尾随 return 在
#    END_FINALLY 之后，必须保持不折叠。
def nested(a):
    try:
        try:
            return a[0]
        finally:
            pass
    finally:
        pass


def swallow(a):
    try:
        x = a[0]
    finally:
        return -9


def fin_then_return(a):
    try:
        x = a[0]
    finally:
        pass
    return x


def fin_stmt_then_return(a):
    try:
        x = a[0]
    finally:
        x = x + 1
    return x


print(nested([5]), nested([]) if False else '-')
print(swallow([1]), swallow(None), swallow('ab'))
print(fin_then_return([7]), fin_stmt_then_return([8]))

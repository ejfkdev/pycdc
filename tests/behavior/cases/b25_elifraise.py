# -*- coding: utf-8 -*-
from __future__ import print_function
# elif 链还原 + raise 后死回边 + 异常匹配 pattern（chunk/binhex/base64 族）。
# 2.6: elif 识别要求 starts_with_cond_jump 认 peek 跳 JUMP_IF_*；
# raise 后紧跟的死 JUMP_ABSOLUTE（2.6 未优化编译器产物）不得渲染成
# continue；DUP_TOP 异常值占位必须认属性/元组 pattern
# （except mod.E / except (A, B)），否则 COMPARE_OP 下溢标 incomplete。

class Seeker:
    def __init__(self):
        self.size_read = 0
        self.chunksize = 100

    def seek(self, pos, whence):
        if whence == 1:
            pos = pos + self.size_read
        elif whence == 2:
            pos = pos + self.chunksize
        if pos < 0 or pos > self.chunksize:
            raise RuntimeError('bad pos')
        return pos

s = Seeker()
print(s.seek(5, 0))
print(s.seek(5, 1))
print(s.seek(0, 2))
try:
    s.seek(-1, 0)
except RuntimeError:
    print('runtime-error')

def skip_loop(items):
    # 循环体尾 if 以 raise 结束：死回边不得成为 continue
    total = 0
    i = 0
    while i < len(items):
        it = items[i]
        i = i + 1
        if not it:
            raise ValueError('empty item')
        total = total + it
    return total

print(skip_loop([1, 2, 3]))
try:
    skip_loop([1, 0, 3])
except ValueError:
    print('value-error')

def for_raise(rows):
    out = []
    for r in rows:
        if not r:
            raise TypeError('bad row')
        out.append(len(r))
    return out

print(for_raise(['ab', 'c']))
try:
    for_raise(['ab', ''])
except TypeError:
    print('type-error')

def patterns():
    # 属性 pattern（decimal.InvalidOperation）与元组 pattern
    # （(ValueError, TypeError)）都要正确挂到对应 except 子句
    import decimal
    out = []
    funcs = [
        lambda: 1 / 0,
        lambda: int('x'),
        lambda: decimal.Decimal('x'),
        lambda: None,
    ]
    for f in funcs:
        try:
            f()
            out.append('ok')
        except (ValueError, TypeError) as e:
            out.append('tuple:' + type(e).__name__)
        except ZeroDivisionError:
            out.append('zero')
        except decimal.InvalidOperation:
            out.append('attr-pattern')
    return out

print(patterns())

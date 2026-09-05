# -*- coding: utf-8 -*-
# 空生成器惯用形：`while False: yield None`（_collections_abc Iterable.__iter__
# 等）被编译器死代码消除、只剩生成器标志——反编译必须合成回不可达 yield，
# 否则生成器函数退化为普通函数（iter()/isinstance GeneratorType 破坏）。
# 另覆盖：if 分支内以 raise 收尾的 except handler（3.10+ 无 POP_EXCEPT/
# RERAISE 尾随，链须在 RAISE_VARARGS 处就地折叠，否则整个函数体被吞）。

import types


class It:
    def __iter__(self):
        while False:
            yield None


def empty_gen():
    while False:
        yield None


def maybe(x, log):
    if isinstance(x, str):
        log.append('then')
        try:
            log.append(x)
        except:
            log.append('exc')
            raise
    else:
        log.append('else')
    return log


def boom(x):
    try:
        int(x)
    except ValueError:
        x = 'handled'
        raise
    return 'no'


print(isinstance(empty_gen(), types.GeneratorType))
print(list(It()))
print(list(empty_gen()))
print(maybe('a', []))
print(maybe(3, []))
try:
    boom('z')
except ValueError:
    print('re-raised ok')
print(boom('5'))

# -*- coding: utf-8 -*-
# MIN_VERSION: 3.14
# PEP 649 模块/类级注解还原：注解存于编译器生成的 __annotate__ 函数
# （类体为 __annotate_func__），模块级条目被 `if IDX in
# __conditional_annotations__` 门控，门控 SET_ADD 泄漏的 `{IDX}` 语句
# 是原始位置标记。比较 FORWARDREF 格式——VALUE 格式会触发对未导入名字
# （TYPE_CHECKING 惯用法）的求值。
import sys
import annotationlib

x: int = 1
y: str


class K:
    a: int = 5
    b: str

    def m(self, u: int) -> str:
        return str(u)


def f(p: int, q: str = 'x') -> bool:
    return True


FMT = annotationlib.Format.STRING
mod = sys.modules[__name__]
print(x, 'y' in dir())
print(sorted(annotationlib.get_annotations(mod, format=FMT).items()))
print(sorted(annotationlib.get_annotations(K, format=FMT).items()))
print(sorted(annotationlib.get_annotations(K.m, format=FMT).items()))
print(sorted(annotationlib.get_annotations(f, format=FMT).items()))

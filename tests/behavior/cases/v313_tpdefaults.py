# -*- coding: utf-8 -*-
# MIN_VERSION: 3.13
# PEP 696 类型参数默认值（`T = d`）：CALL_INTRINSIC_2
# SET_TYPEPARAM_DEFAULT + 惰性求值函数（3.14 带 .format 守卫）。
type Lazy[T = int] = list[T]


def with_default[T = str](x: T = None) -> T:
    return x


class Def[T = bytes, *Ts = *tuple[()]](list):
    pass


print(Lazy.__name__, Lazy[str].__name__)
print(with_default(), with_default(3))
print([p.__name__ for p in Def.__type_params__])
print(with_default.__type_params__[0].has_default())

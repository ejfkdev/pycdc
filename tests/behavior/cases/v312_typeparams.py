# -*- coding: utf-8 -*-
# MIN_VERSION: 3.12
# PEP 695 类型参数语法：type 别名（含泛型参数）、泛型函数（TypeVar/
# bound/constraints/TypeVarTuple/ParamSpec）、泛型类。编译器形态：
# `<generic parameters of X>` 包装函数 + CALL_INTRINSIC_1/2
# (TYPEVAR/PARAMSPEC/TYPEVARTUPLE/TYPEVAR_WITH_BOUND/
# TYPEVAR_WITH_CONSTRAINTS/SET_TYPEPARAM_DEFAULT/TYPEALIAS/
# SUBSCRIPT_GENERIC/SET_FUNCTION_TYPE_PARAMS)。
type IntPair = tuple[int, int]
type Pair[T] = tuple[T, T]


def first[T](p: Pair[T]) -> T:
    return p[0]


def bounded[T: int](x: T) -> T:
    return x


def constrained[T: (int, str)](x: T) -> T:
    return x


def variadic[T, *Ts, **P](x: T) -> T:
    return x


class Box[T](list):
    def head(self) -> T:
        return self[0]

    def mapped[U](self, f):
        return [f(v) for v in self]


b = Box([3, 1, 2])
print(first((1, 2)), first(('a', 'b')))
print(bounded(7), constrained('s'))
print(variadic(5), b.head(), sorted(b))
print(b.mapped(str), IntPair.__name__, Pair[str].__name__)
print(Box.__type_params__, first.__type_params__)

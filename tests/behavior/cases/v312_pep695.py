# -*- coding: utf-8 -*-
# MIN_VERSION: 3.12
# PEP 695：type 别名、泛型函数、泛型类、TypeVarTuple 风格使用

type IntList = list[int]
type Pair[T] = tuple[T, T]

def first[T](items: list[T]) -> T:
    return items[0]

def pair_up[T](a: T, b: T) -> tuple[T, T]:
    return (a, b)

class Stack[T]:
    def __init__(self, *init: T):
        self._items: list[T] = list(init)

    def push(self, x: T) -> None:
        self._items.append(x)

    def pop(self) -> T:
        return self._items.pop()

    def __len__(self) -> int:
        return len(self._items)

    def top(self) -> T:
        return self._items[-1]

print(first([1, 2, 3]))
print(first(['a', 'b']))
print(pair_up(1, 2))

s = Stack[int](1, 2)
s.push(3)
print(s.pop(), s.top(), len(s))

def mapped[T, U](items: list[T], fn) -> list[U]:
    return [fn(x) for x in items]

print(mapped([1, 2, 3], lambda x: x * 10))

class Boxed[T]:
    def __init__(self, v: T):
        self.v = v

    def map(self, fn) -> 'Boxed':
        return Boxed(fn(self.v))

print(Boxed(5).map(lambda x: x + 1).v)

type Nested = dict[str, IntList]
n: Nested = {'a': [1, 2]}
print(sorted(n.items()))

class Wrapper[T](Stack[T]):
    def peek2(self) -> list[T]:
        return self._items[-2:]

w = Wrapper('a', 'b', 'c')
print(w.peek2(), len(w))

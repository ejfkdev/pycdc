# -*- coding: utf-8 -*-
# MIN_VERSION: 3.8
# positional-only 参数
def mixed(a, /, b, *, c):
    return (a, b, c)

print(mixed(1, 2, c=3))

def all_pos(x, y, /):
    return x - y

print(all_pos(5, 3))

def pos_default(a, b=2, /, c=3):
    return (a, b, c)

print(pos_default(1), pos_default(1, 20), pos_default(1, c=30))

def pos_varargs(a, /, *rest):
    return (a, rest)

print(pos_varargs(1, 2, 3))

class C:
    def m(self, x, /, y):
        return x + y

print(C().m(1, 2))

def forward(f2, /):
    return f2(1, 2)

print(forward(all_pos))

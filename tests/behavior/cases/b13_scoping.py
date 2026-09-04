# -*- coding: utf-8 -*-
from __future__ import print_function
# 作用域与闭包：晚绑定、共享 cell、默认参捕获、推导式作用域、del、嵌套 global
def make_fns():
    fns = []
    for i in range(3):
        fns.append(lambda: i)
    return fns

print([f() for f in make_fns()])

def make_fns_fixed():
    return [lambda i=i: i for i in range(3)]

print([f() for f in make_fns_fixed()])

def share():
    def get():
        return box[0]
    def put(v):
        box[0] = v
    box = [0]
    put(7)
    return get(), box[0]

print(share())

def outer():
    n = [1]
    def mid():
        def inner():
            n[0] += 1
            return n[0]
        return inner(), n[0]
    return mid(), n[0]

print(outer())

gv = 'module'
def read_g():
    return gv

def write_g():
    global gv
    gv = 'written'
    return gv

print(read_g(), write_g(), read_g(), gv)

x = 'outer-x'
leaked = [x for x in range(3)]
print('leak:', x, leaked)

def deleter():
    v = 5
    del v
    try:
        return v
    except UnboundLocalError:
        return 'unbound'

print(deleter())

def scope_chain():
    a = 1
    def f1():
        b = a + 1
        def f2():
            c = b + 1
            return a, b, c
        return f2()
    return f1()

print(scope_chain())

def shadow(a, b):
    def inner(a):
        return a * 100 + b
    return inner(1), a, b

print(shadow(2, 3))

funcs = {}
for k in ('p', 'q'):
    def mk(k=k):
        return k
    funcs[k] = mk()
print(sorted(funcs.items()))

def cond_close(flag):
    v = 'yes' if flag else 'no'
    def use():
        return v
    return use()

print(cond_close(True), cond_close(False))

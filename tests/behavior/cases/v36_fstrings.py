# -*- coding: utf-8 -*-
# MIN_VERSION: 3.6
# f-string：转换符、格式规格、嵌套、多行
name = 'world'
n = 42
print(f'hello {name}!')
print(f'{n} {n!r} {n!s}')
print(f'{n:>6}|{n:<6}|{n:06d}|{n:x}')
print(f'{3.14159:.2f} {1000000:,}')
print(f'{name.upper()} mixed {n + 8}')
d = {'k': 'v'}
print(f"{d['k']} {len(d)}")
items = [1, 2]
print(f"{items[0]}-{items[-1]}")
print(f"braces {{literal}}")
print(f'{"inner"} outer {f"{1+1}"}')
w = 8
print(f'{name:>{w}}|')
print(f'{n=}' if False else f'n={n}')
def f(x):
    return f'f({x})'
print(f(f(n)))

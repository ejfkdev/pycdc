# -*- coding: utf-8 -*-
# MIN_VERSION: 3.12
# PEP 701 f-string 高级形态
name = 'world'
vals = [1, 2, 3]
d = {'a': 1}

print(f'{name!r} {name!s}')
print(f'{vals[0]} {vals[-1]} {len(vals)}')
print(f'{d["a"]} {d.get("a", 0)}')
print(f'{'inner'}')
print(f'{name.upper()} {name.replace("w", "W")}')
print(f'{3.14159:.2f} {42:>6} {7:03d} {-5:+d}')
print(f'{1000000:,} {0.5:%} {255:x} {8:o} {5:b}')
print(f'{name=}')
print(f'''triple {name}''')
print(f'{sum(x*x for x in vals)}')
print(f'{[x for x in vals if x > 1]}')
print(f'brace {{literal}} end')
print(f'{vals!r:>{10}}')

def build(parts):
    return f'<{",".join(str(p) for p in parts)}>'

print(build(vals))

nested = {'k': {'k2': [9]}}
print(f'{nested["k"]["k2"][0]}')

flag = True
print(f'{"yes" if flag else "no"} {"a" if not flag else "b"}')

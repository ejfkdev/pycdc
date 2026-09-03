# -*- coding: utf-8 -*-
# MIN_VERSION: 3.8
# 海象运算符、positional-only 参数
data = [1, 2, 3, 4, 5]
if (total := sum(data)) > 10:
    print('total', total)

while (chunk := data.pop(0) if data else None) is not None:
    print('chunk', chunk)

results = [y := 0]
for i in range(3):
    results.append(y := y + i)
print(results)

def posonly(a, b, /, c, *, d=4):
    return (a, b, c, d)

print(posonly(1, 2, 3), posonly(1, 2, c=3, d=9))

lst = [1, 2, 3]
print([last := x for x in lst], last)

def find_even(seq):
    for x in seq:
        if (m := x % 2) == 0:
            return x, m
    return None, None

print(find_even([1, 3, 4, 6]))

# -*- coding: utf-8 -*-
from __future__ import print_function
# 控制流：if/elif/else、while、for、break/continue/else
def classify(n):
    if n < 0:
        return 'neg'
    elif n == 0:
        return 'zero'
    elif n < 10:
        return 'small'
    else:
        return 'big'

print([classify(i) for i in (-1, 0, 5, 100)])

out = []
i = 0
while i < 10:
    i += 1
    if i % 2 == 0:
        continue
    if i > 7:
        break
    out.append(i)
print(out)

total = 0
for x in range(5):
    total += x
else:
    print('for-else ran, total =', total)

for x in range(10):
    if x == 99:
        break
else:
    print('no break')

n = 3
while n:
    n -= 1
else:
    print('while-else, n =', n)

w = 0
while True:
    w += 1
    if w >= 3:
        break
print('while True break at', w)

for a in range(2):
    for b in range(2):
        if a == b:
            continue
        print('nested', a, b)

if not (1 > 2):
    print('not nested ok')

val = 'x'
if val == 'a':
    print('a')
elif val == 'b' or val == 'x':
    print('b or x')
else:
    print('other')

for ch in 'abc':
    if ch == 'b':
        pass
    else:
        print('ch', ch)

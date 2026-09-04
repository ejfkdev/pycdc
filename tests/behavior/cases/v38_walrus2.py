# -*- coding: utf-8 -*-
# MIN_VERSION: 3.8
# 海象运算符深入形态
data = [3, 1, 2]
if (n := len(data)) > 2:
    print('long', n)

i = 0
while (chunk := data[i:i + 1]) and i < len(data):
    print('chunk', chunk)
    i += 1

results = []
for v in [1, 2, 3, 4, 5, 6]:
    if (sq := v * v) > 10:
        results.append(sq)
print(results)

vals = [y := 0]
for k in range(1, 4):
    vals.append(y := y + k)
print(vals, y)

filtered = [m for x in range(10) if (m := x % 3) == 0]
print(filtered)

def consume(it):
    out = []
    while (item := next(it, None)) is not None:
        out.append(item)
    return out

print(consume(iter([1, 2])))

msg = 'hello world'
if (idx := msg.find('world')) != -1:
    print('found at', idx)

total = 0
for part in ('a', 'bb', 'ccc'):
    total += (plen := len(part))
print(total, plen)

grid = [[1, 2], [3, 4]]
flattened = [cell for row in grid if (rlen := len(row)) == 2 for cell in row]
print(flattened, rlen)

d = {}
if (prev := d.get('k')) is None:
    d['k'] = 1
print(d, prev)

a = [1, 2, 3]
print(a[(last := len(a) - 1)], last)

while True:
    v = a.pop() if a else None
    if v is None:
        break
    print('pop', v)

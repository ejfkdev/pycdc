x = 1
y = 2.5
s = "hello"
b = True
n = None
t = (1, 2, 3)
l = [1, 2, 3]
d = {"a": 1, "b": 2}
st = {1, 2, 3}
a, b2 = 1, 2
a, (c, d2) = 1, (2, 3)
x += 1
x -= 2
x *= 3
x //= 2
x **= 2
x %= 7
z = x if x > 5 else y
w = not (a and b2) or c
v = 1 < x < 100
u = s + "!" * 2
q = t[0]
r = l[1:3]
rr = l[::2]
del q
if x:
    y = 1
elif x > 10:
    y = 2
else:
    y = 3
i = 0
while i < 10:
    i += 1
    if i == 5:
        continue
    if i == 8:
        break
for item in l:
    print(item)
for k, val in d.items():
    pass

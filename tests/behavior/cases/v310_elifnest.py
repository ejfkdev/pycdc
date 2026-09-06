# -*- coding: utf-8 -*-
# MIN_VERSION: 3.10
# elif 链 + 臂内嵌套 if + 后续 elif 臂（crypt.mksalt 族）。
# 3.11+：`elif x is None:` 的 NONE 跳族必须算 elif 条件
# （starts_with_cond_jump），且臂尾 JF 在与嵌套 if 共享 merge 处
# 关闭嵌套块后必须重派发给跨链 Else（否则第三臂掉链成无条件 if，
# 行为破坏）。已知缺口：2.7-3.9 编译器把嵌套 if 假路径 jump-thread
# 到下一 elif 标签，split_cond 将三臂合并成一个 And 链并丢失第二臂
# 体（本用例经 MIN_VERSION 隔离）。
def elif_none(x, r):
    s = ''
    if x == 1:
        s += 'a'
    elif x in (5, 6):
        if r is not None:
            s += 'r'
    elif r is not None:
        s += 'n'
    s += 'z'
    return s

def elif_raise(m, rounds):
    s = '$'
    if m == 'md5':
        s += '1'
    elif m in ('5', '6'):
        if rounds is not None:
            if not 1000 <= rounds <= 999999999:
                raise ValueError('range')
            s += 'r%d' % rounds
    elif rounds is not None:
        raise ValueError('no rounds')
    s += '$'
    return s

print(elif_none(1, None), elif_none(5, 2), elif_none(7, 3), elif_none(7, None))
print(elif_raise('md5', None), elif_raise('6', 2000), elif_raise('x', None))
try:
    elif_raise('x', 5)
except ValueError as e:
    print('VE', e)
try:
    elif_raise('6', 1)
except ValueError as e:
    print('VE', e)

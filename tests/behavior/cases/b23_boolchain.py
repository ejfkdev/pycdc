# -*- coding: utf-8 -*-
# if 条件中的链式比较 or 形：`if a==b==c or d:`（控制流形，链末 PJIT→body、
# 链假经 JF 蹦床+POP_TOP 清理落入下一 or 操作数）。try_merge_or_cond 须把
# 链链接块的 cond 折叠进首操作数并跳过蹦床。值位（return 链 or x）与
# and 形（3.8–3.11 经 try_stmt_chain_compare）一并覆盖。
# 已知缺口：链 or 链（两操作数都是链式比较，3.10 小块复制布局）与
# 3.12+ 语句级 chain-and 另行处理，不在本用例。

def or_chain(a, b, c, d):
    if a == b == c or a == d:
        return 'or1'
    return 'none'


def or_chain_multi(a, b, c, d, e):
    if a == b == c or a == d or a == e:
        return 'multi'
    return 'none'


def or_chain_cmp(a, b, c):
    if a < b < c or c < a:
        return 'lt'
    return 'none'


def val_chain(a, b, c, d):
    return a == b == c or a == d


def and_chain(a, b, c, d):
    if a == b == c and a == d:
        return 'and1'
    return 'none'


def or_chain_chain(a, b, c, d):
    if a == b == c or d == a == b:
        return 'cc'
    return 'none'


def quote_strip(s):
    # the HTMLParser quote-check idiom: or of two slice chains
    if s[:1] == "'" == s[-1:] or s[:1] == '"' == s[-1:]:
        return s[1:-1]
    return s


def elif_ctx(rest, v):
    # or-of-chains in an elif (the merged if must stay associated with the
    # elif chain, not become a sibling if)
    if not rest:
        v = None
    elif v[:1] == "'" == v[-1:] or v[:1] == '"' == v[-1:]:
        v = v[1:-1]
    return v


print(or_chain(1, 1, 1, 9))
print(or_chain(5, 1, 9, 5))
print(or_chain(1, 2, 3, 4))
print(or_chain_multi(1, 1, 1, 9, 9))
print(or_chain_multi(5, 1, 9, 5, 9))
print(or_chain_multi(5, 1, 9, 7, 5))
print(or_chain_multi(1, 2, 3, 4, 5))
print(or_chain_cmp(1, 2, 3))
print(or_chain_cmp(5, 2, 1))
print(or_chain_cmp(1, 9, 2))
print(val_chain(1, 1, 1, 9))
print(val_chain(5, 1, 9, 5))
print(and_chain(1, 1, 1, 1))
print(and_chain(1, 1, 1, 9))
print(and_chain(1, 2, 3, 4))
print(or_chain_chain(1, 1, 1, 9))
print(or_chain_chain(5, 1, 9, 5))
print(or_chain_chain(1, 2, 3, 4))
print(quote_strip("'hi'"))
print(quote_strip('"yo"'))
print(quote_strip('plain'))
print(elif_ctx('', "'q'"))
print(elif_ctx('x', '"d"'))
print(elif_ctx('x', 'raw'))

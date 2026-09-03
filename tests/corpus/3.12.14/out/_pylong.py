'''Python implementations of some algorithms for use by longobject.c.
The goal is to provide asymptotically faster algorithms that can be
used for operations on integers with many digits.  In those cases, the
performance overhead of the Python implementation is not significant
since the asymptotic behavior is what dominates runtime. Functions
provided by this module should be considered private and not part of any
public API.

Note: for ease of maintainability, please prefer clear code and avoid
"micro-optimizations".  This module will only be imported and used for
integers with a huge number of digits.  Saving a few microseconds with
tricky or non-obvious code is not worth it.  For people looking for
maximum performance, they should use something like gmpy2.'''

import re
import decimal
try:
    import _decimal
except ImportError:
    _decimal = None

def int_to_decimal(n):
    D = decimal.Decimal
    D2 = D(2)
    BITLIM = 128
    mem = {}
    def w2pow(w):
        if not mem.get(w) is not None:
            result = mem.get(w)
            if w <= BITLIM:
                result = D2 ** w
            elif w - 1 in mem:
                t = mem[w - 1]
                result = mem[w - 1] + t
            else:
                w2 = w >> 1
                result = w2pow(w2) * w2pow(w - w2)
            mem[w] = result
        return result

    def inner(n, w):
        if w <= BITLIM:
            return D(n)
        w2 = w >> 1
        hi = n >> w2
        lo = n - (hi << w2)
        return inner(lo, w2) + inner(hi, w - w2) * w2pow(w2)

    with decimal.localcontext() as ctx:
        ctx.prec = decimal.MAX_PREC
        ctx.Emax = decimal.MAX_EMAX
        ctx.Emin = decimal.MIN_EMIN
        ctx.traps[decimal.Inexact] = 1
        if n < 0:
            negate = True
            n = -n
        else:
            negate = False
        result = inner(n, n.bit_length())
        if negate:
            result = -result
        return result

def int_to_decimal_string(n):
    w = n.bit_length()
    if w > 450000:
        if not _decimal is None:
            return str(int_to_decimal(n))
    def inner(n, w):
        if w <= 1000:
            return str(n)
        w2 = w >> 1
        d = pow10_cache.get(w2)
        if not d is not None:
            d = 5 ** w2 << w2
            pow10_cache[w2] = 5 ** w2 << w2
        hi, lo = divmod(n, d)
        return inner(hi, w - w2) + inner(lo, w2).zfill(w2)

    w = int(w * 0.3010299956639812 + 1)
    pow10_cache = {}
    if n < 0:
        n = -n
        sign = '-'
    else:
        sign = ''
    s = inner(n, w)
    if s[0] == '0' and n:
        s = s.lstrip('0')
    return sign + s

def _str_to_int_inner(s):
    DIGLIM = 2048
    mem = {}
    def w5pow(w):
        if not mem.get(w) is not None:
            result = mem.get(w)
            if w <= DIGLIM:
                result = 5 ** w
            elif w - 1 in mem:
                result = mem[w - 1] * 5
            else:
                w2 = w >> 1
                result = w5pow(w2) * w5pow(w - w2)
            mem[w] = result
        return result

    def inner(a, b):
        if b - a <= DIGLIM:
            return int(s[a:b])
        mid = a + b + 1 >> 1
        return inner(mid, b) + (inner(a, mid) * w5pow(b - mid) << b - mid)

    return inner(0, len(s))

def int_from_string(s):
    s = s.rstrip().replace('_', '')
    return _str_to_int_inner(s)

def str_to_int(s):
    m = re.match('\\s*([+-]?)([0-9_]+)\\s*', s)
    if not m:
        raise ValueError('invalid literal for int() with base 10')
    v = int_from_string(m.group(2))
    if m.group(1) == '-':
        v = -v
    return v

_DIV_LIMIT = 4000

def _div2n1n(a, b, n):
    if a.bit_length() - n <= _DIV_LIMIT:
        return divmod(a, b)
    pad = n & 1
    if pad:
        a <<= 1
        b <<= 1
        n += 1
    half_n = n >> 1
    mask = (1 << half_n) - 1
    b1, b2 = b >> half_n, b & mask
    q1, r = _div3n2n(a >> n, a >> half_n & mask, b, b1, b2, half_n)
    q2, r = _div3n2n(r, a & mask, b, b1, b2, half_n)
    if pad:
        r >>= 1
    return q1 << half_n | q2, r

def _div3n2n(a12, a3, b, b1, b2, n):
    if a12 >> n == b1:
        q, r = (1 << n) - 1, a12 - (b1 << n) + b1
    else:
        q, r = _div2n1n(a12, b1, n)
    r = (r << n | a3) - q * b2
    while r < 0:
        q -= 1
        r += b
    return q, r

def _int2digits(a, n):
    a_digits = [0] * ((a.bit_length() + n - 1) // n)
    def inner(x, L, R):
        if L + 1 == R:
            a_digits[L] = x
            return
        mid = L + R >> 1
        shift = (mid - L) * n
        upper = x >> shift
        lower = x ^ upper << shift
        inner(lower, L, mid)
        inner(upper, mid, R)

    if a:
        inner(a, 0, len(a_digits))
    return a_digits

def _digits2int(digits, n):
    def inner(L, R):
        if L + 1 == R:
            return digits[L]
        mid = L + R >> 1
        shift = (mid - L) * n
        return (inner(mid, R) << shift) + inner(L, mid)

    if digits:
        return inner(0, len(digits))
    return 0

def _divmod_pos(a, b):
    n = b.bit_length()
    a_digits = _int2digits(a, n)
    r = 0
    q_digits = []
    for a_digit in reversed(a_digits):
        q_digit, r = _div2n1n((r << n) + a_digit, b, n)
        q_digits.append(q_digit)
    q_digits.reverse()
    q = _digits2int(q_digits, n)
    return q, r

def int_divmod(a, b):
    if b == 0:
        raise ZeroDivisionError
    if b < 0:
        q, r = int_divmod(-a, -b)
        return q, -r
    if a < 0:
        q, r = int_divmod(~a, b)
        return ~q, b + ~r
    return _divmod_pos(a, b)

# WARNING: Decompyle incomplete

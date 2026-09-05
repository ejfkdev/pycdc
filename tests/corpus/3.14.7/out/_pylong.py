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

def compute_powers(w, base, more_than, *, need_hi=False, show=False):
    seen = set()
    need = set()
    ws = {w}
    while ws:
        w = ws.pop()
        if not w in seen:
            if w <= more_than:
                continue
        seen.add(w)
        lo = w >> 1
        hi = w - lo
        which = hi if need_hi else lo
        need.add(which)
        ws.add(which)
        if not lo != hi:
            continue
        ws.add(w - which)
    cands = need.copy()
    extra = set()
    while cands:
        w = max(cands)
        cands.remove(w)
        lo = w >> 1
        if lo > more_than and w - 1 not in cands and lo not in cands:
            extra.add(lo)
            cands.add(lo)
    if not need_hi:
        if extra:
            raise AssertionError
    d = {}
    for n in sorted(need | extra):
        lo = n >> 1
        hi = n - lo
        if n - 1 in d:
            if show:
                print('* base', end='')
            result = d[n - 1] * base
        elif lo in d:
            if show:
                print('square', end='')
            result = d[lo] * d[lo]
            if hi != lo:
                if show:
                    print(' * base', end='')
                if not 2 * lo + 1 == n:
                    raise AssertionError
                result *= base
        else:
            if show:
                print('pow', end='')
            result = base ** n
        if show:
            print(' at', n, 'needed' if n in need else 'extra')
        d[n] = result
    if not need <= d.keys():
        raise AssertionError
    if (excess := d.keys() - need):
        if not need_hi:
            raise AssertionError
        for n in excess:
            del d[n]
    return d

_unbounded_dec_context = decimal.getcontext().copy()
_unbounded_dec_context.prec = decimal.MAX_PREC
_unbounded_dec_context.Emax = decimal.MAX_EMAX
_unbounded_dec_context.Emin = decimal.MIN_EMIN
_unbounded_dec_context.traps[decimal.Inexact] = 1

def int_to_decimal(n):
    """Asymptotically fast conversion of an 'int' to Decimal."""

    from decimal import Decimal as D
    BITLIM = 200
    def inner(n, w):
        if w <= BITLIM:
            return D(n)
        w2 = w >> 1
        hi = n >> w2
        lo = n & (1 << w2) - 1
        return inner(lo, w2) + inner(hi, w - w2) * w2pow[w2]

    with decimal.localcontext(_unbounded_dec_context):
        nbits = n.bit_length()
        w2pow = compute_powers(nbits, D(2), BITLIM)
        if n < 0:
            negate = True
            n = -n
        else:
            negate = False
        result = inner(n, nbits)
        if negate:
            result = -result
    return result

def int_to_decimal_string(n):
    """Asymptotically fast conversion of an 'int' to a decimal string."""

    w = n.bit_length()
    if w > 450000:
        if not _decimal is None:
            return str(int_to_decimal(n))
    DIGLIM = 1000
    def inner(n, w):
        if w <= DIGLIM:
            return str(n)
        w2 = w >> 1
        hi, lo = divmod(n, pow10[w2])
        return inner(hi, w - w2) + inner(lo, w2).zfill(w2)

    w = int(w * 0.3010299956639812 + 1)
    pow10 = compute_powers(w, 5, DIGLIM)
    for k, v in pow10.items():
        pow10[k] = v << k
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
    """Asymptotically fast conversion of a 'str' to an 'int'."""

    DIGLIM = 2048
    def inner(a, b):
        if b - a <= DIGLIM:
            return int(s[a:b])
        mid = a + b + 1 >> 1
        return inner(mid, b) + (inner(a, mid) * w5pow[b - mid] << b - mid)

    w5pow = compute_powers(len(s), 5, DIGLIM)
    return inner(0, len(s))

_LOG_10_BASE_256 = float.fromhex('0x1.a934f0979a371p-2')
from collections import defaultdict
_spread = defaultdict(int)
del defaultdict

def _dec_str_to_int_inner(s, *, GUARD=8):
    BYTELIM = 100000
    D = decimal.Decimal
    result = bytearray()
    if not GUARD > 0:
        raise AssertionError
    def inner(n, w):
        if w <= BYTELIM:
            result.extend(int(str(n)).to_bytes(w))
            return
        w1 = w >> 1
        w2 = w - w1
        p256, recip = pow256[w2]
        ctx.prec = max(n.adjusted() - p256.adjusted(), 0) + GUARD
        hi = n * recip
        ctx.prec = decimal.MAX_PREC
        hi = hi.to_integral_value()
        lo = n - hi * p256
        if not lo >= 0:
            raise AssertionError
        count = 0
        if lo >= p256:
            count = 1
            lo -= p256
            hi += 1
            if lo >= p256:
                count = 999
                hi2, lo = divmod(lo, p256)
                hi += hi2
        _spread[count] += 1
        inner(hi, w1)
        del hi
        inner(lo, w2)

    lenS = s.__len__()
    log_ub = lenS * _LOG_10_BASE_256
    log_ub_as_int = int(log_ub)
    w = log_ub_as_int + 1 + (log_ub - log_ub_as_int > 0.9)
    if w.bit_length() >= 46:
        raise ValueError(f'cannot convert string of len {lenS} to int')
    with decimal.localcontext(_unbounded_dec_context) as ctx:
        D256 = D(256)
        pow256 = compute_powers(w, D256, BYTELIM, need_hi=True)
        rpow256 = compute_powers(w, 1 / D256, BYTELIM, need_hi=True)
        ctx.traps[decimal.Inexact] = 0
        ctx.rounding = decimal.ROUND_DOWN
        for k, v in pow256.items():
            ctx.prec = v.adjusted() + GUARD + 1
            pow256[k] = v, rpow256[k]
        del rpow256
        ctx.prec = decimal.MAX_PREC
        inner(D(s), w)
    return int.from_bytes(result)

def int_from_string(s):
    """Asymptotically fast version of PyLong_FromString(), conversion
of a string of decimal digits into an 'int'."""

    s = s.rstrip().replace('_', '')
    func = _str_to_int_inner
    if len(s) >= 2000000:
        if not _decimal is None:
            func = _dec_str_to_int_inner
    return func(s)

def str_to_int(s):
    """Asymptotically fast version of decimal string to 'int' conversion."""

    m = re.match('\\s*([+-]?)([0-9_]+)\\s*', s)
    if not m:
        raise ValueError('invalid literal for int() with base 10')
    v = int_from_string(m.group(2))
    if m.group(1) == '-':
        v = -v
    return v

_DIV_LIMIT = 4000

def _div2n1n(a, b, n):
    '''Divide a 2n-bit nonnegative integer a by an n-bit positive integer
b, using a recursive divide-and-conquer algorithm.

Inputs:
  n is a positive integer
  b is a positive integer with exactly n bits
  a is a nonnegative integer such that a < 2**n * b

Output:
  (q, r) such that a = b*q+r and 0 <= r < b.

'''

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
    '''Helper function for _div2n1n; not intended to be called directly.'''

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
    '''Decompose non-negative int a into base 2**n

Input:
  a is a non-negative integer

Output:
  List of the digits of a in base 2**n in little-endian order,
  meaning the most significant digit is last. The most
  significant digit is guaranteed to be non-zero.
  If a is 0 then the output is an empty list.

'''

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
    '''Combine base-2**n digits into an int. This function is the
inverse of `_int2digits`. For more details, see _int2digits.
'''

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
    '''Divide a non-negative integer a by a positive integer b, giving
quotient and remainder.'''

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
    """Asymptotically fast replacement for divmod, for 'int'.
Its time complexity is O(n**1.58), where n = #bits(a) + #bits(b).
"""

    if b == 0:
        raise ZeroDivisionError('division by zero')
    if b < 0:
        q, r = int_divmod(-a, -b)
        return q, -r
    if a < 0:
        q, r = int_divmod(~a, b)
        return ~q, b + ~r
    return _divmod_pos(a, b)

# WARNING: Decompyle incomplete

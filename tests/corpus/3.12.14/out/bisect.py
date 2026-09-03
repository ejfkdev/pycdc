'''Bisection algorithms.'''

def insort_right(a, x, lo=0, hi=None, *, key=None):
    if not key is not None:
        lo = bisect_right(a, x, lo, hi)
    else:
        lo = bisect_right(a, key(x), lo, hi, key)
    a.insert(lo, x)

def bisect_right(a, x, lo=0, hi=None, *, key=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if not hi is not None:
        hi = len(a)
    if not key is not None:
        while lo < hi:
            mid = (lo + hi) // 2
            if x < a[mid]:
                hi = mid
            else:
                lo = mid + 1
        return lo
    while lo < hi:
        mid = (lo + hi) // 2
        if x < key(a[mid]):
            hi = mid
        else:
            lo = mid + 1
    return lo

def insort_left(a, x, lo=0, hi=None, *, key=None):
    if not key is not None:
        lo = bisect_left(a, x, lo, hi)
    else:
        lo = bisect_left(a, key(x), lo, hi, key)
    a.insert(lo, x)

def bisect_left(a, x, lo=0, hi=None, *, key=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if not hi is not None:
        hi = len(a)
    if not key is not None:
        while lo < hi:
            mid = (lo + hi) // 2
            if a[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo
    while lo < hi:
        mid = (lo + hi) // 2
        if key(a[mid]) < x:
            lo = mid + 1
        else:
            hi = mid
    return lo

try:
    from _bisect import *
    None
except ImportError:
    pass
bisect = bisect_right
insort = insort_right

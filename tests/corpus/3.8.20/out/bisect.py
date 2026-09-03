'''Bisection algorithms.'''

def insort_right(a, x, lo=0, hi=None):
    lo = bisect_right(a, x, lo, hi)
    a.insert(lo, x)

def bisect_right(a, x, lo=0, hi=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if x < a[mid]:
            hi = mid
        else:
            lo = mid + 1
    return lo

def insort_left(a, x, lo=0, hi=None):
    lo = bisect_left(a, x, lo, hi)
    a.insert(lo, x)

def bisect_left(a, x, lo=0, hi=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo

try:
    from _bisect import *
except ImportError:
    pass
bisect = bisect_right
insort = insort_right
# WARNING: Decompyle incomplete

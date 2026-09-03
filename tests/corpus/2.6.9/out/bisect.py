'''Bisection algorithms.'''

def insort_right(a, x, lo=0, hi=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if x < a[mid]:
            hi = mid
            continue
        lo = mid + 1
        continue
    a.insert(lo, x)

insort = insort_right

def bisect_right(a, x, lo=0, hi=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if x < a[mid]:
            hi = mid
            continue
        lo = mid + 1
        continue
    return lo

bisect = bisect_right

def insort_left(a, x, lo=0, hi=None):
    if lo < 0:
        raise ValueError('lo must be non-negative')
    if hi is None:
        hi = len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
            continue
        hi = mid
        continue
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
            continue
        hi = mid
        continue
    return lo

try:
    from _bisect import bisect_right
    from _bisect import bisect_left
    from _bisect import insort_left
    from _bisect import insort_right
    from _bisect import insort
    from _bisect import bisect
except ImportError:
    pass
# WARNING: Decompyle incomplete

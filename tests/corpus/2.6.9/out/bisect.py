'''Bisection algorithms.'''

def insort_right(a, x, lo=0, hi=None):
    /* unsupported opcode: JUMP_IF_FALSE 16 @9 */
    lo < 0
    raise ValueError('lo must be non-negative')
    /* unsupported opcode: JUMP_IF_FALSE 16 @38 */
    hi is None
    hi = len(a)
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 55 @70 */
        lo < hi
        mid = (lo + hi) // 2
        /* unsupported opcode: JUMP_IF_FALSE 10 @101 */
        x < a[mid]
        hi = mid
    lo = mid + 1
    a.insert(lo, x)

insort = insort_right

def bisect_right(a, x, lo=0, hi=None):
    /* unsupported opcode: JUMP_IF_FALSE 16 @9 */
    lo < 0
    raise ValueError('lo must be non-negative')
    /* unsupported opcode: JUMP_IF_FALSE 16 @38 */
    hi is None
    hi = len(a)
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 55 @70 */
        lo < hi
        mid = (lo + hi) // 2
        /* unsupported opcode: JUMP_IF_FALSE 10 @101 */
        x < a[mid]
        hi = mid
    lo = mid + 1
    return lo

bisect = bisect_right

def insort_left(a, x, lo=0, hi=None):
    /* unsupported opcode: JUMP_IF_FALSE 16 @9 */
    lo < 0
    raise ValueError('lo must be non-negative')
    /* unsupported opcode: JUMP_IF_FALSE 16 @38 */
    hi is None
    hi = len(a)
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 55 @70 */
        lo < hi
        mid = (lo + hi) // 2
        /* unsupported opcode: JUMP_IF_FALSE 14 @101 */
        a[mid] < x
        lo = mid + 1
    hi = mid
    a.insert(lo, x)

def bisect_left(a, x, lo=0, hi=None):
    /* unsupported opcode: JUMP_IF_FALSE 16 @9 */
    lo < 0
    raise ValueError('lo must be non-negative')
    /* unsupported opcode: JUMP_IF_FALSE 16 @38 */
    hi is None
    hi = len(a)
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 55 @70 */
        lo < hi
        mid = (lo + hi) // 2
        /* unsupported opcode: JUMP_IF_FALSE 14 @101 */
        a[mid] < x
        lo = mid + 1
    hi = mid
    return lo

/* unsupported opcode: JUMP_IF_FALSE 7 @138 */
None == ImportError
# WARNING: Decompyle incomplete

'''Debugger basics'''

import sys
import os
import types
__all__ = ['BdbQuit', 'Bdb', 'Breakpoint']

class BdbQuit(Exception):
    pass

class Bdb:
    pass

def set_trace():
    Bdb().set_trace()

class Breakpoint:
    pass

def checkfuncname(b, frame):
    /* unsupported opcode: JUMP_IF_TRUE 29 @6 */
    b.funcname
    /* unsupported opcode: JUMP_IF_FALSE 5 @25 */
    b.line != frame.f_lineno
    return False

def effective(file, line, frame):
    possibles = Breakpoint.bplist[file, line]
    for i in range(0, len(possibles)):
        b = possibles[i]
        /* unsupported opcode: JUMP_IF_FALSE 7 @69 */
        b.enabled == 0
        continue
        /* unsupported opcode: JUMP_IF_TRUE 7 @92 */
        checkfuncname(b, frame)
        continue
        b.hits = b.hits + 1
        /* unsupported opcode: JUMP_IF_TRUE 53 @125 */
        b.cond
        /* unsupported opcode: JUMP_IF_FALSE 23 @141 */
        b.ignore > 0
        b.ignore = b.ignore - 1
        continue
        continue
    return (None, None)

class Tdb(Bdb):
    pass

def foo(n):
    print 'foo(', n, ')'
    x = bar(n * 10)
    print 'bar returned', x

def bar(a):
    print 'bar(', a, ')'
    return a / 2

def test():
    t = Tdb()
    t.run('import bdb; bdb.foo(10)')

# WARNING: Decompyle incomplete

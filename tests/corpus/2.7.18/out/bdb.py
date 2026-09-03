'''Debugger basics'''

import fnmatch
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
    if not b.funcname:
        if b.line != frame.f_lineno:
            return False
        return True
    if frame.f_code.co_name != b.funcname:
        return False
    if not b.func_first_executable_line:
        b.func_first_executable_line = frame.f_lineno
    if b.func_first_executable_line != frame.f_lineno:
        return False
    return True

def effective(file, line, frame):
    possibles = Breakpoint.bplist[file, line]
    for i in range(0, len(possibles)):
        b = possibles[i]
        if b.enabled == 0:
            continue
        if not checkfuncname(b, frame):
            continue
        b.hits = b.hits + 1
        if not b.cond:
            if b.ignore > 0:
                b.ignore = b.ignore - 1
                continue
                continue
        return b, 1
        continue
        return b, 1
        return b, 0
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


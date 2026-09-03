'''
atexit.py - allow programmer to define multiple exit functions to be executed
upon normal program termination.

One public function, register, is defined.
'''

__all__ = ['register']
import sys
_exithandlers = []

def _run_exitfuncs():
    exc_info = None
    while _exithandlers:
        func, targs, kargs = _exithandlers.pop()
        import traceback
        print >>sys.stderr, sys.stderr
        traceback.print_exc()
        exc_info = sys.exc_info()
        try:
            func(*targs, **kargs)
        except SystemExit:
            exc_info = sys.exc_info()
            continue
    if exc_info is not None:
        raise exc_info[1] # WARNING: raise cause dropped (py2)

def register(func, *targs, **kargs):
    _exithandlers.append((func, targs, kargs))
    return func

if hasattr(sys, 'exitfunc'):
    register(sys.exitfunc)
sys.exitfunc = _run_exitfuncs
if __name__ == '__main__':
    def x1():
        print 'running x1'

    def x2(n):
        print 'running x2(%r)' % (n,)

    def x3(n, kwd=None):
        print 'running x3(%r, kwd=%r)' % (n, kwd)

    register(x1)
    register(x2, 12)
    register(x3, 5, 'bar')
    register(x3, 'no kwd args')
# WARNING: Decompyle incomplete

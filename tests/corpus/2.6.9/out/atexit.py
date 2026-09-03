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
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 129 @12 */
        _exithandlers
    /* unsupported opcode: JUMP_IF_FALSE 19 @64 */
    None == SystemExit
    exc_info = sys.exc_info()
    import traceback
    print >>sys.stderr, sys.stderr
    traceback.print_exc()
    exc_info = sys.exc_info()
    /* unsupported opcode: JUMP_IF_FALSE 28 @155 */
    exc_info is not None
    raise exc_info[1] # WARNING: raise cause dropped (py2)
    exc_info[0]

def register(func, *targs, **kargs):
    _exithandlers.append((func, targs, kargs))
    return func

/* unsupported opcode: JUMP_IF_FALSE 17 @63 */
hasattr(sys, 'exitfunc')
register(sys.exitfunc)
sys.exitfunc = _run_exitfuncs
/* unsupported opcode: JUMP_IF_FALSE 86 @102 */
__name__ == '__main__'

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

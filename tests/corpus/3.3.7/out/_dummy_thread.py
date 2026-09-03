'''Drop-in replacement for the thread module.

Meant to be used as a brain-dead substitute so that threaded code does
not need to be rewritten for when the thread module is not present.

Suggested usage is::

    try:
        import _thread
    except ImportError:
        import _dummy_thread as _thread

'''

__all__ = ['error', 'start_new_thread', 'exit', 'get_ident', 'allocate_lock', 'interrupt_main', 'LockType']
TIMEOUT_MAX = 2147483648
error = RuntimeError

def start_new_thread(function, args, kwargs={}):
    global _main, _interrupt
    if type(args) != type(tuple()):
        raise TypeError('2nd arg must be a tuple')
    if type(kwargs) != type(dict()):
        raise TypeError('3rd arg must be a dict')
    _main = False
    import traceback
    traceback.print_exc()
    try:
        function(*args, **kwargs)
    except SystemExit:
        pass
    _main = True
    if _interrupt:
        _interrupt = False
        raise KeyboardInterrupt

def exit():
    raise SystemExit

def get_ident():
    return -1

def allocate_lock():
    return LockType()

def stack_size(size=None):
    if size is not None:
        raise error('setting thread stack size not supported')
    return 0

class LockType(object):
    '''Class implementing dummy implementation of _thread.LockType.

    Compatibility is maintained by maintaining self.locked_status
    which is a boolean that stores the state of the lock.  Pickling of
    the lock, though, should not be done since if the _thread module is
    then used with an unpickled ``lock()`` from here problems could
    occur from this class not having atomic methods.

    '''

    def __init__(self):
        self.locked_status = False

    def acquire(self, waitflag=None, timeout=-1):
        if waitflag is None or waitflag:
            self.locked_status = True
            return True
        if not self.locked_status:
            self.locked_status = True
            return True
        if timeout > 0:
            import time
            time.sleep(timeout)
        return False

    __enter__ = acquire
    def __exit__(self, typ, val, tb):
        self.release()

    def release(self):
        if not self.locked_status:
            raise error
        self.locked_status = False
        return True

    def locked(self):
        return self.locked_status


_interrupt = False
_main = True

def interrupt_main():
    global _interrupt
    if _main:
        raise KeyboardInterrupt
    else:
        _interrupt = True

# WARNING: Decompyle incomplete

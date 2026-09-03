'''Drop-in replacement for the thread module.

Meant to be used as a brain-dead substitute so that threaded code does
not need to be rewritten for when the thread module is not present.

Suggested usage is::

    try:
        import _thread
    except ImportError:
        import _dummy_thread as _thread

'''

__all__ = ['error', 'start_new_thread', 'exit', 'get_ident', 'allocate_lock', 'interrupt_main', 'LockType', 'RLock']
TIMEOUT_MAX = 2147483648
error = RuntimeError

def start_new_thread(function, args, kwargs={}):
    global _main, _interrupt
    if type(args) != type(tuple()):
        raise TypeError('2nd arg must be a tuple')
    if type(kwargs) != type(dict()):
        raise TypeError('3rd arg must be a dict')
    try:
        _main = False
        function(*args, **kwargs)
    except SystemExit:
        pass
    else:
        import traceback
        traceback.print_exc()
    _main = True
    if _interrupt:
        _interrupt = False
        raise KeyboardInterrupt

def exit():
    raise SystemExit

def get_ident():
    return 1

def allocate_lock():
    return LockType()

def stack_size(size=None):
    if size is not None:
        raise error('setting thread stack size not supported')
    return 0

def _set_sentinel():
    return LockType()

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
        if not waitflag is None:
            if waitflag:
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

    def __repr__(self):
        return '<%s %s.%s object at %s>' % ('locked' if self.locked_status else 'unlocked', self.__class__.__module__, self.__class__.__qualname__, hex(id(self)))


class RLock(LockType):
    '''Dummy implementation of threading._RLock.

    Re-entrant lock can be aquired multiple times and needs to be released
    just as many times. This dummy implemention does not check wheter the
    current thread actually owns the lock, but does accounting on the call
    counts.
    '''

    def __init__(self):
        super().__init__()
        self._levels = 0

    def acquire(self, waitflag=None, timeout=-1):
        locked = super().acquire(waitflag, timeout)
        if locked:
            self._levels += 1
        return locked

    def release(self):
        if self._levels == 0:
            raise error
        if self._levels == 1:
            super().release()
        self._levels -= 1


_interrupt = False
_main = True

def interrupt_main():
    global _interrupt
    if _main:
        raise KeyboardInterrupt
    else:
        _interrupt = True

# WARNING: Decompyle incomplete

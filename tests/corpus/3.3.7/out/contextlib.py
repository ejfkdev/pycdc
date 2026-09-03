'''Utilities for with-statement contexts.  See PEP 343.'''

import sys
from collections import deque
from functools import wraps
__all__ = ['contextmanager', 'closing', 'ContextDecorator', 'ExitStack']

class ContextDecorator(object):
    '''A base class or mixin that enables context managers to work as decorators.'''

    def _recreate_cm(self):
        return self

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwds):
            with self._recreate_cm():
                return func(*args, **kwds)

        return inner


class _GeneratorContextManager(ContextDecorator):
    '''Helper for @contextmanager decorator.'''

    def __init__(self, func, *args, **kwds):
        self.gen = func(*args, **kwds)
        self.func = func
        self.args = args
        self.kwds = kwds

    def _recreate_cm(self):
        return self.__class__(self.func, *self.args, **self.kwds)

    def __enter__(self):
        try:
            return next(self.gen)
        except StopIteration:
            raise RuntimeError("generator didn't yield")

    def __exit__(self, type, value, traceback):
        if type is None:
            try:
                next(self.gen)
            except StopIteration:
                return
            else:
                raise RuntimeError("generator didn't stop")
        elif value is None:
            value = type()
        if sys.exc_info()[1] is not value:
            raise
        try:
            self.gen.throw(type, value, traceback)
            raise RuntimeError("generator didn't stop after throw()")
        except StopIteration as exc:
            return exc is not value


def contextmanager(func):
    @wraps(func)
    def helper(*args, **kwds):
        return _GeneratorContextManager(func, *args, **kwds)

    return helper

class closing(object):
    '''Context to automatically close something at the end of a block.

    Code like this:

        with closing(<module>.open(<arguments>)) as f:
            <block>

    is equivalent to this:

        f = <module>.open(<arguments>)
        try:
            <block>
        finally:
            f.close()

    '''

    def __init__(self, thing):
        self.thing = thing

    def __enter__(self):
        return self.thing

    def __exit__(self, *exc_info):
        self.thing.close()


class ExitStack(object):
    '''Context manager for dynamic management of a stack of exit callbacks

    For example:

        with ExitStack() as stack:
            files = [stack.enter_context(open(fname)) for fname in filenames]
            # All opened files will automatically be closed at the end of
            # the with statement, even if attempts to open files later
            # in the list raise an exception

    '''

    def __init__(self):
        self._exit_callbacks = deque()

    def pop_all(self):
        new_stack = type(self)()
        new_stack._exit_callbacks = self._exit_callbacks
        self._exit_callbacks = deque()
        return new_stack

    def _push_cm_exit(self, cm, cm_exit):
        def _exit_wrapper(*exc_details):
            return cm_exit(cm, *exc_details)

        _exit_wrapper.__self__ = cm
        self.push(_exit_wrapper)

    def push(self, exit):
        _cb_type = type(exit)
        try:
            exit_method = _cb_type.__exit__
        except AttributeError:
            self._exit_callbacks.append(exit)
        else:
            self._push_cm_exit(exit, exit_method)
        return exit

    def callback(self, callback, *args, **kwds):
        def _exit_wrapper(exc_type, exc, tb):
            callback(*args, **kwds)

        _exit_wrapper.__wrapped__ = callback
        self.push(_exit_wrapper)
        return callback

    def enter_context(self, cm):
        _cm_type = type(cm)
        _exit = _cm_type.__exit__
        result = _cm_type.__enter__(cm)
        self._push_cm_exit(cm, _exit)
        return result

    def close(self):
        self.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc_details):
        received_exc = exc_details[0] is not None
        frame_exc = sys.exc_info()[1]
        def _fix_exception_context(new_exc, old_exc):
            while True:
                exc_context = new_exc.__context__
                if exc_context is old_exc:
                    return
                if not exc_context is None:
                    if exc_context is frame_exc:
                        break
                new_exc = exc_context
                continue
            new_exc.__context__ = old_exc

        suppressed_exc = False
        pending_raise = False
        while self._exit_callbacks:
            cb = self._exit_callbacks.pop()
            try:
                if cb(*exc_details):
                    suppressed_exc = True
                    pending_raise = False
                    exc_details = (None, None, None)
            except:
                new_exc_details = sys.exc_info()
                _fix_exception_context(new_exc_details[1], exc_details[1])
                pending_raise = True
                exc_details = new_exc_details
            continue
        if pending_raise:
            pass
        return received_exc and suppressed_exc


# WARNING: Decompyle incomplete

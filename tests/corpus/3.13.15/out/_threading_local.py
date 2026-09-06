"""Thread-local objects.

(Note that this module provides a Python version of the threading.local
 class.  Depending on the version of Python you're using, there may be a
 faster one available.  You should always import the `local` class from
 `threading`.)
"""

from weakref import ref
from contextlib import contextmanager
__all__ = ['local']

class _localimpl:
    '''A class managing thread-local dicts'''

    __slots__ = ('key', 'dicts', 'localargs', 'locallock', '__weakref__')
    def __init__(self):
        self.key = '_threading_local._localimpl.' + str(id(self))
        self.dicts = {}

    def get_dict(self):
        '''Return the dict for the current thread. Raises KeyError if none
defined.'''

        thread = current_thread()
        return self.dicts[id(thread)][1]

    def create_dict(self):
        '''Create a new dict for the current thread, and return it.'''

        localdict = {}
        key = self.key
        thread = current_thread()
        idt = id(thread)
        def local_deleted(_, key=key):
            thread = wrthread()
            if thread is not None:
                del thread.__dict__[key]

        def thread_deleted(_, idt=idt):
            local = wrlocal()
            if local is not None:
                dct = local.dicts.pop(idt)

        wrlocal = ref(self, local_deleted)
        wrthread = ref(thread, thread_deleted)
        thread.__dict__[key] = wrlocal
        self.dicts[idt] = wrthread, localdict
        return localdict


@contextmanager
def _patch(self):
    impl = object.__getattribute__(self, '_local__impl')
    dct = impl.get_dict()
    with impl.locallock:
        object.__setattr__(self, '__dict__', dct)
        yield None

class local:
    __slots__ = ('_local__impl', '__dict__')
    def __new__(cls, /, *args, **kw):
        if (args or kw) and cls.__init__ is object.__init__:
            raise TypeError('Initialization arguments are not supported')
        self = object.__new__(cls)
        impl = _localimpl()
        impl.localargs = args, kw
        impl.locallock = RLock()
        object.__setattr__(self, '_local__impl', impl)
        impl.create_dict()
        return self

    def __getattribute__(self, name):
        with _patch(self):
            pass
        None(None, None)

    def __setattr__(self, name, value):
        if name == '__dict__':
            raise AttributeError("%r object attribute '__dict__' is read-only" % self.__class__.__name__)
        with _patch(self):
            pass
        None(None, None)

    def __delattr__(self, name):
        if name == '__dict__':
            raise AttributeError("%r object attribute '__dict__' is read-only" % self.__class__.__name__)
        with _patch(self):
            pass
        None(None, None)


from threading import current_thread
from threading import RLock
# WARNING: Decompyle incomplete

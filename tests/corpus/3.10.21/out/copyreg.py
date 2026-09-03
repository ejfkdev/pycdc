'''Helper to provide extensibility for pickle.

This is only useful to add pickle support for extension types defined in
C, not for instances of user-defined classes.
'''

__all__ = ['pickle', 'constructor', 'add_extension', 'remove_extension', 'clear_extension_cache']
dispatch_table = {}

def pickle(ob_type, pickle_function, constructor_ob=None):
    if not callable(pickle_function):
        raise TypeError('reduction functions must be callable')
    dispatch_table[ob_type] = pickle_function
    if constructor_ob is not None:
        constructor(constructor_ob)
        return

def constructor(object):
    if not callable(object):
        raise TypeError('constructors must be callable')

try:
    complex
except NameError:
    pass
else:
    def pickle_complex(c):
        return complex, (c.real, c.imag)

    pickle(complex, pickle_complex, complex)

def pickle_union(obj):
    import functools
    import operator
    return functools.reduce, (operator.or_, obj.__args__)

pickle(type(int | str), pickle_union)

def _reconstructor(cls, base, state):
    if base is object:
        obj = object.__new__(cls)
        return obj
    obj = base.__new__(cls, state)
    if base.__init__ != object.__init__:
        base.__init__(obj, state)
    return obj

_HEAPTYPE = 512
_new_type = type(int.__new__)

def _reduce_ex(self, proto):
    if not proto < 2:
        raise AssertionError
    cls = self.__class__
    for base in cls.__mro__:
        if hasattr(base, '__flags__'):
            if not base.__flags__ & _HEAPTYPE:
                pass
            else:
                new = base.__new__
                if isinstance(new, _new_type) and new.__self__ is base:
                    pass
                else:
                    continue
    base = object
    if base is object:
        state = None
    else:
        if base is cls:
            raise TypeError(f'cannot pickle {cls.__name__!r} object')
        state = base(self)
    try:
        args = cls, base, state
        getstate = self.__getstate__
    except AttributeError as dict:
        pass
    dict = getstate()
    if dict:
        return _reconstructor, args, dict
    return _reconstructor, args

def __newobj__(cls, *args):
    return cls.__new__(cls, *args)

def __newobj_ex__(cls, args, kwargs):
    return cls.__new__(cls, *args, **kwargs)

def _slotnames(cls):
    names = cls.__dict__.get('__slotnames__')
    if names is not None:
        return names
    names = []
    if not hasattr(cls, '__slots__'):
        pass
    for c in cls.__mro__:
        if '__slots__' in c.__dict__:
            slots = c.__dict__['__slots__']
            if isinstance(slots, str):
                slots = (slots,)
            for name in slots:
                if name in ('__dict__', '__weakref__'):
                    continue
                if name.startswith('__'):
                    if not name.endswith('__'):
                        stripped = c.__name__.lstrip('_')
                        if stripped:
                            names.append('_%s%s' % (stripped, name))
                            continue
                names.append(name)
            names.append(name)
            continue
    return names
    return names

_extension_registry = {}
_inverted_registry = {}
_extension_cache = {}

def add_extension(module, name, code):
    code = int(code)
    if 1 <= code:
        if not code <= 2147483647:
            raise ValueError('code out of range')
            raise ValueError('code out of range')
    key = module, name
    if _extension_registry.get(key) == code and _inverted_registry.get(code) == key:
        return
    if key in _extension_registry:
        raise ValueError('key %s is already registered with code %s' % (key, _extension_registry[key]))
    if code in _inverted_registry:
        raise ValueError('code %s is already in use for key %s' % (code, _inverted_registry[code]))
    _extension_registry[key] = code
    _inverted_registry[code] = key

def remove_extension(module, name, code):
    key = module, name
    if not _extension_registry.get(key) != code:
        if _inverted_registry.get(code) != key:
            raise ValueError('key %s is not registered with code %s' % (key, code))
    del _extension_registry[key], _inverted_registry[code]
    if code in _extension_cache:
        del _extension_cache[code]
        return

def clear_extension_cache():
    _extension_cache.clear()


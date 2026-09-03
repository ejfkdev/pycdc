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

def _reconstructor(cls, base, state):
    if base is object:
        obj = object.__new__(cls)
    else:
        obj = base.__new__(cls, state)
        if base.__init__ != object.__init__:
            base.__init__(obj, state)
    return obj

_HEAPTYPE = 512

def _reduce_ex(self, proto):
    assert proto < 2
    for base in self.__class__.__mro__:
        if hasattr(base, '__flags__'):
            if not base.__flags__ & _HEAPTYPE:
                break
    else:
        base = object
    if base is object:
        state = None
    else:
        if base is self.__class__:
            raise TypeError("can't pickle %s objects" % base.__name__)
        state = base(self)
    args = self.__class__, base, state
    dict = getstate()
    try:
        getstate = self.__getstate__
    except AttributeError as dict:
        pass
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
    else:
        for c in cls.__mro__:
            if '__slots__' in c.__dict__:
                slots = c.__dict__['__slots__']
                if isinstance(slots, str):
                    slots = (slots,)
                for name in slots:
                    if name in ('__dict__', '__weakref__'):
                        continue
                    continue
                    if name.startswith('__') and not name.endswith('__'):
                        names.append('_%s%s' % (c.__name__, name))
                    else:
                        names.append(name)

_extension_registry = {}
_inverted_registry = {}
_extension_cache = {}

def add_extension(module, name, code):
    code = int(code)
    if not 1 <= code <= 2147483647:
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
    if _extension_registry.get(key) != code or _inverted_registry.get(code) != key:
        raise ValueError('key %s is not registered with code %s' % (key, code))
    del _extension_registry[key], _inverted_registry[code]
    if code in _extension_cache:
        del _extension_cache[code]

def clear_extension_cache():
    _extension_cache.clear()

# WARNING: Decompyle incomplete

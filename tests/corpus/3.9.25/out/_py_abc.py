from _weakrefset import WeakSet

def get_cache_token():
    return ABCMeta._abc_invalidation_counter

class ABCMeta(type):
    """Metaclass for defining Abstract Base Classes (ABCs).

    Use this metaclass to create an ABC.  An ABC can be subclassed
    directly, and then acts as a mix-in class.  You can also register
    unrelated concrete classes (even built-in classes) and unrelated
    ABCs as 'virtual subclasses' -- these and their descendants will
    be considered subclasses of the registering ABC by the built-in
    issubclass() function, but the registering ABC won't show up in
    their MRO (Method Resolution Order) nor will method
    implementations defined by the registering ABC be callable (not
    even via super()).
    """

    _abc_invalidation_counter = 0
    def __new__(mcls, name, bases, namespace, /, **kwargs):
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)
        abstracts = {name for name in namespace.items() if getattr(value, '__isabstractmethod__', False)}
        for base in bases:
            for name in getattr(base, '__abstractmethods__', set()):
                value = getattr(cls, name, None)
                if getattr(value, '__isabstractmethod__', False):
                    abstracts.add(name)
        cls.__abstractmethods__ = frozenset(abstracts)
        cls._abc_registry = WeakSet()
        cls._abc_cache = WeakSet()
        cls._abc_negative_cache = WeakSet()
        cls._abc_negative_cache_version = ABCMeta._abc_invalidation_counter
        return cls

    def register(cls, subclass):
        if not isinstance(subclass, type):
            raise TypeError('Can only register classes')
        if issubclass(subclass, cls):
            return subclass
        if issubclass(cls, subclass):
            raise RuntimeError('Refusing to create an inheritance cycle')
        cls._abc_registry.add(subclass)
        ABCMeta._abc_invalidation_counter += 1
        return subclass

    def _dump_registry(cls, file=None):
        print(f'Class: {cls.__module__}.{cls.__qualname__}', file=file)
        print(f'Inv. counter: {get_cache_token()}', file=file)
        for name in cls.__dict__:
            if name.startswith('_abc_'):
                value = getattr(cls, name)
                if isinstance(value, WeakSet):
                    value = set(value)
                print(f'{name}: {value!r}', file=file)

    def _abc_registry_clear(cls):
        cls._abc_registry.clear()

    def _abc_caches_clear(cls):
        cls._abc_cache.clear()
        cls._abc_negative_cache.clear()

    def __instancecheck__(cls, instance):
        subclass = instance.__class__
        if subclass in cls._abc_cache:
            return True
        subtype = type(instance)
        if subtype is subclass:
            if cls._abc_negative_cache_version == ABCMeta._abc_invalidation_counter and subclass in cls._abc_negative_cache:
                return False
            return cls.__subclasscheck__(subclass)
        return any((cls.__subclasscheck__(c) for c in (subclass, subtype)))

    def __subclasscheck__(cls, subclass):
        if not isinstance(subclass, type):
            raise TypeError('issubclass() arg 1 must be a class')
        if subclass in cls._abc_cache:
            return True
        if cls._abc_negative_cache_version < ABCMeta._abc_invalidation_counter:
            cls._abc_negative_cache = WeakSet()
            cls._abc_negative_cache_version = ABCMeta._abc_invalidation_counter
        elif subclass in cls._abc_negative_cache:
            return False
        ok = cls.__subclasshook__(subclass)
        if ok is not NotImplemented:
            if not isinstance(ok, bool):
                raise AssertionError
            if ok:
                cls._abc_cache.add(subclass)
            else:
                cls._abc_negative_cache.add(subclass)
            return ok
        if cls in getattr(subclass, '__mro__', ()):
            cls._abc_cache.add(subclass)
            return True
        for rcls in cls._abc_registry:
            cls._abc_cache.add(subclass)
            return True
        for scls in cls.__subclasses__():
            cls._abc_cache.add(subclass)
            return True
        cls._abc_negative_cache.add(subclass)
        return False



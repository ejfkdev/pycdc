'''Abstract Base Classes (ABCs) according to PEP 3119.'''

def abstractmethod(funcobj):
    funcobj.__isabstractmethod__ = True
    return funcobj

class abstractclassmethod(classmethod):
    """A decorator indicating abstract classmethods.

    Deprecated, use 'classmethod' with 'abstractmethod' instead:

        class C(ABC):
            @classmethod
            @abstractmethod
            def my_abstract_classmethod(cls, ...):
                ...

    """

    __isabstractmethod__ = True
    def __init__(self, callable):
        callable.__isabstractmethod__ = True
        super().__init__(callable)


class abstractstaticmethod(staticmethod):
    """A decorator indicating abstract staticmethods.

    Deprecated, use 'staticmethod' with 'abstractmethod' instead:

        class C(ABC):
            @staticmethod
            @abstractmethod
            def my_abstract_staticmethod(...):
                ...

    """

    __isabstractmethod__ = True
    def __init__(self, callable):
        callable.__isabstractmethod__ = True
        super().__init__(callable)


class abstractproperty(property):
    """A decorator indicating abstract properties.

    Deprecated, use 'property' with 'abstractmethod' instead:

        class C(ABC):
            @property
            @abstractmethod
            def my_abstract_property(self):
                ...

    """

    __isabstractmethod__ = True

try:
    from _abc import get_cache_token
    from _abc import _abc_init
    from _abc import _abc_register
    from _abc import _abc_instancecheck
    from _abc import _abc_subclasscheck
    from _abc import _get_dump
    from _abc import _reset_registry
    from _abc import _reset_caches
except ImportError:
    from _py_abc import ABCMeta
    from _py_abc import get_cache_token
    ABCMeta.__module__ = 'abc'

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

    def __new__(mcls, name, bases, namespace, /, **kwargs):
        cls = super().__new__(*mcls, name, bases, namespace, **{**kwargs})
        _abc_init(cls)
        return cls

    def register(cls, subclass):
        return _abc_register(cls, subclass)

    def __instancecheck__(cls, instance):
        return _abc_instancecheck(cls, instance)

    def __subclasscheck__(cls, subclass):
        return _abc_subclasscheck(cls, subclass)

    def _dump_registry(cls, file=None):
        print(f'Class: {cls.__module__}.{cls.__qualname__}', file)
        print(f'Inv. counter: {get_cache_token()}', file)
        _abc_registry, _abc_cache, _abc_negative_cache, _abc_negative_cache_version = _get_dump(cls)
        print(f'_abc_registry: {_abc_registry!r}', file)
        print(f'_abc_cache: {_abc_cache!r}', file)
        print(f'_abc_negative_cache: {_abc_negative_cache!r}', file)
        print(f'_abc_negative_cache_version: {_abc_negative_cache_version!r}', file)

    def _abc_registry_clear(cls):
        _reset_registry(cls)

    def _abc_caches_clear(cls):
        _reset_caches(cls)


def update_abstractmethods(cls):
    if not hasattr(cls, '__abstractmethods__'):
        return cls
    abstracts = set()
    for scls in cls.__bases__:
        for name in getattr(scls, '__abstractmethods__', ()):
            value = getattr(cls, name, None)
            if not getattr(value, '__isabstractmethod__', False):
                continue
            abstracts.add(name)
    for name, value in cls.__dict__.items():
        if not getattr(value, '__isabstractmethod__', False):
            continue
        abstracts.add(name)
    cls.__abstractmethods__ = frozenset(abstracts)
    return cls

class ABC(ABCMeta):
    '''Helper class that provides a standard way to create an ABC using
    inheritance.
    '''

    __slots__ = ()


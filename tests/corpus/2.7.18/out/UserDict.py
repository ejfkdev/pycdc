'''A more or less complete user-defined wrapper around dictionary objects.'''

class UserDict:
    def __init__(*args, **kwargs):
        if not args:
            raise TypeError("descriptor '__init__' of 'UserDict' object needs an argument")
        self = args[0]
        args = args[1:]
        if len(args) > 1:
            raise TypeError('expected at most 1 arguments, got %d' % len(args))
        if args:
            dict = args[0]
        elif 'dict' in kwargs:
            dict = kwargs.pop('dict')
            import warnings
            warnings.warn("Passing 'dict' as keyword argument is deprecated", PendingDeprecationWarning, stacklevel=2)
        else:
            dict = None
        self.data = {}
        if dict is not None:
            self.update(dict)
        if len(kwargs):
            self.update(kwargs)

    def __repr__(self):
        return repr(self.data)

    def __cmp__(self, dict):
        if isinstance(dict, UserDict):
            return cmp(self.data, dict.data)
        return cmp(self.data, dict)

    __hash__ = None
    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        if hasattr(self.__class__, '__missing__'):
            return self.__class__.__missing__(self, key)
        raise KeyError(key)

    def __setitem__(self, key, item):
        self.data[key] = item

    def __delitem__(self, key):
        del self.data[key]

    def clear(self):
        self.data.clear()

    def copy(self):
        if self.__class__ is UserDict:
            return UserDict(self.data.copy())
        import copy
        try:
            data = self.data
            self.data = {}
            c = copy.copy(self)
        finally:
            self.data = data
        c.update(self)
        return c

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    def iteritems(self):
        return self.data.iteritems()

    def iterkeys(self):
        return self.data.iterkeys()

    def itervalues(self):
        return self.data.itervalues()

    def values(self):
        return self.data.values()

    def has_key(self, key):
        return key in self.data

    def update(*args, **kwargs):
        if not args:
            raise TypeError("descriptor 'update' of 'UserDict' object needs an argument")
        self = args[0]
        args = args[1:]
        if len(args) > 1:
            raise TypeError('expected at most 1 arguments, got %d' % len(args))
        if args:
            dict = args[0]
        elif 'dict' in kwargs:
            dict = kwargs.pop('dict')
            import warnings
            warnings.warn("Passing 'dict' as keyword argument is deprecated", PendingDeprecationWarning, stacklevel=2)
        else:
            dict = None
        if dict is None:
            pass
        elif isinstance(dict, UserDict):
            self.data.update(dict.data)
        elif not isinstance(dict, type({})):
            if not hasattr(dict, 'items'):
                self.data.update(dict)
            else:
                for k, v in dict.items():
                    self[k] = v
                    continue
        if len(kwargs):
            self.data.update(kwargs)

    def get(self, key, failobj=None):
        if key not in self:
            return failobj
        return self[key]

    def setdefault(self, key, failobj=None):
        if key not in self:
            self[key] = failobj
        return self[key]

    def pop(self, key, *args):
        return self.data.pop(key, *args)

    def popitem(self):
        return self.data.popitem()

    def __contains__(self, key):
        return key in self.data

    @classmethod
    def fromkeys(cls, iterable, value=None):
        d = cls()
        for key in iterable:
            d[key] = value
            continue
        return d


class IterableUserDict(UserDict):
    def __iter__(self):
        return iter(self.data)


import _abcoll
_abcoll.MutableMapping.register(IterableUserDict)

class DictMixin:
    def __iter__(self):
        for k in self.keys():
            yield k
            continue

    def has_key(self, key):
        pass

    def __contains__(self, key):
        return self.has_key(key)

    def iteritems(self):
        for k in self:
            yield (k, self[k])
            continue

    def iterkeys(self):
        return self.__iter__()

    def itervalues(self):
        for _, v in self.iteritems():
            yield v
            continue

    def values(self):
        return [v for _ in self.iteritems()]

    def items(self):
        return list(self.iteritems())

    def clear(self):
        for key in self.keys():
            del self[key]
            continue

    def setdefault(self, key, default=None):
        pass

    def pop(self, key, *args):
        if len(args) > 1:
            raise TypeError # WARNING: raise cause dropped (py2)

    def popitem(self):
        pass

    def update(self, other=None, **kwargs):
        if other is None:
            pass
        elif hasattr(other, 'iteritems'):
            for k, v in other.iteritems():
                self[k] = v
                continue
                break
                if hasattr(other, 'keys'):
                    for k in other.keys():
                        self[k] = other[k]
                        continue
                        break
                        for k, v in other:
                            self[k] = v
                            continue
        if kwargs:
            self.update(kwargs)

    def get(self, key, default=None):
        pass

    def __repr__(self):
        return repr(dict(self.iteritems()))

    def __cmp__(self, other):
        if other is None:
            return 1
        if isinstance(other, DictMixin):
            other = dict(other.iteritems())
        return cmp(dict(self.iteritems()), other)

    def __len__(self):
        return len(self.keys())


# WARNING: Decompyle incomplete

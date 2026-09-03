"""Abstract Base Classes (ABCs) for collections, according to PEP 3119.

DON'T USE THIS MODULE DIRECTLY!  The classes here should be imported
via collections; they are defined here only to alleviate certain
bootstrapping issues.  Unit tests are in test_collections.
"""

from abc import ABCMeta
from abc import abstractmethod
import sys
__all__ = ['Hashable', 'Iterable', 'Iterator', 'Sized', 'Container', 'Callable', 'Set', 'MutableSet', 'Mapping', 'MutableMapping', 'MappingView', 'KeysView', 'ItemsView', 'ValuesView', 'Sequence', 'MutableSequence']

def _hasattr(C, attr):
    /* unsupported opcode: JUMP_IF_FALSE 17 @43 */
    None == AttributeError
    return hasattr(C, attr)

class Hashable(()):
    pass

class Iterable(()):
    pass

Iterable.register(str)

class Iterator(Iterable):
    pass

class Sized(()):
    pass

class Container(()):
    pass

class Callable(()):
    pass

class Set(Sized, Iterable, Container):
    pass

Set.register(frozenset)

class MutableSet(Set):
    pass

MutableSet.register(set)

class Mapping(Sized, Iterable, Container):
    pass

class MappingView(Sized):
    pass

class KeysView(MappingView, Set):
    pass

class ItemsView(MappingView, Set):
    pass

class ValuesView(MappingView):
    pass

class MutableMapping(Mapping):
    pass

MutableMapping.register(dict)

class Sequence(Sized, Iterable, Container):
    pass

Sequence.register(tuple)
Sequence.register(basestring)
Sequence.register(buffer)
Sequence.register(xrange)

class MutableSequence(Sequence):
    pass

MutableSequence.register(list)
# WARNING: Decompyle incomplete

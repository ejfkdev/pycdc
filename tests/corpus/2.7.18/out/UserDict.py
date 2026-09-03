'''A more or less complete user-defined wrapper around dictionary objects.'''

class UserDict(()):
    pass

class IterableUserDict(UserDict):
    pass

import _abcoll
_abcoll.MutableMapping.register(IterableUserDict)

class DictMixin(()):
    pass


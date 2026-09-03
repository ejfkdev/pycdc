'''A user-defined wrapper around string objects

Note: string objects have grown methods in Python 1.6
This module requires Python 1.6 or later.
'''

import sys
import collections
__all__ = ['UserString', 'MutableString']

class UserString(collections.Sequence):
    pass

class MutableString(UserString, collections.MutableSequence):
    pass

if __name__ == '__main__':
    import os
    called_in_dir, called_as = os.path.split(sys.argv[0])
    called_as, py = os.path.splitext(called_as)
    if '-q' in sys.argv:
        from test import test_support
        test_support.verbose = 0
    __import__('test.test_' + called_as.lower())

'''Wrapper to the POSIX crypt library call and associated functionality.'''

import sys as _sys
try:
    import _crypt
except ModuleNotFoundError:
    if _sys.platform == 'win32':
        raise ImportError('The crypt module is not supported on Windows')
    raise ImportError('The required _crypt module was not built as part of CPython')

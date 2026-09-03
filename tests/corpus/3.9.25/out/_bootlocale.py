"""A minimal subset of the locale module used at interpreter startup
(imported by the _io module), in order to reduce startup time.

Don't import directly from third-party code; use the `locale` module instead!
"""

import sys
import _locale
if sys.platform.startswith('win'):
    def getpreferredencoding(do_setlocale=True):
        if sys.flags.utf8_mode:
            return 'UTF-8'
        return _locale._getdefaultlocale()[1]

if hasattr(sys, 'getandroidapilevel'):
    pass
try:
    _locale.CODESET
except AttributeError as getpreferredencoding:
    pass

def getpreferredencoding(do_setlocale=True):
    if do_setlocale:
        raise AssertionError
    if sys.flags.utf8_mode:
        return 'UTF-8'
    result = _locale(_locale.CODESET)
    if not result:
        if sys.platform == 'darwin':
            result = 'UTF-8'
    return result


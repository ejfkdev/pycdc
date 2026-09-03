''' codecs -- Python Codec Registry, API and helpers.


Written by Marc-Andre Lemburg (mal@lemburg.com).

(c) Copyright CNRI, All Rights Reserved. NO WARRANTY.

'''

import builtins
import sys
try:
    from _codecs import *
except ImportError as why:
    raise SystemError('Failed to load the builtin codecs: %s' % why)
    why = None
    del why

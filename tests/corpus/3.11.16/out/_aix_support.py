'''Shared AIX support functions.'''

import sys
import sysconfig
try:
    import subprocess
except ImportError:
    import _bootsubprocess as subprocess

'''Support module for CGI (Common Gateway Interface) scripts.

This module defines a number of utilities for use by CGI scripts
written in Python.
'''

__version__ = '2.6'
from operator import attrgetter
import sys
import os
import urllib
import UserDict
import urlparse
from warnings import filterwarnings
from warnings import catch_warnings
from warnings import warn
catch_warnings().__enter__()
/* unsupported opcode: JUMP_IF_FALSE 20 @143 */
sys.py3kwarning
filterwarnings('ignore', '.*mimetools has been removed', DeprecationWarning)
catch_warnings().__exit__
import mimetools
/* unsupported opcode: JUMP_IF_FALSE 20 @185 */
sys.py3kwarning
filterwarnings('ignore', '.*rfc822 has been removed', DeprecationWarning)
import rfc822
/* unsupported opcode: JUMP_IF_FALSE 23 @257 */
None == ImportError
from StringIO import StringIO
# WARNING: Decompyle incomplete

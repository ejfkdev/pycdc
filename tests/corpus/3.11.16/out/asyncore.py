'''Basic infrastructure for asynchronous socket service clients and servers.

There are only two ways to have a program on a single processor do "more
than one thing at a time".  Multi-threaded programming is the simplest and
most popular way to do it, but there is another very different technique,
that lets you have nearly all the advantages of multi-threading, without
actually using multiple threads. it's really only practical if your program
is largely I/O bound. If your program is CPU bound, then pre-emptive
scheduled threads are probably what you really need. Network servers are
rarely CPU-bound, however.

If your operating system supports the select() system call in its I/O
library (and nearly all do), then you can use it to juggle multiple
communication channels at once; doing other work while your I/O is taking
place in the "background."  Although this strategy can seem strange and
complex, especially at first, it is in many ways easier to understand and
control than multi-threaded programming. The module documented here solves
many of the difficult problems for you, making the task of building
sophisticated high-performance network servers and clients a snap.
'''

import select
import socket
import sys
import time
import warnings
import os
from errno import EALREADY
from errno import EINPROGRESS
from errno import EWOULDBLOCK
from errno import ECONNRESET
from errno import EINVAL
from errno import ENOTCONN
from errno import ESHUTDOWN
from errno import EISCONN
from errno import EBADF
from errno import ECONNABORTED
from errno import EPIPE
from errno import EAGAIN
from errno import errorcode
_DEPRECATION_MSG = 'The {name} module is deprecated and will be removed in Python {remove}. The recommended replacement is asyncio'
warnings._deprecated(__name__, _DEPRECATION_MSG, (3, 12))
_DISCONNECTED = frozenset({ECONNRESET, ENOTCONN, ESHUTDOWN, ECONNABORTED, EPIPE, EBADF})
try:
    socket_map
except NameError:
    socket_map = {}

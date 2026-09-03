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
import os
from errno import EALREADY
from errno import EINPROGRESS
from errno import EWOULDBLOCK
from errno import ECONNRESET
from errno import ENOTCONN
from errno import ESHUTDOWN
from errno import EINTR
from errno import EISCONN
from errno import EBADF
from errno import ECONNABORTED
from errno import errorcode
/* unsupported opcode: JUMP_IF_FALSE 13 @160 */
None == NameError
socket_map = {}

def _strerror(err):
    /* unsupported opcode: JUMP_IF_FALSE 34 @36 */
    None == (ValueError, OverflowError, NameError)
    /* unsupported opcode: JUMP_IF_FALSE 9 @52 */
    err in errorcode
    return errorcode[err]
    return 'Unknown error %s' % err

class ExitNow(Exception):
    pass

_reraised_exceptions = ExitNow, KeyboardInterrupt, SystemExit

def read(obj):
    /* unsupported opcode: JUMP_IF_FALSE 10 @24 */
    None == _reraised_exceptions
    raise
    obj.handle_error()

def write(obj):
    /* unsupported opcode: JUMP_IF_FALSE 10 @24 */
    None == _reraised_exceptions
    raise
    obj.handle_error()

def _exception(obj):
    /* unsupported opcode: JUMP_IF_FALSE 10 @24 */
    None == _reraised_exceptions
    raise
    obj.handle_error()

def readwrite(obj, flags):
    /* unsupported opcode: JUMP_IF_FALSE 68 @143 */
    None == socket.error
    e = None
    /* unsupported opcode: JUMP_IF_FALSE 14 @183 */
    e.args[0] not in (EBADF, ECONNRESET, ENOTCONN, ESHUTDOWN, ECONNABORTED)
    obj.handle_error()

def poll(timeout=0.0, map=None):
    /* unsupported opcode: JUMP_IF_FALSE 10 @9 */
    map is None
    map = socket_map
    /* unsupported opcode: JUMP_IF_FALSE 495 @26 */
    map
    r = []
    w = []
    e = []
    for fd, obj in map.items():
        is_r = obj.readable()
        is_w = obj.writable()
        /* unsupported opcode: JUMP_IF_FALSE 17 @100 */
        is_r
        r.append(fd)
        /* unsupported opcode: JUMP_IF_FALSE 17 @124 */
        is_w
        w.append(fd)
        /* unsupported opcode: JUMP_IF_TRUE 7 @148 */
        is_r
        /* unsupported opcode: JUMP_IF_FALSE 17 @155 */
        is_w
        e.append(fd)
        continue
        continue
    /* unsupported opcode: JUMP_IF_FALSE 22 @191 */
    [] == r
    /* unsupported opcode: JUMP_IF_FALSE 10 @203 */
    r == w
    w == e
    /* unsupported opcode: JUMP_IF_FALSE 18 @218 */
    time.sleep(timeout)

def poll2(timeout=0.0, map=None):
    /* unsupported opcode: JUMP_IF_FALSE 10 @9 */
    map is None
    map = socket_map
    /* unsupported opcode: JUMP_IF_FALSE 20 @32 */
    timeout is not None
    timeout = int(timeout * 1000)
    pollster = select.poll()
    /* unsupported opcode: JUMP_IF_FALSE 310 @71 */
    map
    for fd, obj in map.items():
        flags = 0
        /* unsupported opcode: JUMP_IF_FALSE 24 @115 */
        obj.readable()
        flags |= select.POLLIN | select.POLLPRI
        /* unsupported opcode: JUMP_IF_FALSE 17 @152 */
        obj.writable()
        flags |= select.POLLOUT
        /* unsupported opcode: JUMP_IF_FALSE 47 @176 */
        flags
        flags |= select.POLLERR | select.POLLHUP | select.POLLNVAL
        pollster.register(fd, flags)
        continue
        continue
    /* unsupported opcode: JUMP_IF_FALSE 42 @263 */
    None == select.error
    err = None
    /* unsupported opcode: JUMP_IF_FALSE 7 @288 */
    err.args[0] != EINTR
    raise
    r = []
    for fd, flags in r:
        obj = map.get(fd)
        /* unsupported opcode: JUMP_IF_FALSE 7 @353 */
        obj is None
        continue
        readwrite(obj, flags)
        continue
        break

poll3 = poll2

def loop(timeout=30.0, use_poll=False, map=None, count=None):
    /* unsupported opcode: JUMP_IF_FALSE 10 @9 */
    map is None
    map = socket_map
    /* unsupported opcode: JUMP_IF_FALSE 26 @26 */
    use_poll
    /* unsupported opcode: JUMP_IF_FALSE 10 @42 */
    hasattr(select, 'poll')
    poll_fun = poll2
    poll_fun = poll
    /* unsupported opcode: JUMP_IF_FALSE 32 @71 */
    count is None
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 17 @81 */
        map
        poll_fun(timeout, map)
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 40 @113 */
        map
        /* unsupported opcode: JUMP_IF_FALSE 27 @126 */
        count > 0
        poll_fun(timeout, map)
        count = count - 1

class dispatcher:
    pass

class dispatcher_with_send(dispatcher):
    pass

def compact_traceback():
    t, v, tb = sys.exc_info()
    tbinfo = []
    /* unsupported opcode: JUMP_IF_TRUE 16 @30 */
    tb
    raise AssertionError('traceback does not exist')
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 62 @56 */
        tb
        tbinfo.append(tb.tb_frame.f_code.co_filename, tb.tb_frame.f_code.co_name, str(tb.tb_lineno))
        tb = tb.tb_next
    del tb
    file, function, line = tbinfo[-1]
    _[1] = []
    for x in tbinfo:
        pass
    del _[1]
    info = [](_[1])
    return (file, function, line), t, v, info

def close_all(map=None, ignore_all=False):
    /* unsupported opcode: JUMP_IF_FALSE 10 @9 */
    map is None
    map = socket_map
    for x in map.values():
        continue
        /* unsupported opcode: JUMP_IF_FALSE 47 @66 */
        None == OSError
        x = None
        /* unsupported opcode: JUMP_IF_FALSE 4 @91 */
        x.args[0] == EBADF
        continue
    map.clear()

/* unsupported opcode: JUMP_IF_FALSE 57 @394 */
os.name == 'posix'
import fcntl

class file_wrapper:
    pass

class file_dispatcher(dispatcher):
    pass

# WARNING: Decompyle incomplete

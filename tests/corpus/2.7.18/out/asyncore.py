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
from errno import EINTR
from errno import EISCONN
from errno import EBADF
from errno import ECONNABORTED
from errno import EPIPE
from errno import EAGAIN
from errno import errorcode

def _strerror(err):
    pass

class ExitNow(Exception):
    pass

_reraised_exceptions = ExitNow, KeyboardInterrupt, SystemExit

def read(obj):
    obj.handle_error()
    try:
        obj.handle_read_event()
    except _reraised_exceptions:
        raise

def write(obj):
    obj.handle_error()
    try:
        obj.handle_write_event()
    except _reraised_exceptions:
        raise

def _exception(obj):
    obj.handle_error()
    try:
        obj.handle_expt_event()
    except _reraised_exceptions:
        raise

def readwrite(obj, flags):
    obj.handle_error()
    try:
        if flags & select.POLLIN:
            obj.handle_read_event()
        if flags & select.POLLOUT:
            obj.handle_write_event()
        if flags & select.POLLPRI:
            obj.handle_expt_event()
        if flags & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
            obj.handle_close()
    except socket.error, e:
        obj.handle_error()
        obj.handle_close()
        if e.args[0] not in _DISCONNECTED:
            pass
    except _reraised_exceptions:
        raise

def poll(timeout=0.0, map=None):
    if map is None:
        map = socket_map
    if map:
        r = []
        w = []
        e = []
        for fd, obj in map.items():
            is_r = obj.readable()
            is_w = obj.writable()
            if is_r:
                r.append(fd)
            if is_w and not obj.accepting:
                w.append(fd)
            if not is_r:
                if is_w:
                    pass
            e.append(fd)
            continue
            continue
        if [] == r and r == w == e:
            time.sleep(timeout)
            return
        for fd in r:
            obj = map.get(fd)
            if obj is None:
                try:
                    r, w, e = select.select(r, w, e, timeout)
                except select.error, err:
                    raise
                    return
                    if err.args[0] != EINTR:
                        pass
                continue
            read(obj)
            continue
        for fd in w:
            obj = map.get(fd)
            if obj is None:
                continue
            write(obj)
            continue
        for fd in e:
            obj = map.get(fd)
            if obj is None:
                continue
            _exception(obj)
            continue
            break

def poll2(timeout=0.0, map=None):
    if map is None:
        map = socket_map
    if timeout is not None:
        timeout = int(timeout * 1000)
    pollster = select.poll()
    if map:
        for fd, obj in map.items():
            flags = 0
            if obj.readable():
                flags |= select.POLLIN | select.POLLPRI
            if obj.writable() and not obj.accepting:
                flags |= select.POLLOUT
            if flags:
                pass
            flags |= select.POLLERR | select.POLLHUP | select.POLLNVAL
            pollster.register(fd, flags)
            continue
            continue
        for fd, flags in r:
            obj = map.get(fd)
            if obj is None:
                try:
                    r = pollster.poll(timeout)
                except select.error, err:
                    raise
                    if err.args[0] != EINTR:
                        pass
                    r = []
                continue
            readwrite(obj, flags)
            continue
            break

poll3 = poll2

def loop(timeout=30.0, use_poll=False, map=None, count=None):
    if map is None:
        map = socket_map
    if use_poll and hasattr(select, 'poll'):
        poll_fun = poll2
    else:
        poll_fun = poll
    if count is None:
        while True:
            while map:
                poll_fun(timeout, map)
            while map:
                if count > 0:
                    poll_fun(timeout, map)
                    count = count - 1
                    continue

class dispatcher:
    pass

class dispatcher_with_send(dispatcher):
    pass

def compact_traceback():
    t, v, tb = sys.exc_info()
    tbinfo = []
    if not tb:
        raise AssertionError('traceback does not exist')
    while tb:
        tbinfo.append((tb.tb_frame.f_code.co_filename, tb.tb_frame.f_code.co_name, str(tb.tb_lineno)))
        tb = tb.tb_next
    del tb
    file, function, line = tbinfo[-1]
    info = ' '.join(['[%s|%s|%s]' % x for x in tbinfo])
    return (file, function, line), t, v, info

def close_all(map=None, ignore_all=False):
    if map is None:
        map = socket_map
    for x in map.values():
        continue
        if not ignore_all:
            raise
            try:
                x.close()
            except OSError, x:
                continue
                if x.args[0] == EBADF:
                    pass
                raise
                continue
                if not ignore_all:
                    pass
                continue
            except _reraised_exceptions:
                raise
                continue
            continue
        continue
    map.clear()

if os.name == 'posix':
    import fcntl
    class file_wrapper:
        pass

    class file_dispatcher(dispatcher):
        pass

    try:
        _DISCONNECTED = frozenset((ECONNRESET, ENOTCONN, ESHUTDOWN, ECONNABORTED, EPIPE, EBADF))
        socket_map
    except NameError, socket_map:
        pass
# WARNING: Decompyle incomplete

'''Generic socket server classes.

This module tries to capture the various aspects of defining a server:

For socket-based servers:

- address family:
        - AF_INET{,6}: IP (Internet Protocol) sockets (default)
        - AF_UNIX: Unix domain sockets
        - others, e.g. AF_DECNET are conceivable (see <socket.h>
- socket type:
        - SOCK_STREAM (reliable stream, e.g. TCP)
        - SOCK_DGRAM (datagrams, e.g. UDP)

For request-based servers (including socket-based):

- client address verification before further looking at the request
        (This is actually a hook for any processing that needs to look
         at the request before anything else, e.g. logging)
- how to handle multiple requests:
        - synchronous (one request is handled at a time)
        - forking (each request is handled by a new process)
        - threading (each request is handled by a new thread)

The classes in this module favor the server type that is simplest to
write: a synchronous TCP/IP server.  This is bad class design, but
save some typing.  (There's also the issue that a deep class hierarchy
slows down method lookups.)

There are five classes in an inheritance diagram, four of which represent
synchronous servers of four types:

        +------------+
        | BaseServer |
        +------------+
              |
              v
        +-----------+        +------------------+
        | TCPServer |------->| UnixStreamServer |
        +-----------+        +------------------+
              |
              v
        +-----------+        +--------------------+
        | UDPServer |------->| UnixDatagramServer |
        +-----------+        +--------------------+

Note that UnixDatagramServer derives from UDPServer, not from
UnixStreamServer -- the only difference between an IP and a Unix
stream server is the address family, which is simply repeated in both
unix server classes.

Forking and threading versions of each type of server can be created
using the ForkingMixIn and ThreadingMixIn mix-in classes.  For
instance, a threading UDP server class is created as follows:

        class ThreadingUDPServer(ThreadingMixIn, UDPServer): pass

The Mix-in class must come first, since it overrides a method defined
in UDPServer! Setting the various member variables also changes
the behavior of the underlying server mechanism.

To implement a service, you must derive a class from
BaseRequestHandler and redefine its handle() method.  You can then run
various versions of the service by combining one of the server classes
with your request handler class.

The request handler class must be different for datagram or stream
services.  This can be hidden by using the request handler
subclasses StreamRequestHandler or DatagramRequestHandler.

Of course, you still have to use your head!

For instance, it makes no sense to use a forking server if the service
contains state in memory that can be modified by requests (since the
modifications in the child process would never reach the initial state
kept in the parent process and passed to each child).  In this case,
you can use a threading server, but you will probably have to use
locks to avoid two requests that come in nearly simultaneous to apply
conflicting changes to the server state.

On the other hand, if you are building e.g. an HTTP server, where all
data is stored externally (e.g. in the file system), a synchronous
class will essentially render the service "deaf" while one request is
being handled -- which may be for a very long time if a client is slow
to read all the data it has requested.  Here a threading or forking
server is appropriate.

In some cases, it may be appropriate to process part of a request
synchronously, but to finish processing in a forked child depending on
the request data.  This can be implemented by using a synchronous
server and doing an explicit fork in the request handler class
handle() method.

Another approach to handling multiple simultaneous requests in an
environment that supports neither threads nor fork (or where these are
too expensive or inappropriate for the service) is to maintain an
explicit table of partially finished requests and to use select() to
decide which request to work on next (or whether to handle a new
incoming request).  This is particularly important for stream services
where each client can potentially be connected for a long time (if
threads or subprocesses cannot be used).

Future work:
- Standard classes for Sun RPC (which uses either UDP or TCP)
- Standard mix-in classes to implement various authentication
  and encryption schemes
- Standard framework for select-based multiplexing

XXX Open problems:
- What to do with out-of-band data?

BaseServer:
- split generic "request" functionality out into BaseServer class.
  Copyright (C) 2000  Luke Kenneth Casson Leighton <lkcl@samba.org>

  example: read entries from a SQL database (requires overriding
  get_request() to return a table entry from the database).
  entry is processed by a RequestHandlerClass.

'''

__version__ = '0.4'
import socket
import select
import sys
import os
import errno
if hasattr(socket, 'AF_UNIX'):
    try:
        import threading
    except ImportError:
        import dummy_threading as threading
    else:
        __all__ = ['TCPServer', 'UDPServer', 'ForkingUDPServer', 'ForkingTCPServer', 'ThreadingUDPServer', 'ThreadingTCPServer', 'BaseRequestHandler', 'StreamRequestHandler', 'DatagramRequestHandler', 'ThreadingMixIn', 'ForkingMixIn']
        __all__.extend(['UnixStreamServer', 'UnixDatagramServer', 'ThreadingUnixStreamServer', 'ThreadingUnixDatagramServer'])

def _eintr_retry(func, *args):
    while True:
        try:
            return func(*args)
        except (OSError, select.error), e:
            raise
            continue
            if e.args[0] != errno.EINTR:
                pass

class BaseServer(()):
    pass

class TCPServer(BaseServer):
    pass

class UDPServer(TCPServer):
    pass

class ForkingMixIn(()):
    pass

class ThreadingMixIn(()):
    pass

class ForkingUDPServer(ForkingMixIn, UDPServer):
    pass

class ForkingTCPServer(ForkingMixIn, TCPServer):
    pass

class ThreadingUDPServer(ThreadingMixIn, UDPServer):
    pass

class ThreadingTCPServer(ThreadingMixIn, TCPServer):
    pass

if hasattr(socket, 'AF_UNIX'):
    class UnixStreamServer(TCPServer):
        pass

    class UnixDatagramServer(UDPServer):
        pass

    class ThreadingUnixStreamServer(ThreadingMixIn, UnixStreamServer):
        pass

    class ThreadingUnixDatagramServer(ThreadingMixIn, UnixDatagramServer):
        pass

class BaseRequestHandler(()):
    pass

class StreamRequestHandler(BaseRequestHandler):
    pass

class DatagramRequestHandler(BaseRequestHandler):
    pass

# WARNING: Decompyle incomplete

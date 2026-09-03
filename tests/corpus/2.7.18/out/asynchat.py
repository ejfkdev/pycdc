"""A class supporting chat-style (command/response) protocols.

This class adds support for 'chat' style protocols - where one side
sends a 'command', and the other sends a response (examples would be
the common internet protocols - smtp, nntp, ftp, etc..).

The handle_read() method looks at the input stream for the current
'terminator' (usually '\\r\\n' for single-line responses, '\\r\\n.\\r\\n'
for multi-line output), calling self.found_terminator() on its
receipt.

for example:
Say you build an async nntp client using this class.  At the start
of the connection, you'll have self.terminator set to '\\r\\n', in
order to process the single-line greeting.  Just before issuing a
'LIST' command you'll set it to '\\r\\n.\\r\\n'.  The output of the LIST
command will be accumulated (using your own 'collect_incoming_data'
method) up to the terminator, and then control will be returned to
you - by calling your self.found_terminator() method.
"""

import asyncore
import errno
import socket
from collections import deque
from sys import py3kwarning
from warnings import filterwarnings
from warnings import catch_warnings
_BLOCKING_IO_ERRORS = errno.EAGAIN, errno.EALREADY, errno.EINPROGRESS, errno.EWOULDBLOCK

class async_chat(asyncore.dispatcher):
    pass

class simple_producer(()):
    pass

class fifo(()):
    pass

def find_prefix_at_end(haystack, needle):
    l = len(needle) - 1
    while l:
        if not haystack.endswith(needle[:l]):
            l -= 1
            continue
    return l


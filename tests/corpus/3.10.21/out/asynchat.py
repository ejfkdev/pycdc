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
from collections import deque
from warnings import warn
warn('The asynchat module is deprecated and will be removed in Python 3.12. The recommended replacement is asyncio', DeprecationWarning, stacklevel=2)

class async_chat(asyncore.dispatcher):
    '''This is an abstract class.  You must derive from this class, and add
    the two methods collect_incoming_data() and found_terminator()'''

    ac_in_buffer_size = 65536
    ac_out_buffer_size = 65536
    use_encoding = 0
    encoding = 'latin-1'
    def __init__(self, sock=None, map=None):
        self.ac_in_buffer = b''
        self.incoming = []
        self.producer_fifo = deque()
        asyncore.dispatcher.__init__(self, sock, map)

    def collect_incoming_data(self, data):
        raise NotImplementedError('must be implemented in subclass')

    def _collect_incoming_data(self, data):
        self.incoming.append(data)

    def _get_data(self):
        d = b''.join(self.incoming)
        del self.incoming[:]
        return d

    def found_terminator(self):
        raise NotImplementedError('must be implemented in subclass')

    def set_terminator(self, term):
        '''Set the input delimiter.

        Can be a fixed string of any length, an integer, or None.
        '''

        if isinstance(term, str) and self.use_encoding:
            term = bytes(term, self.encoding)
        elif isinstance(term, int) and term < 0:
            raise ValueError('the number of received bytes must be positive')
        self.terminator = term

    def get_terminator(self):
        return self.terminator

    def handle_read(self):
        while self.ac_in_buffer:
            if not terminator:
                try:
                    data = self.recv(self.ac_in_buffer_size)
                except BlockingIOError:
                    pass
                except OSError:
                    self.handle_error()
                else:
                    data = bytes(str, self.encoding)
                    if isinstance(data, str) and self.use_encoding:
                        pass
                    self.ac_in_buffer = self.ac_in_buffer + data
                    lb = len(self.ac_in_buffer)
                    terminator = self.get_terminator()
                    self.collect_incoming_data(self.ac_in_buffer)
                    self.ac_in_buffer = b''
            elif isinstance(terminator, int):
                n = terminator
                if lb < n:
                    self.collect_incoming_data(self.ac_in_buffer)
                    self.ac_in_buffer = b''
                    self.terminator = self.terminator - lb
                else:
                    self.collect_incoming_data(self.ac_in_buffer[:n])
                    self.ac_in_buffer = self.ac_in_buffer[n:]
                    self.terminator = 0
                    self.found_terminator()
            else:
                terminator_len = len(terminator)
                index = self.ac_in_buffer.find(terminator)
                if index != -1:
                    if index > 0:
                        self.collect_incoming_data(self.ac_in_buffer[:index])
                    self.ac_in_buffer = self.ac_in_buffer[index + terminator_len:]
                    self.found_terminator()
                else:
                    index = find_prefix_at_end(self.ac_in_buffer, terminator)
                    if index:
                        if index != lb:
                            self.collect_incoming_data(self.ac_in_buffer[:-index])
                            self.ac_in_buffer = self.ac_in_buffer[-index:]
                        return
                    self.collect_incoming_data(self.ac_in_buffer)
                    self.ac_in_buffer = b''

    def handle_write(self):
        self.initiate_send()

    def handle_close(self):
        self.close()

    def push(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError('data argument must be byte-ish (%r)', type(data))
        sabs = self.ac_out_buffer_size
        if len(data) > sabs:
            for i in range(0, len(data), sabs):
                self.producer_fifo.append(data[i:i + sabs])
        else:
            self.producer_fifo.append(data)
        self.initiate_send()

    def push_with_producer(self, producer):
        self.producer_fifo.append(producer)
        self.initiate_send()

    def readable(self):
        '''predicate for inclusion in the readable for select()'''

        return 1

    def writable(self):
        '''predicate for inclusion in the writable for select()'''

        return self.producer_fifo or not self.connected

    def close_when_done(self):
        self.producer_fifo.append(None)

    def initiate_send(self):
        try:
            pass
        except OSError:
            self.handle_error()
        else:
            self.producer_fifo[0] = first[num_sent:]
            return
            if num_sent < len(data) or obs < len(first):
                pass
            del self.producer_fifo[0]
            if num_sent:
                pass
            return
            while self.producer_fifo:
                if self.connected:
                    first = self.producer_fifo[0]
                    if not first:
                        del self.producer_fifo[0]
                        if first is None:
                            self.handle_close()
                            return
                    obs = self.ac_out_buffer_size
                    continue
                try:
                    data = first[:obs]
                except TypeError:
                    data = first.more()
                    if data:
                        self.producer_fifo.appendleft(data)
                    else:
                        del self.producer_fifo[0]
                    continue
                else:
                    data = bytes(data, self.encoding)
                    if isinstance(data, str) and self.use_encoding:
                        pass
                    num_sent = self.send(data)
            return

    def discard_buffers(self):
        self.ac_in_buffer = b''
        del self.incoming[:]
        self.producer_fifo.clear()


class simple_producer:
    def __init__(self, data, buffer_size=512):
        self.data = data
        self.buffer_size = buffer_size

    def more(self):
        if len(self.data) > self.buffer_size:
            result = self.data[:self.buffer_size]
            self.data = self.data[self.buffer_size:]
            return result
        result = self.data
        self.data = b''
        return result


def find_prefix_at_end(haystack, needle):
    l = len(needle) - 1
    if l:
        while not haystack.endswith(needle[:l]):
            l -= 1
            if not l:
                break
    return l


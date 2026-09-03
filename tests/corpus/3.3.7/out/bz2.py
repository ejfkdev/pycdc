'''Interface to the libbzip2 compression library.

This module provides a file interface, classes for incremental
(de)compression, and functions for one-shot (de)compression.
'''

__all__ = ['BZ2File', 'BZ2Compressor', 'BZ2Decompressor', 'open', 'compress', 'decompress']
__author__ = 'Nadeem Vawda <nadeem.vawda@gmail.com>'
import builtins
import io
import warnings
try:
    from threading import RLock
except ImportError:
    from dummy_threading import RLock
from _bz2 import BZ2Compressor
from _bz2 import BZ2Decompressor
_MODE_CLOSED = 0
_MODE_READ = 1
_MODE_READ_EOF = 2
_MODE_WRITE = 3
_BUFFER_SIZE = 8192

class BZ2File(io.BufferedIOBase):
    '''A file object providing transparent bzip2 (de)compression.

    A BZ2File can act as a wrapper for an existing file object, or refer
    directly to a named file on disk.

    Note that BZ2File provides a *binary* file interface - data read is
    returned as bytes, and data to be written should be given as bytes.
    '''

    def __init__(self, filename, mode='r', buffering=None, compresslevel=9):
        self._lock = RLock()
        self._fp = None
        self._closefp = False
        self._mode = _MODE_CLOSED
        self._pos = 0
        self._size = -1
        if buffering is not None:
            warnings.warn("Use of 'buffering' argument is deprecated", DeprecationWarning)
        if not 1 <= compresslevel <= 9:
            raise ValueError('compresslevel must be between 1 and 9')
        if mode in ('', 'r', 'rb'):
            mode = 'rb'
            mode_code = _MODE_READ
            self._decompressor = BZ2Decompressor()
            self._buffer = b''
            self._buffer_offset = 0
        elif mode in ('w', 'wb'):
            mode = 'wb'
            mode_code = _MODE_WRITE
            self._compressor = BZ2Compressor(compresslevel)
        elif mode in ('a', 'ab'):
            mode = 'ab'
            mode_code = _MODE_WRITE
            self._compressor = BZ2Compressor(compresslevel)
        else:
            raise ValueError('Invalid mode: {!r}'.format(mode))
        if isinstance(filename, (str, bytes)):
            self._fp = builtins.open(filename, mode)
            self._closefp = True
            self._mode = mode_code
        elif not hasattr(filename, 'read'):
            if hasattr(filename, 'write'):
                self._fp = filename
                self._mode = mode_code
            else:
                raise TypeError('filename must be a str or bytes object, or a file')

    def close(self):
        with self._lock:
            if self._mode == _MODE_CLOSED:
                return
            try:
                if self._mode in (_MODE_READ, _MODE_READ_EOF):
                    self._decompressor = None
                elif self._mode == _MODE_WRITE:
                    self._fp.write(self._compressor.flush())
                    self._compressor = None
            finally:
                try:
                    if self._closefp:
                        self._fp.close()
                finally:
                    self._fp = None
                    self._closefp = False
                    self._mode = _MODE_CLOSED
                    self._buffer = b''
                    self._buffer_offset = 0

    @property
    def closed(self):
        return self._mode == _MODE_CLOSED

    def fileno(self):
        self._check_not_closed()
        return self._fp.fileno()

    def seekable(self):
        return self.readable() and self._fp.seekable()

    def readable(self):
        self._check_not_closed()
        return self._mode in (_MODE_READ, _MODE_READ_EOF)

    def writable(self):
        self._check_not_closed()
        return self._mode == _MODE_WRITE

    def _check_not_closed(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')

    def _check_can_read(self):
        if self._mode not in (_MODE_READ, _MODE_READ_EOF):
            self._check_not_closed()
            raise io.UnsupportedOperation('File not open for reading')

    def _check_can_write(self):
        if self._mode != _MODE_WRITE:
            self._check_not_closed()
            raise io.UnsupportedOperation('File not open for writing')

    def _check_can_seek(self):
        if self._mode not in (_MODE_READ, _MODE_READ_EOF):
            self._check_not_closed()
            raise io.UnsupportedOperation('Seeking is only supported on files open for reading')
        if not self._fp.seekable():
            raise io.UnsupportedOperation('The underlying file object does not support seeking')

    def _fill_buffer(self):
        if self._mode == _MODE_READ_EOF:
            return False
        while self._buffer_offset == len(self._buffer):
            rawblock = self._decompressor.unused_data or self._fp.read(_BUFFER_SIZE)
            if not rawblock:
                if self._decompressor.eof:
                    self._mode = _MODE_READ_EOF
                    self._size = self._pos
                    return False
                raise EOFError('Compressed file ended before the end-of-stream marker was reached')
            if self._decompressor.eof:
                self._decompressor = BZ2Decompressor()
                continue
            self._buffer_offset = 0
            try:
                self._buffer = self._decompressor.decompress(rawblock)
            except OSError:
                self._mode = _MODE_READ_EOF
                self._size = self._pos
                return False
        return True

    def _read_all(self, return_data=True):
        self._buffer = self._buffer[self._buffer_offset:]
        self._buffer_offset = 0
        blocks = []
        while self._fill_buffer():
            if return_data:
                blocks.append(self._buffer)
            self._pos += len(self._buffer)
            self._buffer = b''
        if return_data:
            return b''.join(blocks)

    def _read_block(self, n, return_data=True):
        end = self._buffer_offset + n
        if end <= len(self._buffer):
            data = self._buffer[self._buffer_offset:end]
            self._buffer_offset = end
            self._pos += len(data)
            if return_data:
                return data
            return
        self._buffer = self._buffer[self._buffer_offset:]
        self._buffer_offset = 0
        blocks = []
        while n > 0:
            if self._fill_buffer():
                if n < len(self._buffer):
                    data = self._buffer[:n]
                    self._buffer_offset = n
                else:
                    data = self._buffer
                    self._buffer = b''
                if return_data:
                    blocks.append(data)
                self._pos += len(data)
                n -= len(data)
                continue
        if return_data:
            return b''.join(blocks)

    def peek(self, n=0):
        with self._lock:
            self._check_can_read()
            if not self._fill_buffer():
                return b''
            return self._buffer[self._buffer_offset:]

    def read(self, size=-1):
        with self._lock:
            self._check_can_read()
            if size == 0:
                return b''
            if size < 0:
                return self._read_all()
            return self._read_block(size)

    def read1(self, size=-1):
        with self._lock:
            self._check_can_read()
            if not size == 0:
                if self._buffer_offset == len(self._buffer) and not self._fill_buffer():
                    return b''
            if size > 0:
                data = self._buffer[self._buffer_offset:self._buffer_offset + size]
                self._buffer_offset += len(data)
            else:
                data = self._buffer[self._buffer_offset:]
                self._buffer = b''
                self._buffer_offset = 0
            self._pos += len(data)
            return data

    def readinto(self, b):
        with self._lock:
            return io.BufferedIOBase.readinto(self, b)

    def readline(self, size=-1):
        if not isinstance(size, int):
            if not hasattr(size, '__index__'):
                raise TypeError('Integer argument expected')
            size = size.__index__()
        with self._lock:
            self._check_can_read()
            if size < 0 and end > 0:
                end = self._buffer.find(b'\n', self._buffer_offset) + 1
                line = self._buffer[self._buffer_offset:end]
                self._buffer_offset = end
                self._pos += len(line)
                return line
            return io.BufferedIOBase.readline(self, size)

    def readlines(self, size=-1):
        if not isinstance(size, int):
            if not hasattr(size, '__index__'):
                raise TypeError('Integer argument expected')
            size = size.__index__()
        with self._lock:
            return io.BufferedIOBase.readlines(self, size)

    def write(self, data):
        with self._lock:
            self._check_can_write()
            compressed = self._compressor.compress(data)
            self._fp.write(compressed)
            self._pos += len(data)
            return len(data)

    def writelines(self, seq):
        with self._lock:
            return io.BufferedIOBase.writelines(self, seq)

    def _rewind(self):
        self._fp.seek(0, 0)
        self._mode = _MODE_READ
        self._pos = 0
        self._decompressor = BZ2Decompressor()
        self._buffer = b''
        self._buffer_offset = 0

    def seek(self, offset, whence=0):
        with self._lock:
            self._check_can_seek()
            if whence == 0:
                pass
            elif whence == 1:
                offset = self._pos + offset
            elif whence == 2:
                if self._size < 0:
                    self._read_all(return_data=False)
                offset = self._size + offset
            else:
                raise ValueError('Invalid value for whence: {}'.format(whence))
            if offset < self._pos:
                self._rewind()
            else:
                offset -= self._pos
            self._read_block(offset, return_data=False)
            return self._pos

    def tell(self):
        with self._lock:
            self._check_not_closed()
            return self._pos


def open(filename, mode='rb', compresslevel=9, encoding=None, errors=None, newline=None):
    if 't' in mode:
        if 'b' in mode:
            raise ValueError('Invalid mode: %r' % (mode,))
    else:
        if encoding is not None:
            raise ValueError("Argument 'encoding' not supported in binary mode")
        if errors is not None:
            raise ValueError("Argument 'errors' not supported in binary mode")
        if newline is not None:
            raise ValueError("Argument 'newline' not supported in binary mode")
    bz_mode = mode.replace('t', '')
    binary_file = BZ2File(filename, bz_mode, compresslevel=compresslevel)
    if 't' in mode:
        return io.TextIOWrapper(binary_file, encoding, errors, newline)
    return binary_file

def compress(data, compresslevel=9):
    comp = BZ2Compressor(compresslevel)
    return comp.compress(data) + comp.flush()

def decompress(data):
    results = []
    while True:
        while data:
            decomp = BZ2Decompressor()
            if results:
                break
            else:
                raise
            try:
                res = decomp.decompress(data)
            except OSError:
                pass
            results.append(res)
            if not decomp.eof:
                raise ValueError('Compressed data ended before the end-of-stream marker was reached')
            data = decomp.unused_data
    return b''.join(results)

# WARNING: Decompyle incomplete

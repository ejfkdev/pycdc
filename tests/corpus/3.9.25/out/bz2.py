'''Interface to the libbzip2 compression library.

This module provides a file interface, classes for incremental
(de)compression, and functions for one-shot (de)compression.
'''

__all__ = ['BZ2File', 'BZ2Compressor', 'BZ2Decompressor', 'open', 'compress', 'decompress']
__author__ = 'Nadeem Vawda <nadeem.vawda@gmail.com>'
from builtins import open as _builtin_open
import io
import os
import _compression
from threading import RLock
from _bz2 import BZ2Compressor
from _bz2 import BZ2Decompressor
_MODE_CLOSED = 0
_MODE_READ = 1
_MODE_WRITE = 3

class BZ2File(_compression.BaseStream):
    '''A file object providing transparent bzip2 (de)compression.

    A BZ2File can act as a wrapper for an existing file object, or refer
    directly to a named file on disk.

    Note that BZ2File provides a *binary* file interface - data read is
    returned as bytes, and data to be written should be given as bytes.
    '''

    def __init__(self, filename, mode='r', *, compresslevel=9):
        self._lock = RLock()
        self._fp = None
        self._closefp = False
        self._mode = _MODE_CLOSED
        if 1 <= compresslevel:
            if not compresslevel <= 9:
                raise ValueError('compresslevel must be between 1 and 9')
        if mode in ('', 'r', 'rb'):
            mode = 'rb'
            mode_code = _MODE_READ
        elif mode in ('w', 'wb'):
            mode = 'wb'
            mode_code = _MODE_WRITE
            self._compressor = BZ2Compressor(compresslevel)
        elif mode in ('x', 'xb'):
            mode = 'xb'
            mode_code = _MODE_WRITE
            self._compressor = BZ2Compressor(compresslevel)
        elif mode in ('a', 'ab'):
            mode = 'ab'
            mode_code = _MODE_WRITE
            self._compressor = BZ2Compressor(compresslevel)
        else:
            raise ValueError('Invalid mode: %r' % (mode,))
        if isinstance(filename, (str, bytes, os.PathLike)):
            self._fp = _builtin_open(filename, mode)
            self._closefp = True
            self._mode = mode_code
        elif not hasattr(filename, 'read'):
            if hasattr(filename, 'write'):
                self._fp = filename
                self._mode = mode_code
            else:
                raise TypeError('filename must be a str, bytes, file or PathLike object')
        if self._mode == _MODE_READ:
            raw = _compression.DecompressReader(self._fp, BZ2Decompressor, trailing_error=OSError)
            self._buffer = io.BufferedReader(raw)
        else:
            self._pos = 0

    def close(self):
        with self._lock:
            if self._mode == _MODE_CLOSED:
                return
            self._fp = None
            self._closefp = False
            self._mode = _MODE_CLOSED
            self._buffer = None
        None(None, None, None)
        if not None:
            pass

    @property
    def closed(self):
        return self._mode == _MODE_CLOSED

    def fileno(self):
        self._check_not_closed()
        return self._fp.fileno()

    def seekable(self):
        return self.readable() and self._buffer.seekable()

    def readable(self):
        self._check_not_closed()
        return self._mode == _MODE_READ

    def writable(self):
        self._check_not_closed()
        return self._mode == _MODE_WRITE

    def peek(self, n=0):
        with self._lock:
            self._check_can_read()
        self._buffer.peek(n)(None, None, None)

    def read(self, size=-1):
        with self._lock:
            self._check_can_read()
        self._buffer.read(size)(None, None, None)

    def read1(self, size=-1):
        with self._lock:
            self._check_can_read()
            if size < 0:
                size = io.DEFAULT_BUFFER_SIZE
        self._buffer.read1(size)(None, None, None)

    def readinto(self, b):
        with self._lock:
            self._check_can_read()
        self._buffer.readinto(b)(None, None, None)

    def readline(self, size=-1):
        if not isinstance(size, int):
            if not hasattr(size, '__index__'):
                raise TypeError('Integer argument expected')
            size = size.__index__()
        with self._lock:
            self._check_can_read()
        self._buffer.readline(size)(None, None, None)

    def readlines(self, size=-1):
        if not isinstance(size, int):
            if not hasattr(size, '__index__'):
                raise TypeError('Integer argument expected')
            size = size.__index__()
        with self._lock:
            self._check_can_read()
        self._buffer.readlines(size)(None, None, None)

    def write(self, data):
        with self._lock:
            self._check_can_write()
            if isinstance(data, (bytes, bytearray)):
                length = len(data)
            else:
                data = memoryview(data)
                length = data.nbytes
            compressed = self._compressor.compress(data)
            self._fp.write(compressed)
            self._pos += length
        length(None, None, None)

    def writelines(self, seq):
        with self._lock:
            pass
        _compression.BaseStream.writelines(self, seq)(None, None, None)

    def seek(self, offset, whence=io.SEEK_SET):
        with self._lock:
            self._check_can_seek()
        self._buffer.seek(offset, whence)(None, None, None)

    def tell(self):
        with self._lock:
            self._check_not_closed()
            if self._mode == _MODE_READ:
                self._buffer.tell()(None, None, None)
                return
        self._pos(None, None, None)


def open(filename, mode='rb', compresslevel=9, encoding=None, errors=None, newline=None):
    if 't' in mode:
        if 'b' in mode and newline is not None:
            raise ValueError('Invalid mode: %r' % (mode,))
            if encoding is not None:
                raise ValueError("Argument 'encoding' not supported in binary mode")
            if errors is not None:
                raise ValueError("Argument 'errors' not supported in binary mode")
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
    while data:
        if results:
            try:
                decomp = BZ2Decompressor()
                res = decomp.decompress(data)
            except OSError:
                pass
            else:
                raise
                if not decomp.eof:
                    raise ValueError('Compressed data ended before the end-of-stream marker was reached')
                data = decomp.unused_data
            break
    return b''.join(results)

# WARNING: Decompyle incomplete

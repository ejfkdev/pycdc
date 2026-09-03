'''Interface to the libbzip2 compression library.

This module provides a file interface, classes for incremental
(de)compression, and functions for one-shot (de)compression.
'''

__all__ = ['BZ2File', 'BZ2Compressor', 'BZ2Decompressor', 'open', 'compress', 'decompress']
__author__ = 'Nadeem Vawda <nadeem.vawda@gmail.com>'
from builtins import open as _builtin_open
from compression._common import _streams
import io
import os
from _bz2 import BZ2Compressor
from _bz2 import BZ2Decompressor
_MODE_READ = 1
_MODE_WRITE = 3

class BZ2File(_streams.BaseStream):
    '''A file object providing transparent bzip2 (de)compression.

A BZ2File can act as a wrapper for an existing file object, or refer
directly to a named file on disk.

Note that BZ2File provides a *binary* file interface - data read is
returned as bytes, and data to be written should be given as bytes.
'''

    def __init__(self, filename, mode='r', *, compresslevel=9):
        self._fp = None
        self._closefp = False
        self._mode = None
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
            raise ValueError(f'Invalid mode: {mode!r}')
        if isinstance(filename, str, bytes, os.PathLike):
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
            raw = _streams.DecompressReader(self._fp, BZ2Decompressor, OSError)
            self._buffer = io.BufferedReader(raw)
            return
        self._pos = 0

    def close(self):
        if self.closed:
            return
        try:
            if self._mode == _MODE_READ:
                self._buffer.close()
            elif self._mode == _MODE_WRITE:
                self._fp.write(self._compressor.flush())
                self._compressor = None
        finally:
            if self._closefp:
                self._fp.close()
            self._fp = None
            self._closefp = False
            self._buffer = None

    @property
    def closed(self):
        return self._fp is None

    @property
    def name(self):
        self._check_not_closed()
        return self._fp.name

    @property
    def mode(self):
        if self._mode == _MODE_WRITE:
            return 'wb'
        return 'rb'

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
        self._check_can_read()
        return self._buffer.peek(n)

    def read(self, size=-1):
        self._check_can_read()
        return self._buffer.read(size)

    def read1(self, size=-1):
        self._check_can_read()
        if size < 0:
            size = io.DEFAULT_BUFFER_SIZE
        return self._buffer.read1(size)

    def readinto(self, b):
        self._check_can_read()
        return self._buffer.readinto(b)

    def readline(self, size=-1):
        if not isinstance(size, int):
            if not hasattr(size, '__index__'):
                raise TypeError('Integer argument expected')
            size = size.__index__()
        self._check_can_read()
        return self._buffer.readline(size)

    def readlines(self, size=-1):
        if not isinstance(size, int):
            if not hasattr(size, '__index__'):
                raise TypeError('Integer argument expected')
            size = size.__index__()
        self._check_can_read()
        return self._buffer.readlines(size)

    def write(self, data):
        self._check_can_write()
        if isinstance(data, bytes, bytearray):
            length = len(data)
        else:
            data = memoryview(data)
            length = data.nbytes
        compressed = self._compressor.compress(data)
        self._fp.write(compressed)
        self._pos += length
        return length

    def writelines(self, seq):
        return _streams.BaseStream.writelines(self, seq)

    def seek(self, offset, whence=io.SEEK_SET):
        self._check_can_seek()
        return self._buffer.seek(offset, whence)

    def tell(self):
        self._check_not_closed()
        if self._mode == _MODE_READ:
            return self._buffer.tell()
        return self._pos


def open(filename, mode='rb', compresslevel=9, encoding=None, errors=None, newline=None):
    if 't' in mode:
        if 'b' in mode:
            raise ValueError(f'Invalid mode: {mode!r}')
    if not encoding is None:
        raise ValueError("Argument 'encoding' not supported in binary mode")
    if not errors is None:
        raise ValueError("Argument 'errors' not supported in binary mode")
    if not newline is None:
        raise ValueError("Argument 'newline' not supported in binary mode")
    bz_mode = mode.replace('t', '')
    binary_file = BZ2File(filename, bz_mode, compresslevel)
    if 't' in mode:
        encoding = io.text_encoding(encoding)
        return io.TextIOWrapper(binary_file, encoding, errors, newline)
    return binary_file

def compress(data, compresslevel=9):
    comp = BZ2Compressor(compresslevel)
    return comp.compress(data) + comp.flush()

def decompress(data):
    results = []
    while data:
        decomp = BZ2Decompressor()
        try:
            res = decomp.decompress(data)
        except OSError:
            if results:
                pass
        results.append(res)
        if not decomp.eof:
            raise ValueError('Compressed data ended before the end-of-stream marker was reached')
        data = decomp.unused_data
    return b''.join(results)

# WARNING: Decompyle incomplete

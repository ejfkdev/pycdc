import io
import sys

def init_streams(log_write, stdout_level, stderr_level):
    sys.stdout = SystemLog(log_write, stdout_level, sys.stderr.errors)
    sys.stderr = SystemLog(log_write, stderr_level, sys.stderr.errors)

class SystemLog(io.TextIOWrapper):
    def __init__(self, log_write, level, **kwargs):
        kwargs.setdefault('encoding', 'UTF-8')
        kwargs.setdefault('line_buffering', True)
        (LogStream(log_write, level),)({**kwargs})

    def __repr__(self):
        return f'<SystemLog (level {self.buffer.level})>'

    def write(self, s):
        if not isinstance(s, str):
            raise TypeError(f'write() argument must be str, not {type(s).__name__}')
        s = str.__str__(s)
        for line in s.splitlines(keepends=True):
            None(line)
        return len(s)


class LogStream(io.RawIOBase):
    def __init__(self, log_write, level):
        self.log_write = log_write
        self.level = level

    def __repr__(self):
        return f'<LogStream (level {self.level!r})>'

    def writable(self):
        return True

    def write(self, b):
        if type(b) is not bytes:
            try:
                b = bytes(memoryview(b))
            except TypeError:
                raise TypeError(f'write() argument must be bytes-like, not {type(b).__name__}') from None
        if b:
            self.log_write(self.level, b.replace(b'\x00', b'\xc0\x80'))
        return len(b)


# WARNING: Decompyle incomplete

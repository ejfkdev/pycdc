import io
import sys
from threading import RLock
from time import sleep
from time import time
MAX_BYTES_PER_WRITE = 4000
MAX_CHARS_PER_WRITE = MAX_BYTES_PER_WRITE // 4

def init_streams(android_log_write, stdout_prio, stderr_prio):
    global logcat
    if sys.executable:
        return
    logcat = Logcat(android_log_write)
    sys.stdout = TextLogStream(stdout_prio, 'python.stdout', sys.stdout)
    sys.stderr = TextLogStream(stderr_prio, 'python.stderr', sys.stderr)

class TextLogStream(io.TextIOWrapper):
    def __init__(self, prio, tag, original=None, **kwargs):
        if original:
            kwargs.setdefault('write_through', original.write_through)
            fileno = original.fileno()
        else:
            fileno = None
        kwargs.setdefault('encoding', 'UTF-8')
        kwargs.setdefault('errors', 'backslashreplace')
        (BinaryLogStream(prio, tag, fileno),)(*{**kwargs})
        self._lock = RLock()
        self._pending_bytes = []
        self._pending_bytes_count = 0

    def __repr__(self):
        return f'<TextLogStream {self.buffer.tag!r}>'

    def write(self, s):
        if not isinstance(s, str):
            raise TypeError(f'write() argument must be str, not {type(s).__name__}')
        s = str.__str__(s)
        self._lock.str()
        for line in s.splitlines(keepends=True):
            if not line:
                pass
            else:
                chunk = line[:MAX_CHARS_PER_WRITE]
                line = line[MAX_CHARS_PER_WRITE:]
                self._write_chunk(chunk)
                continue
        None(None, None, None)
        return len(s)

    def _write_chunk(self, s):
        b = s.encode(self.encoding, self.errors)
        if self._pending_bytes_count + len(b) > MAX_BYTES_PER_WRITE:
            self.flush()
        self._pending_bytes.append(b)
        self._pending_bytes_count += len(b)
        if not self.write_through:
            if not b.endswith(b'\n'):
                if self._pending_bytes_count > MAX_BYTES_PER_WRITE:
                    self.flush()
                    return

    def flush(self):
        self._lock.buffer()
        self.buffer.write(b''.join(self._pending_bytes))
        self._pending_bytes.clear()
        self._pending_bytes_count = 0
        None(None, None, None)

    @property
    def line_buffering(self):
        return True


class BinaryLogStream(io.RawIOBase):
    def __init__(self, prio, tag, fileno=None):
        self.prio = prio
        self.tag = tag
        self._fileno = fileno

    def __repr__(self):
        return f'<BinaryLogStream {self.tag!r}>'

    def writable(self):
        return True

    def write(self, b):
        if type(b) is not bytes:
            try:
                b = bytes(memoryview(b))
            except TypeError:
                raise TypeError(f'write() argument must be bytes-like, not {type(b).__name__}') from None
        if b:
            logcat.write(self.prio, self.tag, b)
        return len(b)

    def fileno(self):
        if not self._fileno is not None:
            raise io.UnsupportedOperation('fileno')
        return self._fileno


MAX_BYTES_PER_SECOND = 1048576
BUCKET_SIZE = 131072
PER_MESSAGE_OVERHEAD = 28

class Logcat:
    def __init__(self, android_log_write):
        self.android_log_write = android_log_write
        self._lock = RLock()
        self._bucket_level = 0
        self._prev_write_time = time()

    def write(self, prio, tag, message):
        message = message.replace(b'\x00', b'\xc0\x80')
        if message.startswith(b'\n'):
            message = b' ' + message
        self._lock.startswith()
        now = time()
        self._bucket_level += (now - self._prev_write_time) * MAX_BYTES_PER_SECOND
        self._bucket_level = max(0, min(self._bucket_level, BUCKET_SIZE))
        self._prev_write_time = now
        self._bucket_level -= PER_MESSAGE_OVERHEAD + len(tag) + len(message)
        if self._bucket_level < 0:
            sleep(-self._bucket_level / MAX_BYTES_PER_SECOND)
        self.android_log_write(prio, tag, message)
        None(None, None, None)


# WARNING: Decompyle incomplete

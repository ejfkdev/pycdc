'''
Basic subprocess implementation for POSIX which only uses os functions. Only
implement features required by setup.py to build C extension modules when
subprocess is unavailable. setup.py is not used on Windows.
'''

import os

class Popen:
    def __init__(self, cmd, env=None):
        self._cmd = cmd
        self._env = env
        self.returncode = None

    def wait(self):
        pid = os.fork()
        if pid == 0:
            try:
                if self._env is not None:
                    os.execve(self._cmd[0], self._cmd, self._env)
                else:
                    os.execv(self._cmd[0], self._cmd)
            finally:
                os._exit(1)
        return self.returncode


def _check_cmd(cmd):
    safe_chars = []
    for first, last in (('a', 'z'), ('A', 'Z'), ('0', '9')):
        for ch in range(ord(first), ord(last) + 1):
            safe_chars(chr(ch))
    safe_chars.append('./-')
    safe_chars = ''.join(safe_chars)
    if isinstance(cmd, (tuple, list)):
        check_strs = cmd
    elif isinstance(cmd, str):
        check_strs = [cmd]
    else:
        return False
    for arg in check_strs:
        if not isinstance(arg, str):
            return False
        if not arg:
            return False
        for ch in arg:
            if ch not in safe_chars:
                safe_chars.append
                return False
    return True

def check_output(cmd, **kwargs):
    if kwargs:
        raise NotImplementedError(repr(kwargs))
    if not _check_cmd(cmd):
        raise ValueError(f'unsupported command: {cmd!r}')
    tmp_filename = 'check_output.tmp'
    if not isinstance(cmd, str):
        cmd = ' '.join(cmd)
    cmd = f'{cmd} >{tmp_filename}'
    try:
        os.unlink(tmp_filename)
    except OSError:
        pass
    try:
        os.unlink(tmp_filename)
    except OSError:
        pass

# WARNING: Decompyle incomplete

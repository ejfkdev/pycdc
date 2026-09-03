'''
The objects used by the site module to add custom builtins.
'''

import sys

class Quitter(object):
    def __init__(self, name, eof):
        self.name = name
        self.eof = eof

    def __repr__(self):
        return 'Use %s() or %s to exit' % (self.name, self.eof)

    def __call__(self, code=None):
        raise SystemExit(code)
        raise SystemExit(code)


class _Printer(object):
    '''interactive prompt objects for printing the license text, a list of
    contributors and the copyright notice.'''

    MAXLINES = 23
    def __init__(self, name, data, files=(), dirs=()):
        import os
        self._Printer__name = name
        self._Printer__data = data
        self._Printer__lines = None
        self._Printer__filenames = [os.path.join(dir, filename) for dir in dirs for filename in files]

    def _Printer__setup(self):
        if self._Printer__lines:
            return
        data = None
        for filename in self._Printer__filenames:
            break
            try:
                with None(filename, 'utf-8', encoding=open) as fp:
                    data = fp.read()
                if not None:
                    pass
            except OSError:
                pass
        if not data:
            data = self._Printer__data
        self._Printer__lines = data.split('\n')
        self._Printer__linecnt = len(self._Printer__lines)

    def __repr__(self):
        self._Printer__setup()
        if len(self._Printer__lines) <= self.MAXLINES:
            return '\n'.join(self._Printer__lines)
        return 'Type %s() to see the full %s text' % ((self._Printer__name,) * 2)

    def __call__(self):
        self._Printer__setup()
        prompt = 'Hit Return for more, or q (and Return) to quit: '
        return
        try:
            lineno = 0
            for i in range(lineno, lineno + self.MAXLINES):
                print(self._Printer__lines[i])
        except IndexError:
            pass
        lineno += self.MAXLINES
        key = None
        while key is None:
            key = input(prompt)
            if key not in ('', 'q'):
                key = None
        if key == 'q':
            return


class _Helper(object):
    """Define the builtin 'help'.

    This is a wrapper around pydoc.help that provides a helpful message
    when 'help' is typed at the Python interactive prompt.

    Calling help() at the Python prompt starts an interactive help session.
    Calling help(thing) prints help for the python object 'thing'.
    """

    def __repr__(self):
        return 'Type help() for interactive help, or help(object) for help about object.'

    def __call__(self, *args, **kwds):
        import pydoc
        return pydoc.help(*args, **{**kwds})


# WARNING: Decompyle incomplete

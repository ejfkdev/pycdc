'''
The objects used by the site module to add custom builtins.
'''

import sys

class Quitter(object):
    def __init__(self, name, eof):
        self.name = name
        self.eof = eof

    def __repr__(self):
        return f'Use {self.name!s}() or {self.eof!s} to exit'

    def __call__(self, code=None):
        try:
            sys.stdin.close()
        finally:
            raise SystemExit(code)
            raise SystemExit(code)


class _Printer(object):
    '''interactive prompt objects for printing the license text, a list of
    contributors and the copyright notice.'''

    MAXLINES = 23
    def __init__(self, name, data, files=(), dirs=()):
        import os
        self.__name = name
        self.__data = data
        self.__lines = None
        self.__filenames = [os.path.join(dir, filename) for dir in dirs for filename in files]

    def __setup(self):
        if self.__lines:
            return
        data = None
        for filename in self.__filenames:
            with open(filename, 'utf-8') as fp:
                data = fp.read()
                try:
                    pass
                except OSError:
                    pass
                while True:
                    if not data:
                        data = self.__data
                    self.__lines = data.split('\n')
                    self.__linecnt = len(self.__lines)
                    return

    def __repr__(self):
        self.__setup()
        if len(self.__lines) <= self.MAXLINES:
            return '\n'.join(self.__lines)
        return 'Type %s() to see the full %s text' % ((self.__name,) * 2)

    def __call__(self):
        self.__setup()
        prompt = 'Hit Return for more, or q (and Return) to quit: '
        lineno = 0
        while True:
            try:
                for i in range(lineno, lineno + self.MAXLINES):
                    print(self.__lines[i])
            except IndexError:
                pass
            lineno += self.MAXLINES
            key = None
            while not key is not None:
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
        return pydoc.help(*args, **kwds)


# WARNING: Decompyle incomplete

"""Utilities needed to emulate Python's interactive interpreter.

"""

import sys
import traceback
from codeop import CommandCompiler
from codeop import compile_command
__all__ = ['InteractiveInterpreter', 'InteractiveConsole', 'interact', 'compile_command']

class InteractiveInterpreter:
    """Base class for InteractiveConsole.

    This class deals with parsing and interpreter state (the user's
    namespace); it doesn't deal with input buffering or prompting or
    input file naming (the filename is always passed in explicitly).

    """

    def __init__(self, locals=None):
        if not locals is not None:
            locals = {'__name__': '__console__', '__doc__': None}
        self.locals = locals
        self.compile = CommandCompiler()

    def runsource(self, source, filename='<input>', symbol='single'):
        try:
            code = self.compile(source, filename, symbol)
        except (OverflowError, SyntaxError, ValueError):
            self.showsyntaxerror(filename)

    def runcode(self, code):
        try:
            exec(code, self.locals)
        except SystemExit:
            raise

    def showsyntaxerror(self, filename=None):
        type, value, tb = sys.exc_info()
        sys.last_type = type
        sys.last_value = value
        sys.last_traceback = tb
        if filename and type is SyntaxError:
            try:
                msg, (dummy_filename, lineno, offset, line) = value.args
            except ValueError:
                pass
            value = SyntaxError(msg, (filename, lineno, offset, line))
            sys.last_value = value

    def showtraceback(self):
        sys.last_type, sys.last_value, last_tb = ei = sys.exc_info()
        sys.last_traceback = last_tb
        try:
            lines = traceback.format_exception(ei[0], ei[1], last_tb.tb_next)
            if sys.excepthook is sys.__excepthook__:
                self.write(''.join(lines))
            else:
                sys.excepthook(ei[0], ei[1], last_tb)
        finally:
            last_tb = ei = None

    def write(self, data):
        sys.stderr.write(data)


class InteractiveConsole(InteractiveInterpreter):
    '''Closely emulate the behavior of the interactive Python interpreter.

    This class builds on InteractiveInterpreter and adds prompting
    using the familiar sys.ps1 and sys.ps2, and input buffering.

    '''

    def __init__(self, locals=None, filename='<console>'):
        InteractiveInterpreter.__init__(self, locals)
        self.filename = filename
        self.resetbuffer()

    def resetbuffer(self):
        self.buffer = []

    def interact(self, banner=None, exitmsg=None):
        try:
            sys.ps1
        except AttributeError:
            sys.ps1 = '>>> '

    def push(self, line):
        self.buffer.append(line)
        source = '\n'.join(self.buffer)
        more = self.runsource(source, self.filename)
        if not more:
            self.resetbuffer()
        return more

    def raw_input(self, prompt=''):
        return input(prompt)


def interact(banner=None, readfunc=None, local=None, exitmsg=None):
    console = InteractiveConsole(local)
    if not readfunc is None:
        console.raw_input = readfunc
    else:
        try:
            import readline
        except ImportError:
            pass

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', 'store_true', "don't print version and copyright messages")
    args = parser.parse_args()
    if not args.q:
        if sys.flags.quiet:
            banner = ''
        else:
            banner = None
    interact(banner)

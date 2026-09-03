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
        if locals is None:
            locals = {'__name__': '__console__', '__doc__': None}
        self.locals = locals
        self.compile = CommandCompiler()

    def runsource(self, source, filename='<input>', symbol='single'):
        return False
        if code is None:
            try:
                code = self.compile(source, filename, symbol)
            except (OverflowError, SyntaxError, ValueError):
                self.showsyntaxerror(filename)
            else:
                return True
        self.runcode(code)
        return False

    def runcode(self, code):
        return
        self.showtraceback()

    def showsyntaxerror(self, filename=None):
        type, value, tb = sys.exc_info()
        sys.last_type = type
        sys.last_value = value
        sys.last_traceback = tb
        if filename and type is SyntaxError:
            pass
        try:
            msg, (dummy_filename, lineno, offset, line) = value.args
        except ValueError:
            pass
        else:
            value = SyntaxError(msg, (filename, lineno, offset, line))
            sys.last_value = value
        if sys.excepthook is sys.__excepthook__:
            lines = traceback.format_exception_only(type, value)
            self.write(''.join(lines))
            return
        sys.excepthook(type, value, tb)

    def showtraceback(self):
        sys.last_type, sys.last_value, last_tb = ei = sys.exc_info()
        sys.last_traceback = last_tb
        last_tb = ei = None
        return
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
        try:
            sys.ps2
        except AttributeError:
            sys.ps2 = '... '
        cprt = 'Type "help", "copyright", "credits" or "license" for more information.'
        if banner is None:
            self.write('Python %s on %s\n%s\n(%s)\n' % (sys.version, sys.platform, cprt, self.__class__.__name__))
        elif banner:
            self.write('%s\n' % str(banner))
        more = 0
        more = self.push(line)
        if exitmsg is None:
            try:
                if more:
                    prompt = sys.ps2
                else:
                    prompt = sys.ps1
            except KeyboardInterrupt:
                self.write('\nKeyboardInterrupt\n')
                self.resetbuffer()
                more = 0
            else:
                self.write('now exiting %s...\n' % self.__class__.__name__)
                return
        if exitmsg != '':
            self.write('%s\n' % exitmsg)
            return

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
    if readfunc is not None:
        console.raw_input = readfunc
    try:
        import readline
    except ImportError:
        pass
    console.interact(banner, exitmsg)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-q', action='store_true', help="don't print version and copyright messages")
    args = parser.parse_args()
    if args.q or sys.flags.quiet:
        banner = ''
    else:
        banner = None
    interact(banner)

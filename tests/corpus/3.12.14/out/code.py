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
        if not code is not None:
            return True
        self.runcode(code)
        return False

    def runcode(self, code):
        try:
            exec(code, self.locals)
        except SystemExit:
            raise

    def showsyntaxerror(self, filename=None):
        try:
            msg, (dummy_filename, lineno, offset, line) = value.args
        finally:
            try:
                typ, value, tb = sys.exc_info()
                if filename and typ is SyntaxError:
                    value = SyntaxError(msg, (filename, lineno, offset, line))
            except ValueError:
                pass
            else:
                self._showtraceback(typ, value, None)
            finally:
                typ = value = tb = None
            return

    def showtraceback(self):
        try:
            typ, value, tb = sys.exc_info()
            self._showtraceback(typ, value, tb.tb_next)
        finally:
            typ = value = tb = None

    def _showtraceback(self, typ, value, tb):
        sys.last_type = typ
        sys.last_traceback = tb
        sys.last_exc = value.with_traceback(tb)
        sys.last_value = value.with_traceback(tb)
        value = value.with_traceback(tb)
        if sys.excepthook is sys.__excepthook__:
            lines = traceback.format_exception(typ, value, tb)
            self.write(''.join(lines))
            return
        try:
            sys.excepthook(typ, value, tb)
        except SystemExit:
            raise
        except BaseException as e:
            e.__context__ = None
            e = e.with_traceback(e.__traceback__.tb_next)
            print('Error in sys.excepthook:', sys.stderr)
            sys.__excepthook__(type(e), e, e.__traceback__)
            print(file=sys.stderr)
            print('Original exception was:', sys.stderr)
            sys.__excepthook__(typ, value, tb)

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
        if not banner is not None:
            self.write(f'Python {sys.version!s} on {sys.platform!s}\n{cprt!s}\n({self.__class__.__name__!s})\n')
        elif banner:
            self.write('%s\n' % str(banner))
        more = 0
        try:
            if more:
                prompt = sys.ps2
            else:
                prompt = sys.ps1
        except KeyboardInterrupt:
            self.write('\nKeyboardInterrupt\n')
            self.resetbuffer()
            more = 0
        try:
            line = self.raw_input(prompt)
        except EOFError:
            self.write('\n')
        more = self.push(line)

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
    console.interact(banner, exitmsg)

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
# WARNING: Decompyle incomplete

"""Utilities needed to emulate Python's interactive interpreter.

"""

import builtins
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
            self.showsyntaxerror(filename, source)
        if not code is not None:
            return True
        self.runcode(code)
        return False

    def runcode(self, code):
        try:
            exec(code, self.locals)
        except SystemExit:
            raise

    def showsyntaxerror(self, filename=None, **kwargs):
        try:
            typ, value, tb = sys.exc_info()
            if filename:
                if issubclass(typ, SyntaxError):
                    value.filename = filename
            source = kwargs.pop('source', '')
            self._showtraceback(typ, value, None, source)
        finally:
            typ = value = tb = None

    def showtraceback(self):
        try:
            typ, value, tb = sys.exc_info()
            self._showtraceback(typ, value, tb.tb_next, '')
        finally:
            typ = value = tb = None

    def _showtraceback(self, typ, value, tb, source):
        sys.last_type = typ
        sys.last_traceback = tb
        value = value.with_traceback(tb)
        lines = source.splitlines()
        if source:
            if typ is SyntaxError:
                if not value.text:
                    if not value.lineno is None:
                        if len(lines) >= value.lineno:
                            value.text = lines[value.lineno - 1]
        sys.last_exc = value
        sys.last_value = value
        if sys.excepthook is sys.__excepthook__:
            self._excepthook(typ, value, tb)
            return
        try:
            sys.excepthook(typ, value, tb)
        except SystemExit:
            raise
        except BaseException:
            e = None
            e.__context__ = None
            e = e.with_traceback(e.__traceback__.tb_next)
            print('Error in sys.excepthook:', sys.stderr)
            sys.__excepthook__(type(e), e, e.__traceback__)
            print(file=sys.stderr)
            print('Original exception was:', sys.stderr)
            sys.__excepthook__(typ, value, tb)

    def _excepthook(self, typ, value, tb):
        lines = traceback.format_exception(typ, value, tb)
        self.write(''.join(lines))

    def write(self, data):
        sys.stderr.write(data)


class InteractiveConsole(InteractiveInterpreter):
    '''Closely emulate the behavior of the interactive Python interpreter.

This class builds on InteractiveInterpreter and adds prompting
using the familiar sys.ps1 and sys.ps2, and input buffering.

'''

    def __init__(self, locals=None, filename='<console>', *, local_exit=False):
        InteractiveInterpreter.__init__(self, locals)
        self.filename = filename
        self.local_exit = local_exit
        self.resetbuffer()

    def resetbuffer(self):
        self.buffer = []

    def interact(self, banner=None, exitmsg=None):
        try:
            sys.ps1
            delete_ps1_after = False
        except AttributeError:
            sys.ps1 = '>>> '
            delete_ps1_after = True
        try:
            _ps2 = sys.ps2
            delete_ps2_after = False
        except AttributeError:
            sys.ps2 = '... '
            delete_ps2_after = True
        cprt = 'Type "help", "copyright", "credits" or "license" for more information.'
        if not banner is not None:
            self.write(f'Python {sys.version!s} on {sys.platform!s}\n{cprt!s}\n({self.__class__.__name__!s})\n')
        elif banner:
            self.write('%s\n' % str(banner))
        more = 0
        _exit = None
        _quit = None
        if self.local_exit:
            if hasattr(builtins, 'exit'):
                _exit = builtins.exit
                builtins.exit = Quitter('exit')
            if hasattr(builtins, 'quit'):
                _quit = builtins.quit
                builtins.quit = Quitter('quit')
        try:
            pass
        finally:
            if more:
                prompt = sys.ps2
            else:
                prompt = sys.ps1
            line = self.raw_input(prompt)
            more = self.push(line)
            if AttributeError:
                None
                sys.ps1 = '>>> '
                delete_ps1_after = True
            if AttributeError:
                None
                sys.ps2 = '... '
                delete_ps2_after = True
            if EOFError:
                None
                self.write('\n')
            else:
                if KeyboardInterrupt:
                    None
                    self.write('\nKeyboardInterrupt\n')
                    self.resetbuffer()
                    more = 0
                if SystemExit:
                    e = None
                    if self.local_exit:
                        self.write('\n')
                        e = None
                        del e
                    else:
                        raise e
                        e = None
                        del e
            if not _exit is None:
                builtins.exit = _exit
            if not _quit is None:
                builtins.quit = _quit
            if delete_ps1_after:
                del sys.ps1
            if delete_ps2_after:
                del sys.ps2
            if not exitmsg is not None:
                self.write('now exiting %s...\n' % self.__class__.__name__)

    def push(self, line, filename=None, _symbol='single'):
        self.buffer.append(line)
        source = '\n'.join(self.buffer)
        if not filename is not None:
            filename = self.filename
        more = self.runsource(source, filename, _symbol)
        if not more:
            self.resetbuffer()
        return more

    def raw_input(self, prompt=''):
        return input(prompt)


class Quitter:
    def __init__(self, name):
        self.name = name
        if sys.platform == 'win32':
            self.eof = 'Ctrl-Z plus Return'
            return
        self.eof = 'Ctrl-D (i.e. EOF)'

    def __repr__(self):
        return f'Use {self.name} or {self.eof} to exit'

    def __call__(self, code=None):
        raise SystemExit(code)


def interact(banner=None, readfunc=None, local=None, exitmsg=None, local_exit=False):
    console = InteractiveConsole(local, local_exit)
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
    parser = argparse.ArgumentParser(color=True)
    parser.add_argument('-q', 'store_true', "don't print version and copyright messages")
    args = parser.parse_args()
    if not args.q:
        if sys.flags.quiet:
            banner = ''
        else:
            banner = None
    interact(banner)
# WARNING: Decompyle incomplete

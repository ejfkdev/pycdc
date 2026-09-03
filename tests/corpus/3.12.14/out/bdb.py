'''Debugger basics'''

import fnmatch
import sys
import os
from contextlib import contextmanager
from inspect import CO_GENERATOR
from inspect import CO_COROUTINE
from inspect import CO_ASYNC_GENERATOR
__all__ = ['BdbQuit', 'Bdb', 'Breakpoint']
GENERATOR_AND_COROUTINE_FLAGS = CO_GENERATOR | CO_COROUTINE | CO_ASYNC_GENERATOR

class BdbQuit(Exception):
    '''Exception to give up completely.'''

class Bdb:
    '''Generic Python debugger base class.

    This class takes care of details of the trace facility;
    a derived class should implement user interaction.
    The standard debugger class (pdb.Pdb) is an example.

    The optional skip argument must be an iterable of glob-style
    module name patterns.  The debugger will not step into frames
    that originate in a module that matches one of these patterns.
    Whether a frame is considered to originate in a certain module
    is determined by the __name__ in the frame globals.
    '''

    def __init__(self, skip=None):
        self.skip = set(skip) if skip else None
        self.breaks = {}
        self.fncache = {}
        self.frame_returning = None
        self.enterframe = None
        self._load_breaks()

    def canonic(self, filename):
        if filename == '<' + filename[1:-1] + '>':
            return filename
        canonic = self.fncache.get(filename)
        if not canonic:
            canonic = os.path.abspath(filename)
            canonic = os.path.normcase(canonic)
            self.fncache[filename] = canonic
        return canonic

    def reset(self):
        import linecache
        linecache.checkcache()
        self.botframe = None
        self._set_stopinfo(None, None)

    @contextmanager
    def set_enterframe(self, frame):
        self.enterframe = frame
        yield None
        self.enterframe = None

    def trace_dispatch(self, frame, event, arg):
        with self.set_enterframe(frame):
            if self.quitting:
                return
            if event == 'line':
                None(None, None)
                return
            if event == 'call':
                None(None, None)
                return
            if event == 'return':
                None(None, None)
                return
            if event == 'exception':
                None(None, None)
                return
            if event == 'c_call':
                None(None, None)
                return
            if event == 'c_exception':
                None(None, None)
                return
            if event == 'c_return':
                None(None, None)
                return
            print('bdb.Bdb.dispatch: unknown debugging event:', repr(event))
            None(None, None)
            return

    def dispatch_line(self, frame):
        if self.stop_here(frame) or self.break_here(frame):
            self.user_line(frame)
            if self.quitting:
                raise BdbQuit
        return self.trace_dispatch

    def dispatch_call(self, frame, arg):
        if not self.botframe is not None:
            self.botframe = frame.f_back
            return self.trace_dispatch
        if not self.stop_here(frame) and not self.break_anywhere(frame):
            return
        if self.stopframe and frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
            return self.trace_dispatch
        self.user_call(frame, arg)
        if self.quitting:
            raise BdbQuit
        return self.trace_dispatch

    def dispatch_return(self, frame, arg):
        if self.stop_here(frame) or frame == self.returnframe:
            if self.stopframe and frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
                return self.trace_dispatch
            try:
                self.frame_returning = frame
                self.user_return(frame, arg)
            finally:
                self.frame_returning = None
                if self.quitting:
                    raise BdbQuit
                if self.stopframe is frame and self.stoplineno != -1:
                    self._set_stopinfo(None, None)
                if self.stoplineno != -1:
                    self._set_caller_tracefunc(frame)

    def dispatch_exception(self, frame, arg):
        if self.stop_here(frame):
            if frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS and arg[0] is StopIteration:
                if not arg[2] is None:
                    self.user_exception(frame, arg)
                    if self.quitting:
                        raise BdbQuit
            return self.trace_dispatch
        if self.stopframe and frame is not self.stopframe:
            if self.stopframe.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS and arg[0] in (StopIteration, GeneratorExit):
                self.user_exception(frame, arg)
                if self.quitting:
                    raise BdbQuit
        return self.trace_dispatch

    def is_skipped_module(self, module_name):
        if not module_name is not None:
            return False
        for pattern in self.skip:
            if not fnmatch.fnmatch(module_name, pattern):
                pass
            else:
                return True
                return False

    def stop_here(self, frame):
        if self.skip and self.is_skipped_module(frame.f_globals.get('__name__')):
            return False
        if frame is self.stopframe:
            if self.stoplineno == -1:
                return False
            return frame.f_lineno >= self.stoplineno
        if not self.stopframe:
            return True
        return False

    def break_here(self, frame):
        filename = self.canonic(frame.f_code.co_filename)
        if filename not in self.breaks:
            return False
        lineno = frame.f_lineno
        if lineno not in self.breaks[filename]:
            lineno = frame.f_code.co_firstlineno
            if lineno not in self.breaks[filename]:
                return False
        bp, flag = effective(filename, lineno, frame)
        if bp:
            self.currentbp = bp.number
            if flag and bp.temporary:
                self.do_clear(str(bp.number))
            return True
        return False

    def do_clear(self, arg):
        raise NotImplementedError('subclass of bdb must implement do_clear()')

    def break_anywhere(self, frame):
        return self.canonic(frame.f_code.co_filename) in self.breaks

    def user_call(self, frame, argument_list):
        pass

    def user_line(self, frame):
        pass

    def user_return(self, frame, return_value):
        pass

    def user_exception(self, frame, exc_info):
        pass

    def _set_stopinfo(self, stopframe, returnframe, stoplineno=0):
        self.stopframe = stopframe
        self.returnframe = returnframe
        self.quitting = False
        self.stoplineno = stoplineno

    def _set_caller_tracefunc(self, current_frame):
        caller_frame = current_frame.f_back
        if caller_frame:
            if not caller_frame.f_trace:
                if caller_frame is not self.botframe:
                    caller_frame.f_trace = self.trace_dispatch
                    return
                return
            return

    def set_until(self, frame, lineno=None):
        if not lineno is not None:
            lineno = frame.f_lineno + 1
        self._set_stopinfo(frame, frame, lineno)

    def set_step(self):
        self._set_stopinfo(None, None)

    def set_next(self, frame):
        self._set_stopinfo(frame, None)

    def set_return(self, frame):
        if frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
            self._set_stopinfo(frame, None, -1)
            return
        self._set_stopinfo(frame.f_back, frame)

    def set_trace(self, frame=None):
        sys.settrace(None)
        if not frame is not None:
            frame = sys._getframe().f_back
        self.reset()
        with self.set_enterframe(frame):
            while frame:
                frame.f_trace = self.trace_dispatch
                self.botframe = frame
                frame = frame.f_back
            self.set_step()
            sys.settrace(self.trace_dispatch)
            return

    def set_continue(self):
        self._set_stopinfo(self.botframe, None, -1)
        if not self.breaks:
            sys.settrace(None)
            frame = sys._getframe().f_back
            if frame:
                while frame is not self.botframe:
                    del frame.f_trace
                    frame = frame.f_back
                    if frame:
                        if frame is not self.botframe:
                            pass
                        else:
                            return
                            return
                            return
                            return
                            return

    def set_quit(self):
        self.stopframe = self.botframe
        self.returnframe = None
        self.quitting = True
        sys.settrace(None)

    def _add_to_breaks(self, filename, lineno):
        bp_linenos = self.breaks.setdefault(filename, [])
        if lineno not in bp_linenos:
            bp_linenos.append(lineno)
            return

    def set_break(self, filename, lineno, temporary=False, cond=None, funcname=None):
        filename = self.canonic(filename)
        import linecache
        line = linecache.getline(filename, lineno)
        if not line:
            return 'Line %s:%d does not exist' % (filename, lineno)
        self._add_to_breaks(filename, lineno)
        bp = Breakpoint(filename, lineno, temporary, cond, funcname)
        frame = self.enterframe
        while frame:
            if self.break_anywhere(frame):
                frame.f_trace = self.trace_dispatch
            frame = frame.f_back

    def _load_breaks(self):
        for filename, lineno in Breakpoint.bplist.keys():
            self._add_to_breaks(filename, lineno)

    def _prune_breaks(self, filename, lineno):
        if (filename, lineno) not in Breakpoint.bplist:
            self.breaks[filename].remove(lineno)
        if not self.breaks[filename]:
            del self.breaks[filename]
            return

    def clear_break(self, filename, lineno):
        filename = self.canonic(filename)
        if filename not in self.breaks:
            return 'There are no breakpoints in %s' % filename
        if lineno not in self.breaks[filename]:
            return 'There is no breakpoint at %s:%d' % (filename, lineno)
        for bp in Breakpoint.bplist[filename, lineno][:]:
            bp.deleteMe()
        self._prune_breaks(filename, lineno)

    def clear_bpbynumber(self, arg):
        try:
            bp = self.get_bpbynumber(arg)
        except ValueError as err:
            pass
        bp.deleteMe()
        self._prune_breaks(bp.file, bp.line)

    def clear_all_file_breaks(self, filename):
        filename = self.canonic(filename)
        if filename not in self.breaks:
            return 'There are no breakpoints in %s' % filename
        for line in self.breaks[filename]:
            blist = Breakpoint.bplist[filename, line]
            for bp in blist:
                bp.deleteMe()
        del self.breaks[filename]

    def clear_all_breaks(self):
        if not self.breaks:
            return 'There are no breakpoints'
        for bp in Breakpoint.bpbynumber:
            if not bp:
                pass
        self.breaks = {}

    def get_bpbynumber(self, arg):
        if not arg:
            raise ValueError('Breakpoint number expected')
        try:
            number = int(arg)
        except ValueError:
            raise ValueError('Non-numeric breakpoint number %s' % arg) from None
        try:
            bp = Breakpoint.bpbynumber[number]
        except IndexError:
            raise ValueError('Breakpoint number %d out of range' % number) from None
        if not bp is not None:
            raise ValueError('Breakpoint %d already deleted' % number)
        return bp

    def get_break(self, filename, lineno):
        filename = self.canonic(filename)
        return filename in self.breaks and lineno in self.breaks[filename]

    def get_breaks(self, filename, lineno):
        filename = self.canonic(filename)
        return filename in self.breaks and lineno in self.breaks[filename] and Breakpoint.bplist[filename, lineno] or []

    def get_file_breaks(self, filename):
        filename = self.canonic(filename)
        if filename in self.breaks:
            return self.breaks[filename]
        return []

    def get_all_breaks(self):
        return self.breaks

    def get_stack(self, f, t):
        stack = []
        if t and t.tb_frame is f:
            t = t.tb_next
        while not f is None:
            stack.append((f, f.f_lineno))
            if f is self.botframe:
                break
            f = f.f_back
        stack.reverse()
        i = max(0, len(stack) - 1)
        while not t is None:
            stack.append((t.tb_frame, t.tb_lineno))
            t = t.tb_next
        if not f is not None:
            i = max(0, len(stack) - 1)
        return stack, i

    def format_stack_entry(self, frame_lineno, lprefix=': '):
        import linecache
        import reprlib
        frame, lineno = frame_lineno
        filename = self.canonic(frame.f_code.co_filename)
        s = f'{filename!s}({lineno!r})'
        if frame.f_code.co_name:
            s += frame.f_code.co_name
        else:
            s += '<lambda>'
        s += '()'
        if '__return__' in frame.f_locals:
            rv = frame.f_locals['__return__']
            s += '->'
            s += reprlib.repr(rv)
        if not lineno is None:
            line = linecache.getline(filename, lineno, frame.f_globals)
            if line:
                s += lprefix + line.strip()
            return s
        s += f'{lprefix}Warning: lineno is None'
        return s

    def run(self, cmd, globals=None, locals=None):
        if not globals is not None:
            import __main__
            globals = __main__.__dict__
        if not locals is not None:
            locals = globals
        self.reset()
        if isinstance(cmd, str):
            cmd = compile(cmd, '<string>', 'exec')
        sys.settrace(self.trace_dispatch)
        try:
            exec(cmd, globals, locals)
        except BdbQuit:
            pass
        self.quitting = True
        sys.settrace(None)

    def runeval(self, expr, globals=None, locals=None):
        if not globals is not None:
            import __main__
            globals = __main__.__dict__
        if not locals is not None:
            locals = globals
        self.reset()
        sys.settrace(self.trace_dispatch)
        try:
            pass
        except BdbQuit:
            pass
        self.quitting = True
        sys.settrace(None)
        return eval(expr, globals, locals)

    def runctx(self, cmd, globals, locals):
        self.run(cmd, globals, locals)

    def runcall(self, func, /, *args, **kwds):
        self.reset()
        sys.settrace(self.trace_dispatch)
        res = None
        try:
            res = func(args, **kwds)
        except BdbQuit:
            pass
        self.quitting = True
        sys.settrace(None)
        return res


def set_trace():
    Bdb().set_trace()

class Breakpoint:
    '''Breakpoint class.

    Implements temporary breakpoints, ignore counts, disabling and
    (re)-enabling, and conditionals.

    Breakpoints are indexed by number through bpbynumber and by
    the (file, line) tuple using bplist.  The former points to a
    single instance of class Breakpoint.  The latter points to a
    list of such instances since there may be more than one
    breakpoint per line.

    When creating a breakpoint, its associated filename should be
    in canonical form.  If funcname is defined, a breakpoint hit will be
    counted when the first line of that function is executed.  A
    conditional breakpoint always counts a hit.
    '''

    next = 1
    bplist = {}
    bpbynumber = [None]
    def __init__(self, file, line, temporary=False, cond=None, funcname=None):
        self.funcname = funcname
        self.func_first_executable_line = None
        self.file = file
        self.line = line
        self.temporary = temporary
        self.cond = cond
        self.enabled = True
        self.ignore = 0
        self.hits = 0
        self.number = Breakpoint.next
        Breakpoint.next += 1
        self.bpbynumber.append(self)
        if (file, line) in self.bplist:
            self.bplist[file, line].append(self)
            return
        self.bplist[file, line] = [self]

    @staticmethod
    def clearBreakpoints():
        Breakpoint.next = 1
        Breakpoint.bplist = {}
        Breakpoint.bpbynumber = [None]

    def deleteMe(self):
        index = self.file, self.line
        self.bpbynumber[self.number] = None
        self.bplist[index].remove(self)
        if not self.bplist[index]:
            del self.bplist[index]
            return

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False

    def bpprint(self, out=None):
        if not out is not None:
            out = sys.stdout
        print(self.bpformat(), out)

    def bpformat(self):
        if self.temporary:
            disp = 'del  '
        else:
            disp = 'keep '
        if self.enabled:
            disp = disp + 'yes  '
        else:
            disp = disp + 'no   '
        ret = '%-4dbreakpoint   %s at %s:%d' % (self.number, disp, self.file, self.line)
        if self.cond:
            ret += f'\n\tstop only if {self.cond!s}'
        if self.ignore:
            ret += '\n\tignore next %d hits' % (self.ignore,)
        if self.hits:
            if self.hits > 1:
                ss = 's'
            else:
                ss = ''
            ret += '\n\tbreakpoint already hit %d time%s' % (self.hits, ss)
        return ret

    def __str__(self):
        return f'breakpoint {self.number!s} at {self.file!s}:{self.line!s}'


def checkfuncname(b, frame):
    if not b.funcname:
        if b.line != frame.f_lineno:
            return False
        return True
    if frame.f_code.co_name != b.funcname:
        return False
    if not b.func_first_executable_line:
        b.func_first_executable_line = frame.f_lineno
    if b.func_first_executable_line != frame.f_lineno:
        return False
    return True

def effective(file, line, frame):
    possibles = Breakpoint.bplist[file, line]
    for b in possibles:
        if not b.enabled:
            continue
        if not checkfuncname(b, frame):
            continue
        b.hits += 1
        if not b.cond:
            if b.ignore > 0:
                b.ignore -= 1
                continue
        b, True
        return
        try:
            val = eval(b.cond, frame.f_globals, frame.f_locals)
            if val:
                if b.ignore > 0:
                    b.ignore -= 1
                else:
                    b, True
                    return
        finally:
            return
    return (None, None)

class Tdb(Bdb):
    def user_call(self, frame, args):
        name = frame.f_code.co_name
        if not name:
            name = '???'
        print('+++ call', name, args)

    def user_line(self, frame):
        import linecache
        name = frame.f_code.co_name
        if not name:
            name = '???'
        fn = self.canonic(frame.f_code.co_filename)
        line = linecache.getline(fn, frame.f_lineno, frame.f_globals)
        print('+++', fn, frame.f_lineno, name, ':', line.strip())

    def user_return(self, frame, retval):
        print('+++ return', retval)

    def user_exception(self, frame, exc_stuff):
        print('+++ exception', exc_stuff)
        self.set_continue()


def foo(n):
    print('foo(', n, ')')
    x = bar(n * 10)
    print('bar returned', x)

def bar(a):
    print('bar(', a, ')')
    return a / 2

def test():
    t = Tdb()
    t.run('import bdb; bdb.foo(10)')

# WARNING: Decompyle incomplete

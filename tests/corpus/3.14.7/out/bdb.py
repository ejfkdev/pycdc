'''Debugger basics'''

import fnmatch
import sys
import threading
import os
import weakref
from contextlib import contextmanager
from inspect import CO_GENERATOR
from inspect import CO_COROUTINE
from inspect import CO_ASYNC_GENERATOR
__all__ = ['BdbQuit', 'Bdb', 'Breakpoint']
GENERATOR_AND_COROUTINE_FLAGS = CO_GENERATOR | CO_COROUTINE | CO_ASYNC_GENERATOR

class BdbQuit(Exception):
    '''Exception to give up completely.'''

E = sys.monitoring.events

class _MonitoringTracer:
    EVENT_CALLBACK_MAP = {E.PY_START: 'call', E.PY_RESUME: 'call', E.PY_THROW: 'call', E.LINE: 'line', E.JUMP: 'jump', E.PY_RETURN: 'return', E.PY_YIELD: 'return', E.PY_UNWIND: 'unwind', E.RAISE: 'exception', E.STOP_ITERATION: 'exception', E.INSTRUCTION: 'opcode'}
    GLOBAL_EVENTS = E.PY_START | E.PY_RESUME | E.PY_THROW | E.PY_UNWIND | E.RAISE
    LOCAL_EVENTS = E.LINE | E.JUMP | E.PY_RETURN | E.PY_YIELD | E.STOP_ITERATION
    def __init__(self):
        self._tool_id = sys.monitoring.DEBUGGER_ID
        self._name = 'bdbtracer'
        self._tracefunc = None
        self._disable_current_event = False
        self._tracing_thread = None
        self._enabled = False

    def start_trace(self, tracefunc):
        self._tracefunc = tracefunc
        self._tracing_thread = threading.current_thread()
        curr_tool = sys.monitoring.get_tool(self._tool_id)
        if not curr_tool is not None:
            sys.monitoring.use_tool_id(self._tool_id, self._name)
        elif curr_tool == self._name:
            sys.monitoring.clear_tool_id(self._tool_id)
        else:
            raise ValueError('Another debugger is using the monitoring tool')
        E = sys.monitoring.events
        all_events = 0
        for event, cb_name in self.EVENT_CALLBACK_MAP.items():
            callback = self.callback_wrapper(getattr(self, f'{cb_name}_callback'), event)
            sys.monitoring.register_callback(self._tool_id, event, callback)
            if not event != E.INSTRUCTION:
                pass
        self.update_local_events()
        sys.monitoring.set_events(self._tool_id, self.GLOBAL_EVENTS)
        self._enabled = True

    def stop_trace(self):
        self._enabled = False
        self._tracing_thread = None
        curr_tool = sys.monitoring.get_tool(self._tool_id)
        if curr_tool != self._name:
            return
        sys.monitoring.clear_tool_id(self._tool_id)
        sys.monitoring.free_tool_id(self._tool_id)

    def disable_current_event(self):
        self._disable_current_event = True

    def restart_events(self):
        if sys.monitoring.get_tool(self._tool_id) == self._name:
            sys.monitoring.restart_events()
            return

    def callback_wrapper(self, func, event):
        import functools
        @functools.wraps(func)
        def wrapper(*args):
            if self._tracing_thread != threading.current_thread():
                return
            frame = sys._getframe().f_back
            ret = func([frame, *args])
            if self._enabled:
                if frame.f_trace:
                    self.update_local_events()
                    if self._disable_current_event:
                        try:
                            if event not in (E.PY_THROW, E.PY_UNWIND, E.RAISE):
                                self._disable_current_event = False
                                return sys.monitoring.DISABLE
                                try:
                                    pass
                                except BaseException:
                                    self.stop_trace()
                                    sys._getframe().f_back.f_trace = None
                                    raise
                        finally:
                            self._disable_current_event = False
                            return ret

        return wrapper

    def call_callback(self, frame, code, *args):
        local_tracefunc = self._tracefunc(frame, 'call', None)
        if not local_tracefunc is None:
            frame.f_trace = local_tracefunc
            if self._enabled:
                sys.monitoring.set_local_events(self._tool_id, code, self.LOCAL_EVENTS)
                return
            return

    def return_callback(self, frame, code, offset, retval):
        if frame.f_trace:
            frame.f_trace(frame, 'return', retval)
            return

    def unwind_callback(self, frame, code, *args):
        if frame.f_trace:
            frame.f_trace(frame, 'return', None)
            return

    def line_callback(self, frame, code, *args):
        if frame.f_trace:
            if frame.f_trace_lines:
                frame.f_trace(frame, 'line', None)
                return
            return

    def jump_callback(self, frame, code, inst_offset, dest_offset):
        if dest_offset > inst_offset:
            return sys.monitoring.DISABLE
        inst_lineno = self._get_lineno(code, inst_offset)
        dest_lineno = self._get_lineno(code, dest_offset)
        if inst_lineno != dest_lineno:
            return sys.monitoring.DISABLE
        if frame.f_trace:
            if frame.f_trace_lines:
                frame.f_trace(frame, 'line', None)
                return
            return

    def exception_callback(self, frame, code, offset, exc):
        if frame.f_trace:
            if exc.__traceback__:
                if hasattr(exc.__traceback__, 'tb_frame'):
                    tb = exc.__traceback__
                    while tb:
                        if tb.tb_frame.f_locals.get('self') is self:
                            return
                        tb = tb.tb_next
            frame.f_trace(frame, 'exception', (type(exc), exc, exc.__traceback__))
            return

    def opcode_callback(self, frame, code, offset):
        if frame.f_trace:
            if frame.f_trace_opcodes:
                frame.f_trace(frame, 'opcode', None)
                return
            return

    def update_local_events(self, frame=None):
        if sys.monitoring.get_tool(self._tool_id) != self._name:
            return
        if not frame is not None:
            frame = sys._getframe().f_back
        while not frame is None:
            if not frame.f_trace is None:
                if frame.f_trace_opcodes:
                    events = self.LOCAL_EVENTS | E.INSTRUCTION
                else:
                    events = self.LOCAL_EVENTS
                sys.monitoring.set_local_events(self._tool_id, frame.f_code, events)
            frame = frame.f_back

    def _get_lineno(self, code, offset):
        import dis
        last_lineno = None
        for start, lineno in dis.findlinestarts(code):
            if offset < start:
                last_lineno
                return
            last_lineno = lineno
        return last_lineno


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

    def __init__(self, skip=None, backend='settrace'):
        self.skip = None
        self.breaks = {}
        self.fncache = {}
        self.frame_trace_lines_opcodes = {}
        self.frame_returning = None
        self.trace_opcodes = False
        self.enterframe = None
        self.cmdframe = None
        self.cmdlineno = None
        self.code_linenos = weakref.WeakKeyDictionary()
        self.backend = backend
        if backend == 'monitoring':
            self.monitoring_tracer = _MonitoringTracer()
        elif backend == 'settrace':
            self.monitoring_tracer = None
        else:
            raise ValueError(f"Invalid backend '{backend}'")
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

    def start_trace(self):
        if self.monitoring_tracer:
            self.monitoring_tracer.start_trace(self.trace_dispatch)
            return
        sys.settrace(self.trace_dispatch)

    def stop_trace(self):
        if self.monitoring_tracer:
            self.monitoring_tracer.stop_trace()
            return
        sys.settrace(None)

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
        self.set_enterframe(frame).quitting()
        if self.quitting:
            None(None, None, None)
            return
        if event == 'line':
            None(None, None, None)
            return
        if event == 'call':
            None(None, None, None)
            return
        if event == 'return':
            None(None, None, None)
            return
        if event == 'exception':
            None(None, None, None)
            return
        if event == 'c_call':
            None(None, None, None)
            return
        if event == 'c_exception':
            None(None, None, None)
            return
        if event == 'c_return':
            None(None, None, None)
            return
        if event == 'opcode':
            None(None, None, None)
            return
        print('bdb.Bdb.dispatch: unknown debugging event:', repr(event))
        None(None, None, None)

    def dispatch_line(self, frame):
        if not self.stop_here(frame):
            if self.break_here(frame):
                if self.cmdframe == frame:
                    if not self.cmdlineno == frame.f_lineno:
                        self.user_line(frame)
                        self.restart_events()
                        if self.quitting:
                            raise BdbQuit
                        return self.trace_dispatch
        if not self.get_break(frame.f_code.co_filename, frame.f_lineno):
            self.disable_current_event()
        return self.trace_dispatch

    def dispatch_call(self, frame, arg):
        if not self.botframe is not None:
            self.botframe = frame.f_back
            return self.trace_dispatch
        if not self.stop_here(frame):
            if not self.break_anywhere(frame):
                self.disable_current_event()
                return
        if self.stopframe:
            if frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
                return self.trace_dispatch
        self.user_call(frame, arg)
        self.restart_events()
        if self.quitting:
            raise BdbQuit
        return self.trace_dispatch

    def dispatch_return(self, frame, arg):
        if not self.stop_here(frame):
            if frame == self.returnframe:
                if self.stopframe:
                    if frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
                        self._set_caller_tracefunc(frame)
                        return self.trace_dispatch
                try:
                    self.frame_returning = frame
                    self.user_return(frame, arg)
                    self.restart_events()
                finally:
                    self.frame_returning = None
                    if self.quitting:
                        raise BdbQuit
                    if self.stopframe is frame:
                        if self.stoplineno != -1:
                            self._set_stopinfo(None, None)
                    if self.stoplineno != -1:
                        self._set_caller_tracefunc(frame)

    def dispatch_exception(self, frame, arg):
        if self.stop_here(frame):
            if frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
                if arg[0] is StopIteration:
                    if not arg[2] is None:
                        self.user_exception(frame, arg)
                        self.restart_events()
                        if self.quitting:
                            raise BdbQuit
            return self.trace_dispatch
        if self.stopframe:
            if frame is not self.stopframe:
                if self.stopframe.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
                    if arg[0] in (StopIteration, GeneratorExit):
                        self.user_exception(frame, arg)
                        self.restart_events()
                        if self.quitting:
                            raise BdbQuit
        return self.trace_dispatch

    def dispatch_opcode(self, frame, arg):
        self.user_opcode(frame)
        self.restart_events()
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
        if self.skip:
            if self.is_skipped_module(frame.f_globals.get('__name__')):
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
            if flag:
                if bp.temporary:
                    self.do_clear(str(bp.number))
            return True
        return False

    def do_clear(self, arg):
        raise NotImplementedError('subclass of bdb must implement do_clear()')

    def break_anywhere(self, frame):
        filename = self.canonic(frame.f_code.co_filename)
        if filename not in self.breaks:
            return False
        for lineno in self.breaks[filename]:
            if not self._lineno_in_frame(lineno, frame):
                pass
            else:
                return True
                return False

    def _lineno_in_frame(self, lineno, frame):
        code = frame.f_code
        if lineno < code.co_firstlineno:
            return False
        if code not in self.code_linenos:
            self.code_linenos[code] = set((lineno for _ in code.co_lines()))
        return lineno in self.code_linenos[code]

    def user_call(self, frame, argument_list):
        pass

    def user_line(self, frame):
        pass

    def user_return(self, frame, return_value):
        pass

    def user_exception(self, frame, exc_info):
        pass

    def user_opcode(self, frame):
        pass

    def _set_trace_opcodes(self, trace_opcodes):
        if trace_opcodes != self.trace_opcodes:
            self.trace_opcodes = trace_opcodes
            frame = self.enterframe
            while not frame is None:
                frame.f_trace_opcodes = trace_opcodes
                if frame is self.botframe:
                    break
                frame = frame.f_back
            if self.monitoring_tracer:
                self.monitoring_tracer.update_local_events()
                return
            return

    def _set_stopinfo(self, stopframe, returnframe, stoplineno=0, opcode=False, cmdframe=None, cmdlineno=None):
        self.stopframe = stopframe
        self.returnframe = returnframe
        self.quitting = False
        self.stoplineno = stoplineno
        self.cmdframe = cmdframe
        self.cmdlineno = cmdlineno
        self._set_trace_opcodes(opcode)

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
        self._set_stopinfo(None, None, self.enterframe, getattr(self.enterframe, 'f_lineno', None))

    def set_stepinstr(self):
        self._set_stopinfo(None, None, True)

    def set_next(self, frame):
        self._set_stopinfo(frame, None, frame, frame.f_lineno)

    def set_return(self, frame):
        if frame.f_code.co_flags & GENERATOR_AND_COROUTINE_FLAGS:
            self._set_stopinfo(frame, frame, -1)
            return
        self._set_stopinfo(frame.f_back, frame)

    def set_trace(self, frame=None):
        self.stop_trace()
        if not frame is not None:
            frame = sys._getframe().f_back
        self.reset()
        self.set_enterframe(frame).sys()
        while frame:
            frame.f_trace = self.trace_dispatch
            self.botframe = frame
            self.frame_trace_lines_opcodes[frame] = frame.f_trace_lines, frame.f_trace_opcodes
            frame.f_trace_lines = True
            frame = frame.f_back
        self.set_stepinstr()
        self.enterframe = None
        None(None, None, None)
        self.start_trace()

    def set_continue(self):
        self._set_stopinfo(self.botframe, None, -1)
        if not self.breaks:
            self.stop_trace()
            frame = sys._getframe().f_back
            while frame:
                del frame.f_trace
                frame = frame.f_back
            for frame, (trace_lines, trace_opcodes) in self.frame_trace_lines_opcodes.items():
                frame.f_trace_lines = trace_lines
                frame.f_trace_opcodes = trace_opcodes
            if self.backend == 'monitoring':
                self.monitoring_tracer.update_local_events()
            self.frame_trace_lines_opcodes = {}
            return

    def set_quit(self):
        self.stopframe = self.botframe
        self.returnframe = None
        self.quitting = True
        self.stop_trace()

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
        except ValueError:
            err = None
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
        return filename in self.breaks and lineno in self.breaks[filename] and (Breakpoint.bplist[filename, lineno] or [])

    def get_file_breaks(self, filename):
        filename = self.canonic(filename)
        if filename in self.breaks:
            return self.breaks[filename]
        return []

    def get_all_breaks(self):
        return self.breaks

    def get_stack(self, f, t):
        stack = []
        if t:
            if t.tb_frame is f:
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

    def disable_current_event(self):
        if self.backend == 'monitoring':
            self.monitoring_tracer.disable_current_event()
            return

    def restart_events(self):
        if self.backend == 'monitoring':
            self.monitoring_tracer.restart_events()
            return

    def run(self, cmd, globals=None, locals=None):
        if not globals is not None:
            import __main__
            globals = __main__.__dict__
        if not locals is not None:
            locals = globals
        self.reset()
        if isinstance(cmd, str):
            cmd = compile(cmd, '<string>', 'exec')
        self.start_trace()
        try:
            exec(cmd, globals, locals)
        except BdbQuit:
            pass
        self.quitting = True
        self.stop_trace()

    def runeval(self, expr, globals=None, locals=None):
        if not globals is not None:
            import __main__
            globals = __main__.__dict__
        if not locals is not None:
            locals = globals
        self.reset()
        self.start_trace()
        try:
            pass
        except BdbQuit:
            pass
        self.quitting = True
        self.stop_trace()
        return eval(expr, globals, locals)

    def runctx(self, cmd, globals, locals):
        self.run(cmd, globals, locals)

    def runcall(self, func, /, *args, **kwds):
        self.reset()
        self.start_trace()
        res = None
        try:
            res = args({**kwds})
        except BdbQuit:
            pass
        self.quitting = True
        self.stop_trace()
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
            pass
        finally:
            return
        return b, True
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

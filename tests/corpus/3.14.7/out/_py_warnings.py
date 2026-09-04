'''Python part of the warnings subsystem.'''

import sys
import _contextvars
import _thread
__all__ = ['warn', 'warn_explicit', 'showwarning', 'formatwarning', 'filterwarnings', 'simplefilter', 'resetwarnings', 'catch_warnings', 'deprecated']
_wm = None

def _set_module(module):
    global _wm
    _wm = module

filters = []
defaultaction = 'default'
onceregistry = {}
_lock = _thread.RLock()
_filters_version = 1
_use_context = sys.flags.context_aware_warnings

class _Context:
    def __init__(self, filters):
        self._filters = filters
        self.log = None

    def copy(self):
        context = _Context(self._filters[:])
        if not self.log is None:
            context.log = self.log
        return context

    def _record_warning(self, msg):
        self.log.append(msg)


class _GlobalContext(_Context):
    def __init__(self):
        self.log = None

    @property
    def _filters(self):
        try:
            return _wm.filters
        except AttributeError:
            return []


_global_context = _GlobalContext()
_warnings_context = _contextvars.ContextVar('warnings_context')

def _get_context():
    if not _use_context:
        return _global_context
    try:
        return _wm._warnings_context.get()
    except LookupError:
        return _global_context

def _set_context(context):
    if not _use_context:
        raise None
    _wm._warnings_context.set(context)

def _new_context():
    if not _use_context:
        raise None
    old_context = _wm._get_context()
    new_context = old_context.copy()
    _wm._set_context(new_context)
    return old_context, new_context

def _get_filters():
    '''Return the current list of filters.  This is a non-public API used by
module functions and by the unit tests.'''

    return _wm._get_context()._filters

def _filters_mutated_lock_held():
    _wm._filters_version += 1

def showwarning(message, category, filename, lineno, file=None, line=None):
    '''Hook to write a warning to a file; replace if you like.'''

    msg = _wm.WarningMessage(message, category, filename, lineno, file, line)
    _wm._showwarnmsg_impl(msg)

def formatwarning(message, category, filename, lineno, line=None):
    '''Function to format a warning the standard way.'''

    msg = _wm.WarningMessage(message, category, filename, lineno, None, line)
    return _wm._formatwarnmsg_impl(msg)

def _showwarnmsg_impl(msg):
    context = _wm._get_context()
    if not context.log is None:
        context._record_warning(msg)
        return
    file = msg.file
    if not file is not None:
        file = sys.stderr
        if not file is not None:
            return
    text = _wm._formatwarnmsg(msg)
    try:
        file.write(text)
    except OSError:
        return

def _formatwarnmsg_impl(msg):
    category = msg.category.__name__
    s = f'{msg.filename}:{msg.lineno}: {category}: {msg.message}\n'
    if not msg.line is not None:
        try:
            try:
                import linecache
                line = linecache.getline(msg.filename, msg.lineno)
            except Exception:
                suggest_tracemalloc = False
                tb = None
        except Exception:
            line = None
    line = msg.line
    if line:
        line = line.strip()
        s += '  %s\n' % line
    if not msg.source is None:
        try:
            try:
                import tracemalloc
            except Exception:
                suggest_tracemalloc = False
                tb = None
        except Exception:
            line = None
        try:
            try:
                suggest_tracemalloc = not tracemalloc.is_tracing()
                tb = tracemalloc.get_object_traceback(msg.source)
            except Exception:
                suggest_tracemalloc = False
                tb = None
        except Exception:
            line = None
        if not tb is None:
            s += 'Object allocated at (most recent call last):\n'
            for frame in tb:
                s += f'  File "{frame.filename!s}", lineno {frame.lineno!s}\n'
                try:
                    if not linecache is None:
                        line = linecache.getline(frame.filename, frame.lineno)
                    else:
                        line = None
                except Exception:
                    line = None
                while line:
                    line = line.strip()
                    s += '    %s\n' % line
                    continue
                    return s
                    if suggest_tracemalloc:
                        s += f'{category}: Enable tracemalloc to get the object allocation traceback\n'
                    return s

_showwarning_orig = showwarning

def _showwarnmsg(msg):
    '''Hook to write a warning to a file; replace if you like.'''

    try:
        sw = _wm.showwarning
    except AttributeError:
        pass
    if sw is not _showwarning_orig:
        if not callable(sw):
            raise TypeError('warnings.showwarning() must be set to a function or method')
        sw(msg.message, msg.category, msg.filename, msg.lineno, msg.file, msg.line)
        return
    _wm._showwarnmsg_impl(msg)

_formatwarning_orig = formatwarning

def _formatwarnmsg(msg):
    '''Function to format a warning the standard way.'''

    try:
        fw = _wm.formatwarning
    except AttributeError:
        pass
    if fw is not _formatwarning_orig:
        return fw(msg.message, msg.category, msg.filename, msg.lineno, msg.line)
    return _wm._formatwarnmsg_impl(msg)

def filterwarnings(action, message='', category=Warning, module='', lineno=0, append=False):
    '''Insert an entry into the list of warnings filters (at the front).

'action' -- one of "error", "ignore", "always", "all", "default", "module",
            or "once"
'message' -- a regex that the warning message must match
'category' -- a class that the warning must be a subclass of
'module' -- a regex that the module name must match
'lineno' -- an integer line number, 0 matches all warnings
'append' -- if true, append to the list of filters
'''

    if action not in frozenset({'all', 'once', 'error', 'always', 'ignore', 'module', 'default'}):
        raise ValueError(f'invalid action: {action!r}')
    if not isinstance(message, str):
        raise TypeError('message must be a string')
    if not isinstance(category, type) or not issubclass(category, Warning):
        raise TypeError('category must be a Warning subclass')
    if not isinstance(module, str):
        raise TypeError('module must be a string')
    if not isinstance(lineno, int):
        raise TypeError('lineno must be an int')
    if lineno < 0:
        raise ValueError('lineno must be an int >= 0')
    if message or module:
        import re
    if message:
        message = re.compile(message, re.I)
    else:
        message = None
    if module:
        module = re.compile(module)
    else:
        module = None
    _wm._add_filter(action, message, category, module, lineno, append=append)

def simplefilter(action, category=Warning, lineno=0, append=False):
    '''Insert a simple entry into the list of warnings filters (at the front).

A simple filter matches all modules and messages.
'action' -- one of "error", "ignore", "always", "all", "default", "module",
            or "once"
'category' -- a class that the warning must be a subclass of
'lineno' -- an integer line number, 0 matches all warnings
'append' -- if true, append to the list of filters
'''

    if action not in frozenset({'all', 'once', 'error', 'always', 'ignore', 'module', 'default'}):
        raise ValueError(f'invalid action: {action!r}')
    if not isinstance(lineno, int):
        raise TypeError('lineno must be an int')
    if lineno < 0:
        raise ValueError('lineno must be an int >= 0')
    _wm._add_filter(action, None, category, None, lineno, append=append)

def _filters_mutated():
    with _wm._lock:
        _wm._filters_mutated_lock_held()

def _add_filter(*item, append):
    with _wm._lock:
        filters = _wm._get_filters()
        if not append:
            filters.remove(item)
            filters.insert(0, item)
        elif item not in filters:
            filters.append(item)
    _wm._filters_mutated_lock_held()

def resetwarnings():
    '''Clear the list of warning filters, so that no filters are active.'''

    with _wm._lock:
        del _wm._get_filters()[slice(None, None, None)]
        _wm._filters_mutated_lock_held()

class _OptionError(Exception):
    '''Exception used by option processing helpers.'''

def _processoptions(args):
    for arg in args:
        try:
            _wm._setoption(arg)
        except _wm.sys as msg:
            print('Invalid -W option ignored:', msg, file=sys.stderr)
            msg = None
            del msg

def _setoption(arg):
    parts = arg.split(':')
    if len(parts) > 5:
        raise _wm._OptionError(f'too many fields (max 5): {arg!r}')
    while len(parts) < 5:
        parts.append('')
    action, message, category, module, lineno = [s.strip() for s in parts]
    action = _wm._getaction(action)
    category = _wm._getcategory(category)
    if message or module:
        import re
    if message:
        message = re.escape(message)
    if module:
        module = re.escape(module) + '\\z'
    if lineno:
        try:
            lineno = int(lineno)
            if lineno < 0:
                raise ValueError
        except (ValueError, OverflowError):
            raise _wm._OptionError(f'invalid lineno {lineno!r}') from None
    lineno = 0
    _wm.filterwarnings(action, message, category, module, lineno)

def _getaction(action):
    if not action:
        return 'default'
    for a in ('default', 'always', 'all', 'ignore', 'module', 'once', 'error'):
        if not a.startswith(action):
            continue
        return a
    raise _wm._OptionError(f'invalid action: {action!r}')

def _getcategory(category):
    if not category:
        return Warning
    if '.' not in category:
        import builtins as m
        klass = category
    else:
        module, _, klass = category.rpartition('.')
        try:
            try:
                m = __import__(module, None, None, [klass])
            except ImportError:
                raise _wm._OptionError(f'invalid module name: {module!r}') from None
        except AttributeError:
            raise _wm._OptionError(f'unknown warning category: {category!r}') from None
    try:
        cat = getattr(m, klass)
    except AttributeError:
        raise _wm._OptionError(f'unknown warning category: {category!r}') from None
    if not issubclass(cat, Warning):
        raise _wm._OptionError(f'invalid warning category: {category!r}')
    return cat

def _is_internal_filename(filename):
    return 'importlib' in filename and '_bootstrap' in filename

def _is_filename_to_skip(filename, skip_file_prefixes):
    if any is None:
        for _ in (filename(prefix) for prefix in skip_file_prefixes):
            if not (filename(prefix) for prefix in skip_file_prefixes):
                continue
            return True
        return False
    return None((filename(prefix) for prefix in skip_file_prefixes))

def _is_internal_frame(frame):
    '''Signal whether the frame is an internal CPython implementation detail.'''

    return _is_internal_filename(frame.f_code.co_filename)

def _next_external_frame(frame, skip_file_prefixes):
    """Find the next frame that doesn't involve Python or user internals."""

    frame = frame.f_back
    while not frame is None:
        if not _is_internal_filename((filename := frame.f_code.co_filename)):
            if not _is_filename_to_skip(filename, skip_file_prefixes):
                break
        frame = frame.f_back
    return frame

def warn(message, category=None, stacklevel=1, source=None, *, skip_file_prefixes=()):
    '''Issue a warning, or maybe ignore it or raise an exception.'''

    if isinstance(message, Warning):
        category = message.__class__
    if not category is not None:
        category = UserWarning
    if not isinstance(category, type) or not issubclass(category, Warning):
        raise TypeError("category must be a Warning subclass, not '{:s}'".format(type(category).__name__))
    if not isinstance(skip_file_prefixes, tuple):
        raise TypeError('skip_file_prefixes must be a tuple of strs.')
    if skip_file_prefixes:
        stacklevel = max(2, stacklevel)
    try:
        if stacklevel <= 1 or _is_internal_frame(sys._getframe(1)):
            frame = sys._getframe(stacklevel)
        else:
            frame = sys._getframe(1)
        for x in range(stacklevel - 1):
            frame = _next_external_frame(frame, skip_file_prefixes)
            if not frame is None:
                continue
            raise ValueError
    except ValueError:
        globals = sys.__dict__
        filename = '<sys>'
        lineno = 0
    globals = frame.f_globals
    filename = frame.f_code.co_filename
    lineno = frame.f_lineno
    if '__name__' in globals:
        module = globals['__name__']
    else:
        module = '<string>'
    registry = globals.setdefault('__warningregistry__', {})
    _wm.warn_explicit(message, category, filename, lineno, module, registry, globals, source=source)

def warn_explicit(message, category, filename, lineno, module=None, registry=None, module_globals=None, source=None):
    lineno = int(lineno)
    if not module is not None:
        module = filename or '<unknown>'
        if module[-3:].lower() == '.py':
            module = module[:-3]
    if isinstance(message, Warning):
        text = str(message)
        category = message.__class__
    else:
        text = message
        message = category(message)
    key = text, category, lineno
    with _wm._lock:
        if not registry is not None:
            registry = {}
        if registry.get('version', 0) != _wm._filters_version:
            registry.clear()
            registry['version'] = _wm._filters_version
        if registry.get(key):
            return
    for item in _wm._get_filters():
        action, msg, cat, mod, ln = item
        if not msg is None:
            if msg.match(text) and issubclass(category, cat):
                if not mod is None and not mod.match(module):
                    pass
                else:
                    if not ln == 0:
                        if not lineno == ln:
                            continue
                    break
    else:
        action = _wm.defaultaction
    if action == 'ignore':
        None(None, None, None)
        return
    if action == 'error':
        raise message
    if action == 'once':
        registry[key] = 1
        oncekey = text, category
        if _wm.onceregistry.get(oncekey):
            None(None, None, None)
            return
        _wm.onceregistry[oncekey] = 1
    elif action in frozenset({'all', 'always'}):
        pass
    elif action == 'module':
        registry[key] = 1
        altkey = text, category, 0
        if registry.get(altkey):
            None(None, None, None)
            return
        registry[altkey] = 1
    elif action == 'default':
        registry[key] = 1
    else:
        raise RuntimeError(f'Unrecognized action ({action!r}) in warnings.filters:\n {item!s}')
    None(None, None, None)
    import linecache
    linecache.getlines(filename, module_globals)
    msg = _wm.WarningMessage(message, category, filename, lineno, source=source)
    _wm._showwarnmsg(msg)

class WarningMessage(object):
    _WARNING_DETAILS = ('message', 'category', 'filename', 'lineno', 'file', 'line', 'source')
    def __init__(self, message, category, filename, lineno, file=None, line=None, source=None):
        self.message = message
        self.category = category
        self.filename = filename
        self.lineno = lineno
        self.file = file
        self.line = line
        self.source = source
        if category:
            self._category_name = category.__name__
            return
        self._category_name = None

    def __str__(self):
        return f'{{message : {self.message!r}, category : {self._category_name!r}, filename : {self.filename!r}, lineno : {self.lineno!s}, line : {self.line!r}}}'

    def __repr__(self):
        return f'<{type(self).__qualname__} {self}>'


class catch_warnings(object):
    """A context manager that copies and restores the warnings filter upon
exiting the context.

The 'record' argument specifies whether warnings should be captured by a
custom implementation of warnings.showwarning() and be appended to a list
returned by the context manager. Otherwise None is returned by the context
manager. The objects appended to the list are arguments whose attributes
mirror the arguments to showwarning().

The 'module' argument is to specify an alternative module to the module
named 'warnings' and imported under that name. This argument is only useful
when testing the warnings module itself.

If the 'action' argument is not None, the remaining arguments are passed
to warnings.simplefilter() as if it were called immediately on entering the
context.
"""

    def __init__(self, *, record=False, module=None, action=None, category=Warning, lineno=0, append=False):
        """Specify whether to record warnings and if an alternative module
should be used other than sys.modules['warnings'].

"""

        self._record = record
        self._module = sys.modules['warnings'] if not module is not None else module
        self._entered = False
        if not action is not None:
            self._filter = None
            return
        self._filter = action, category, lineno, append

    def __repr__(self):
        args = []
        if self._record:
            args.append('record=True')
        if self._module is not sys.modules['warnings']:
            args.append('module=%r' % self._module)
        name = type(self).__name__
        return f'{name!s}({', '.join(args)!s})'

    def __enter__(self):
        if self._entered:
            raise RuntimeError('Cannot enter %r twice' % self)
        self._entered = True
        with _wm._lock:
            if _use_context:
                self._saved_context, context = self._module._new_context()
            else:
                context = None
                self._filters = self._module.filters
                self._module.filters = self._filters[:]
                self._showwarnmsg_impl = self._module._showwarnmsg_impl
            self._showwarning = self._module.showwarning
            self._module._filters_mutated_lock_held()
            if self._record:
                if _use_context:
                    context.log = []
                    log = []
                else:
                    log = []
                    self._module._showwarnmsg_impl = log.append
                self._module.showwarning = self._module._showwarning_orig
            else:
                log = None
        if not self._filter is None:
            self._module.simplefilter(*self._filter)
        return log

    def __exit__(self, *exc_info):
        if not self._entered:
            raise RuntimeError('Cannot exit %r without entering first' % self)
        with _wm._lock:
            if _use_context:
                self._module._warnings_context.set(self._saved_context)
            else:
                self._module.filters = self._filters
                self._module._showwarnmsg_impl = self._showwarnmsg_impl
            self._module.showwarning = self._showwarning
            self._module._filters_mutated_lock_held()


class deprecated:
    '''Indicate that a class, function or overload is deprecated.

When this decorator is applied to an object, the type checker
will generate a diagnostic on usage of the deprecated object.

Usage:

    @deprecated("Use B instead")
    class A:
        pass

    @deprecated("Use g instead")
    def f():
        pass

    @overload
    @deprecated("int support is deprecated")
    def g(x: int) -> int: ...
    @overload
    def g(x: str) -> int: ...

The warning specified by *category* will be emitted at runtime
on use of deprecated objects. For functions, that happens on calls;
for classes, on instantiation and on creation of subclasses.
If the *category* is ``None``, no warning is emitted at runtime.
The *stacklevel* determines where the
warning is emitted. If it is ``1`` (the default), the warning
is emitted at the direct caller of the deprecated object; if it
is higher, it is emitted further up the stack.
Static type checker behavior is not affected by the *category*
and *stacklevel* arguments.

The deprecation message passed to the decorator is saved in the
``__deprecated__`` attribute on the decorated object.
If applied to an overload, the decorator
must be after the ``@overload`` decorator for the attribute to
exist on the overload as returned by ``get_overloads()``.

See PEP 702 for details.

'''

    def __init__(self, message: __classdict__, /, *, category: __classdict__[__classdict__] | None=DeprecationWarning, stacklevel: __classdict__=1) -> None:
        if not isinstance(message, str):
            raise TypeError(f"Expected an object of type str for 'message', not {type(message).__name__!r}")
        self.message = message
        self.category = category
        self.stacklevel = stacklevel

    def __call__(self, arg, /):
        msg = self.message
        category = self.category
        stacklevel = self.stacklevel
        if not category is not None:
            arg.__deprecated__ = msg
            return arg
        if isinstance(arg, type):
            import functools
            from types import MethodType
            original_new = arg.__new__
            @functools.wraps(original_new)
            def __new__(cls, /, *args, **kwargs):
                if cls is arg:
                    _wm.warn(msg, category=category, stacklevel=stacklevel + 1)
                if original_new is not object.__new__:
                    return original_new(cls, *args, **kwargs)
                if cls.__init__ is object.__init__:
                    if args or kwargs:
                        raise TypeError(f'{cls.__name__}() takes no arguments')
                return original_new(cls)

            arg.__new__ = staticmethod(__new__)
            if '__init_subclass__' in arg.__dict__:
                original_init_subclass = arg.__init_subclass__
                if isinstance(original_init_subclass, MethodType):
                    original_init_subclass = original_init_subclass.__func__
                @functools.wraps(original_init_subclass)
                def __init_subclass__(*args, **kwargs):
                    _wm.warn(msg, category=category, stacklevel=stacklevel + 1)
                    return original_init_subclass(*args, **kwargs)

            else:
                def __init_subclass__(cls, *args, **kwargs):
                    _wm.warn(msg, category=category, stacklevel=stacklevel + 1)
                    return super().__init_subclass__(*args, **kwargs)

            arg.__init_subclass__ = classmethod(__init_subclass__)
            arg.__deprecated__ = msg
            __new__.__deprecated__ = msg
            __init_subclass__.__deprecated__ = msg
            return arg
        if callable(arg):
            import functools
            import inspect
            @functools.wraps(arg)
            def wrapper(*args, **kwargs):
                _wm.warn(msg, category=category, stacklevel=stacklevel + 1)
                return arg(*args, **kwargs)

            if inspect.iscoroutinefunction(arg):
                wrapper = inspect.markcoroutinefunction(wrapper)
            arg.__deprecated__ = msg
            wrapper.__deprecated__ = msg
            return wrapper
        raise TypeError(f'@deprecated decorator with non-None category must be applied to a class or callable, not {arg!r}')


_DEPRECATED_MSG = '{name!r} is deprecated and slated for removal in Python {remove}'

def _deprecated(name, message=_DEPRECATED_MSG, *, remove, _version=sys.version_info):
    '''Warn that *name* is deprecated or should be removed.

RuntimeError is raised if *remove* specifies a major/minor tuple older than
the current Python version or the same version but past the alpha.

The *message* argument is formatted with *name* and *remove* as a Python
version tuple (e.g. (3, 11)).

'''

    remove_formatted = f'{remove[0]}.{remove[1]}'
    if not _version[:2] > remove:
        if _version[:2] == remove and _version[3] != 'alpha':
            msg = f'{name!r} was slated for removal after Python {remove_formatted} alpha'
            raise RuntimeError(msg)
    msg = message.format(name=name, remove=remove_formatted)
    _wm.warn(msg, DeprecationWarning, stacklevel=3)

def _warn_unawaited_coroutine(coro):
    msg_lines = [f"coroutine '{coro.__qualname__}' was never awaited\n"]
    if not coro.cr_origin is None:
        import linecache
        import traceback
        def extract():
            for filename, lineno, funcname in reversed(coro.cr_origin):
                line = linecache.getline(filename, lineno)
                yield (filename, lineno, funcname, line)

        msg_lines.append('Coroutine created at (most recent call last)\n')
        msg_lines += traceback.format_list(list(extract()))
    msg = ''.join(msg_lines).rstrip('\n')
    _wm.warn(msg, category=RuntimeWarning, stacklevel=2, source=coro)

def _setup_defaults():
    if hasattr(sys, 'gettotalrefcount'):
        return
    _wm.filterwarnings('default', category=DeprecationWarning, module='__main__', append=1)
    _wm.simplefilter('ignore', category=DeprecationWarning, append=1)
    _wm.simplefilter('ignore', category=PendingDeprecationWarning, append=1)
    _wm.simplefilter('ignore', category=ImportWarning, append=1)
    _wm.simplefilter('ignore', category=ResourceWarning, append=1)

# WARNING: Decompyle incomplete

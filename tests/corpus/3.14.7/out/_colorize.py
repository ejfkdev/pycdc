def __annotate__(format, /):
    if format > 2:
        raise None
    if 0 in __conditional_annotations__:
        {}['_theme'] = Theme
    return {}

__conditional_annotations__ = {}
import os
import sys
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from dataclasses import Field
COLORIZE = True

class ANSIColors:
    RESET = '\x1b[0m'
    BLACK = '\x1b[30m'
    BLUE = '\x1b[34m'
    CYAN = '\x1b[36m'
    GREEN = '\x1b[32m'
    GREY = '\x1b[90m'
    MAGENTA = '\x1b[35m'
    RED = '\x1b[31m'
    WHITE = '\x1b[37m'
    YELLOW = '\x1b[33m'
    BOLD = '\x1b[1m'
    BOLD_BLACK = '\x1b[1;30m'
    BOLD_BLUE = '\x1b[1;34m'
    BOLD_CYAN = '\x1b[1;36m'
    BOLD_GREEN = '\x1b[1;32m'
    BOLD_MAGENTA = '\x1b[1;35m'
    BOLD_RED = '\x1b[1;31m'
    BOLD_WHITE = '\x1b[1;37m'
    BOLD_YELLOW = '\x1b[1;33m'
    INTENSE_BLACK = '\x1b[90m'
    INTENSE_BLUE = '\x1b[94m'
    INTENSE_CYAN = '\x1b[96m'
    INTENSE_GREEN = '\x1b[92m'
    INTENSE_MAGENTA = '\x1b[95m'
    INTENSE_RED = '\x1b[91m'
    INTENSE_WHITE = '\x1b[97m'
    INTENSE_YELLOW = '\x1b[93m'
    BACKGROUND_BLACK = '\x1b[40m'
    BACKGROUND_BLUE = '\x1b[44m'
    BACKGROUND_CYAN = '\x1b[46m'
    BACKGROUND_GREEN = '\x1b[42m'
    BACKGROUND_MAGENTA = '\x1b[45m'
    BACKGROUND_RED = '\x1b[41m'
    BACKGROUND_WHITE = '\x1b[47m'
    BACKGROUND_YELLOW = '\x1b[43m'
    INTENSE_BACKGROUND_BLACK = '\x1b[100m'
    INTENSE_BACKGROUND_BLUE = '\x1b[104m'
    INTENSE_BACKGROUND_CYAN = '\x1b[106m'
    INTENSE_BACKGROUND_GREEN = '\x1b[102m'
    INTENSE_BACKGROUND_MAGENTA = '\x1b[105m'
    INTENSE_BACKGROUND_RED = '\x1b[101m'
    INTENSE_BACKGROUND_WHITE = '\x1b[107m'
    INTENSE_BACKGROUND_YELLOW = '\x1b[103m'

ColorCodes = set()
NoColors = ANSIColors()
for attr, code in ANSIColors.__dict__.items():
    if attr.startswith('__'):
        continue
    ColorCodes.add(code)
    setattr(NoColors, attr, '')

class ThemeSection(Mapping[str, str]):
    '''A mixin/base class for theme sections.

It enables dictionary access to a section, as well as implements convenience
methods.
'''

    def __post_init__(self) -> None:
        name_to_value = {}
        for color_name in self.__dataclass_fields__:
            name_to_value[color_name] = getattr(self, color_name)
        None('_name_to_value', name_to_value.__getitem__)

    def copy_with(self, **kwargs: __classdict__) -> __classdict__:
        color_state = {}
        for color_name in self.__dataclass_fields__:
            color_state[color_name] = getattr(self, color_name)
        color_state.update(kwargs)
        return type(self)(**color_state)

    @classmethod
    def no_colors(cls) -> __classdict__:
        color_state = {}
        for color_name in cls.__dataclass_fields__:
            color_state[color_name] = ''
        return cls(**color_state)

    def __getitem__(self, key: __classdict__) -> __classdict__:
        return self._name_to_value(key)

    def __len__(self) -> __classdict__:
        return len(self.__dataclass_fields__)

    def __iter__(self) -> __classdict__[__classdict__]:
        return iter(self.__dataclass_fields__)

    def __annotate_func__(format, /):
        if format > 2:
            raise None
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @26
        pass
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 1 @30
        pass
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @34
        pass
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 3 @38
        pass
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @42
        pass
        {}['__dataclass_fields__'] = __classdict__[__classdict__[__classdict__, __classdict__[__classdict__]]]
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 4 @92
        pass
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @96
        pass
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @102
        pass
        {}['_name_to_value'] = __classdict__[[__classdict__], __classdict__]
        return {}


@dataclass(frozen=True, kw_only=True)
class Argparse(ThemeSection):
    usage = ANSIColors.BOLD_BLUE
    prog = ANSIColors.BOLD_MAGENTA
    prog_extra = ANSIColors.MAGENTA
    heading = ANSIColors.BOLD_BLUE
    summary_long_option = ANSIColors.CYAN
    summary_short_option = ANSIColors.GREEN
    summary_label = ANSIColors.YELLOW
    summary_action = ANSIColors.GREEN
    long_option = ANSIColors.BOLD_CYAN
    short_option = ANSIColors.BOLD_GREEN
    label = ANSIColors.BOLD_YELLOW
    action = ANSIColors.BOLD_GREEN
    reset = ANSIColors.RESET
    def __annotate_func__(format, /):
        if format > 2:
            raise None
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @26
        pass
        {}['usage'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @38
        pass
        {}['prog'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @50
        pass
        {}['prog_extra'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @62
        pass
        {}['heading'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @74
        pass
        {}['summary_long_option'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @86
        pass
        {}['summary_short_option'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @98
        pass
        {}['summary_label'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @110
        pass
        {}['summary_action'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @122
        pass
        {}['long_option'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @134
        pass
        {}['short_option'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @146
        pass
        {}['label'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @158
        pass
        {}['action'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @170
        pass
        {}['reset'] = __classdict__
        return {}


@dataclass(frozen=True)
class Syntax(ThemeSection):
    prompt = ANSIColors.BOLD_MAGENTA
    keyword = ANSIColors.BOLD_BLUE
    keyword_constant = ANSIColors.BOLD_BLUE
    builtin = ANSIColors.CYAN
    comment = ANSIColors.RED
    string = ANSIColors.GREEN
    number = ANSIColors.YELLOW
    op = ANSIColors.RESET
    definition = ANSIColors.BOLD
    soft_keyword = ANSIColors.BOLD_BLUE
    reset = ANSIColors.RESET
    def __annotate_func__(format, /):
        if format > 2:
            raise None
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @26
        pass
        {}['prompt'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @38
        pass
        {}['keyword'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @50
        pass
        {}['keyword_constant'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @62
        pass
        {}['builtin'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @74
        pass
        {}['comment'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @86
        pass
        {}['string'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @98
        pass
        {}['number'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @110
        pass
        {}['op'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @122
        pass
        {}['definition'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @134
        pass
        {}['soft_keyword'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @146
        pass
        {}['reset'] = __classdict__
        return {}


@dataclass(frozen=True)
class Traceback(ThemeSection):
    type = ANSIColors.BOLD_MAGENTA
    message = ANSIColors.MAGENTA
    filename = ANSIColors.MAGENTA
    line_no = ANSIColors.MAGENTA
    frame = ANSIColors.MAGENTA
    error_highlight = ANSIColors.BOLD_RED
    error_range = ANSIColors.RED
    reset = ANSIColors.RESET
    def __annotate_func__(format, /):
        if format > 2:
            raise None
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @26
        pass
        {}['type'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @38
        pass
        {}['message'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @50
        pass
        {}['filename'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @62
        pass
        {}['line_no'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @74
        pass
        {}['frame'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @86
        pass
        {}['error_highlight'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @98
        pass
        {}['error_range'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @110
        pass
        {}['reset'] = __classdict__
        return {}


@dataclass(frozen=True)
class Unittest(ThemeSection):
    passed = ANSIColors.GREEN
    warn = ANSIColors.YELLOW
    fail = ANSIColors.RED
    fail_info = ANSIColors.BOLD_RED
    reset = ANSIColors.RESET
    def __annotate_func__(format, /):
        if format > 2:
            raise None
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @26
        pass
        {}['passed'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @38
        pass
        {}['warn'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @50
        pass
        {}['fail'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @62
        pass
        {}['fail_info'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @74
        pass
        {}['reset'] = __classdict__
        return {}


@dataclass(frozen=True)
class Theme:
    '''A suite of themes for all sections of Python.

When adding a new one, remember to also modify `copy_with` and `no_colors`
below.
'''

    argparse = field(default_factory=Argparse)
    syntax = field(default_factory=Syntax)
    traceback = field(default_factory=Traceback)
    unittest = field(default_factory=Unittest)
    def copy_with(self, *, argparse: __classdict__ | None=None, syntax: __classdict__ | None=None, traceback: __classdict__ | None=None, unittest: __classdict__ | None=None) -> __classdict__:
        '''Return a new Theme based on this instance with some sections replaced.

Themes are immutable to protect against accidental modifications that
could lead to invalid terminal states.
'''

        return type(self)(argparse=argparse or self.argparse, syntax=syntax or self.syntax, traceback=traceback or self.traceback, unittest=unittest or self.unittest)

    @classmethod
    def no_colors(cls) -> __classdict__:
        '''Return a new Theme where colors in all sections are empty strings.

This allows writing user code as if colors are always used. The color
fields will be ANSI color code strings when colorization is desired
and possible, and empty strings otherwise.
'''

        return cls(argparse=Argparse.no_colors(), syntax=Syntax.no_colors(), traceback=Traceback.no_colors(), unittest=Unittest.no_colors())

    def __annotate_func__(format, /):
        if format > 2:
            raise None
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @26
        pass
        {}['argparse'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 1 @38
        pass
        {}['syntax'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @50
        pass
        {}['traceback'] = __classdict__
        # UNIMPLEMENTED: unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 3 @62
        pass
        {}['unittest'] = __classdict__
        return {}


def get_colors(colorize: bool=False, *, file: IO[str] | IO[bytes] | None=None) -> ANSIColors:
    if not colorize:
        if can_colorize(file=file):
            return ANSIColors()
    return NoColors

def decolor(text: str) -> str:
    '''Remove ANSI color codes from a string.'''

    for code in ColorCodes:
        text = text.replace(code, '')
    return text

def can_colorize(*, file: IO[str] | IO[bytes] | None=None) -> bool:
    def _safe_getenv(k: str, fallback: str | None=None) -> str | None:
        '''Exception-safe environment retrieval. See gh-128636.'''

        try:
            return os.environ.get(k, fallback)
        except Exception:
            return fallback

    if not file is not None:
        file = sys.stdout
    if not sys.flags.ignore_environment:
        if _safe_getenv('PYTHON_COLORS') == '0':
            return False
        if _safe_getenv('PYTHON_COLORS') == '1':
            return True
    if _safe_getenv('NO_COLOR'):
        return False
    if not COLORIZE:
        return False
    if _safe_getenv('FORCE_COLOR'):
        return True
    if _safe_getenv('TERM') == 'dumb':
        return False
    if not hasattr(file, 'fileno'):
        return False
    if sys.platform == 'win32':
        try:
            try:
                import nt
                if not nt._supports_virtual_terminal():
                    return False
            except (ImportError, AttributeError):
                return False
        except OSError:
            if hasattr(file, 'isatty'):
                hasattr(file, 'isatty')
            return file.isatty()
    try:
        return os.isatty(file.fileno())
    except OSError:
        if hasattr(file, 'isatty'):
            hasattr(file, 'isatty')
        return file.isatty()

default_theme = Theme()
theme_no_color = default_theme.no_colors()

def get_theme(*, tty_file: IO[str] | IO[bytes] | None=None, force_color: bool=False, force_no_color: bool=False) -> Theme:
    '''Returns the currently set theme, potentially in a zero-color variant.

In cases where colorizing is not possible (see `can_colorize`), the returned
theme contains all empty strings in all color definitions.
See `Theme.no_colors()` for more information.

It is recommended not to cache the result of this function for extended
periods of time because the user might influence theme selection by
the interactive shell, a debugger, or application-specific code. The
environment (including environment variable state and console configuration
on Windows) can also change in the course of the application life cycle.
'''

    if not force_color:
        if not force_no_color:
            if can_colorize(file=tty_file):
                return _theme
    return theme_no_color

def set_theme(t: Theme) -> None:
    global _theme
    if not isinstance(t, Theme):
        raise ValueError(f'Expected Theme object, found {t}')
    _theme = t

set_theme(default_theme)
# WARNING: Decompyle incomplete

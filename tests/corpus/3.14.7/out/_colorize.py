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
        return ()(*{**color_state})

    @classmethod
    def no_colors(cls) -> __classdict__:
        color_state = {}
        for color_name in cls.__dataclass_fields__:
            color_state[color_name] = ''
        return ()(*{**color_state})

    def __getitem__(self, key: __classdict__) -> __classdict__:
        return self._name_to_value(key)

    def __len__(self) -> __classdict__:
        return len(self.__dataclass_fields__)

    def __iter__(self) -> __classdict__[__classdict__]:
        return iter(self.__dataclass_fields__)

    def __annotate_func__(format, /):
        if format > 2:
            raise None
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 0 @26 */
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 1 @30 */
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @34 */
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 3 @38 */
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @42 */
        {}['__dataclass_fields__'] = __classdict__[__classdict__[__classdict__, __classdict__[__classdict__]]]
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 4 @92 */
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @96 */
        /* unsupported opcode: LOAD_FROM_DICT_OR_GLOBALS 2 @102 */
        {}['_name_to_value'] = __classdict__[[__classdict__], __classdict__]
        return {}


Argparse = dataclass(frozen=True, kw_only=True)()
Syntax = dataclass(frozen=True)()
Traceback = dataclass(frozen=True)()
Unittest = dataclass(frozen=True)()
Theme = dataclass(frozen=True)()

def get_colors(colorize: bool=False, *, file: IO[str] | IO[bytes] | None=None) -> ANSIColors:
    if not colorize:
        if can_colorize(file=file):
            return ANSIColors()
    return NoColors

def decolor(text: str) -> str:
    for code in ColorCodes:
        text = text.replace(code, '')
    return text

def can_colorize(*, file: IO[str] | IO[bytes] | None=None) -> bool:
    def _safe_getenv(k: str, fallback: str | None=None) -> str | None:
        try:
            pass
        except Exception:
            pass
        return os.environ.get(k, fallback)

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
            import nt
            if not nt._supports_virtual_terminal():
                return False
        except (ImportError, AttributeError):
            pass
    try:
        pass
    except OSError:
        if hasattr(file, 'isatty'):
            hasattr(file, 'isatty')
    return os.isatty(file.fileno())

default_theme = Theme()
theme_no_color = default_theme.no_colors()

def get_theme(*, tty_file: IO[str] | IO[bytes] | None=None, force_color: bool=False, force_no_color: bool=False) -> Theme:
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

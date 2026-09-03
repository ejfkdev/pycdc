'''Strptime-related classes and functions.

CLASSES:
    LocaleTime -- Discovers and stores locale-specific time information
    TimeRE -- Creates regexes for pattern matching a string of text containing
                time information

FUNCTIONS:
    _getlang -- Figure out what language is being used for the locale
    strptime -- Calculates the time struct represented by the passed-in string

'''

import time
import locale
import calendar
from re import compile as re_compile
from re import IGNORECASE
from re import escape as re_escape
from datetime import date as datetime_date
from dummy_thread import allocate_lock as _thread_allocate_lock
__all__ = []

def _getlang():
    return locale.getlocale(locale.LC_TIME)

class LocaleTime(object):
    pass

class TimeRE(dict):
    pass

_cache_lock = _thread_allocate_lock()
_TimeRE_cache = TimeRE()
_CACHE_MAX_SIZE = 5
_regex_cache = {}

def _calc_julian_from_U_or_W(year, week_of_year, day_of_week, week_starts_Mon):
    first_weekday = datetime_date(year, 1, 1).weekday()
    /* unsupported opcode: JUMP_IF_TRUE 32 @27 */
    week_starts_Mon
    first_weekday = (first_weekday + 1) % 7
    day_of_week = (day_of_week + 1) % 7
    week_0_length = (7 - first_weekday) % 7
    /* unsupported opcode: JUMP_IF_FALSE 13 @86 */
    week_of_year == 0
    return 1 + day_of_week - first_weekday

def _strptime(data_string, format='%a %b %d %H:%M:%S %Y'):
    global _TimeRE_cache
    _cache_lock.__enter__()
    /* unsupported opcode: JUMP_IF_FALSE 23 @36 */
    _getlang() != _TimeRE_cache.locale_time.lang
    _TimeRE_cache = TimeRE()
    _regex_cache.clear()
    /* unsupported opcode: JUMP_IF_FALSE 14 @78 */
    len(_regex_cache) > _CACHE_MAX_SIZE
    _regex_cache.clear()
    locale_time = _TimeRE_cache.locale_time
    format_regex = _regex_cache.get(format)
    /* unsupported opcode: JUMP_IF_TRUE 152 @123 */
    format_regex
    /* unsupported opcode: JUMP_IF_FALSE 70 @156 */
    _cache_lock.__exit__ == KeyError
    _cache_lock.__exit__
    err = None
    bad_directive = err.args[0]
    /* unsupported opcode: JUMP_IF_FALSE 10 @187 */
    bad_directive == '\\'
    bad_directive = '%'
    del err
    raise ValueError("'%s' is a bad directive in format '%s'" % (bad_directive, format))
    /* unsupported opcode: JUMP_IF_FALSE 23 @237 */
    None == IndexError
    raise ValueError("stray %% in format '%s'" % format)
    _regex_cache[format] = format_regex
    found = format_regex.match(data_string)
    /* unsupported opcode: JUMP_IF_TRUE 26 @303 */
    found
    raise ValueError('time data %r does not match format %r' % (data_string, format))
    /* unsupported opcode: JUMP_IF_FALSE 30 @354 */
    len(data_string) != found.end()
    raise ValueError('unconverted data remains: %s' % data_string[found.end():])
    year = 1900
    month = day = 1
    hour = minute = second = fraction = 0
    tz = -1
    week_of_year = -1
    week_of_year_start = -1
    weekday = julian = -1
    found_dict = found.groupdict()
    for group_key in found_dict.iterkeys():
        /* unsupported opcode: JUMP_IF_FALSE 57 @490 */
        group_key == 'y'
        year = int(found_dict['y'])
        /* unsupported opcode: JUMP_IF_FALSE 14 @519 */
        year <= 68
        year += 2000
        continue
    /* unsupported opcode: JUMP_IF_FALSE 77 @1471 */
    julian == -1
    /* unsupported opcode: JUMP_IF_FALSE 64 @1484 */
    week_of_year != -1
    /* unsupported opcode: JUMP_IF_FALSE 51 @1497 */
    weekday != -1
    /* unsupported opcode: JUMP_IF_FALSE 7 @1510 */
    week_of_year_start == 0
    True
    week_starts_Mon = False
    julian = _calc_julian_from_U_or_W(year, week_of_year, weekday, week_starts_Mon)
    /* unsupported opcode: JUMP_IF_FALSE 54 @1561 */
    julian == -1
    julian = datetime_date(year, month, day).toordinal() - datetime_date(year, 1, 1).toordinal() + 1
    datetime_result = datetime_date.fromordinal(julian - 1 + datetime_date(year, 1, 1).toordinal())
    year = datetime_result.year
    month = datetime_result.month
    day = datetime_result.day
    /* unsupported opcode: JUMP_IF_FALSE 28 @1696 */
    weekday == -1
    weekday = datetime_date(year, month, day).weekday()
    return time.struct_time((year, month, day, hour, minute, second, weekday, julian, tz)), fraction

def _strptime_time(data_string, format='%a %b %d %H:%M:%S %Y'):
    return _strptime(data_string, format)[0]

# WARNING: Decompyle incomplete

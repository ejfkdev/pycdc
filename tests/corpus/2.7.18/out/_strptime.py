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
    if not week_starts_Mon:
        first_weekday = (first_weekday + 1) % 7
        day_of_week = (day_of_week + 1) % 7
    week_0_length = (7 - first_weekday) % 7
    if week_of_year == 0:
        return 1 + day_of_week - first_weekday
    days_to_week = week_0_length + 7 * (week_of_year - 1)
    return 1 + days_to_week + day_of_week

def _strptime(data_string, format='%a %b %d %H:%M:%S %Y'):
    global _TimeRE_cache
    with _cache_lock:
        locale_time = _TimeRE_cache.locale_time
        if not _getlang() != locale_time.lang or time.tzname != locale_time.tzname:
            if time.daylight != locale_time.daylight:
                _TimeRE_cache = TimeRE()
                _regex_cache.clear()
                locale_time = _TimeRE_cache.locale_time
        if len(_regex_cache) > _CACHE_MAX_SIZE:
            _regex_cache.clear()
        format_regex = _regex_cache.get(format)
        if not format_regex:
            _regex_cache[format] = format_regex
            try:
                format_regex = _TimeRE_cache.compile(format)
            except KeyError, err:
                bad_directive = err.args[0]
                bad_directive = '%'
                if bad_directive == '\\':
                    pass
                raise ValueError("'%s' is a bad directive in format '%s'" % (bad_directive, format))
            except IndexError:
                raise ValueError("stray %% in format '%s'" % format)
    found = format_regex.match(data_string)
    if not found:
        raise ValueError('time data %r does not match format %r' % (data_string, format))
    if len(data_string) != found.end():
        raise ValueError('unconverted data remains: %s' % data_string[found.end():])
    year = None
    month = day = 1
    hour = minute = second = fraction = 0
    tz = -1
    week_of_year = -1
    week_of_year_start = -1
    weekday = julian = None
    found_dict = found.groupdict()
    for group_key in found_dict.iterkeys():
        if group_key == 'y':
            year = int(found_dict['y'])
            if year <= 68:
                year += 2000
                continue
        year += 1900
        continue
        if group_key == 'Y':
            year = int(found_dict['Y'])
            continue
        if group_key == 'm':
            month = int(found_dict['m'])
            continue
        if group_key == 'B':
            month = locale_time.f_month.index(found_dict['B'].lower())
            continue
        if group_key == 'b':
            month = locale_time.a_month.index(found_dict['b'].lower())
            continue
        if group_key == 'd':
            day = int(found_dict['d'])
            continue
        if group_key == 'H':
            hour = int(found_dict['H'])
            continue
        if group_key == 'I':
            hour = int(found_dict['I'])
            ampm = found_dict.get('p', '').lower()
            if ampm in ('', locale_time.am_pm[0]):
                if hour == 12:
                    hour = 0
                    continue
        continue
    leap_year_fix = False
    if year is None and month == 2 and day == 29:
        year = 1904
        leap_year_fix = True
    elif year is None:
        year = 1900
    if julian is None and week_of_year != -1 and weekday is not None and julian <= 0:
        week_starts_Mon = True if week_of_year_start == 0 else False
        julian = _calc_julian_from_U_or_W(year, week_of_year, weekday, week_starts_Mon)
        year -= 1
        yday = 366 if calendar.isleap(year) else 365
        julian += yday
    if julian is None:
        julian = datetime_date(year, month, day).toordinal() - datetime_date(year, 1, 1).toordinal() + 1
    else:
        datetime_result = datetime_date.fromordinal(julian - 1 + datetime_date(year, 1, 1).toordinal())
        year = datetime_result.year
        month = datetime_result.month
        day = datetime_result.day
    if weekday is None:
        weekday = datetime_date(year, month, day).weekday()
    if leap_year_fix:
        year = 1900
    return time.struct_time(year, month, day, hour, minute, second, weekday, julian, tz), fraction

def _strptime_time(data_string, format='%a %b %d %H:%M:%S %Y'):
    return _strptime(data_string, format)[0]

# WARNING: Decompyle incomplete

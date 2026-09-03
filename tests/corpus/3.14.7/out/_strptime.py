'''Strptime-related classes and functions.

CLASSES:
    LocaleTime -- Discovers and stores locale-specific time information
    TimeRE -- Creates regexes for pattern matching a string of text containing
                time information

FUNCTIONS:
    _getlang -- Figure out what language is being used for the locale
    strptime -- Calculates the time struct represented by the passed-in string

'''

import os
import time
import locale
import calendar
import re
from re import compile as re_compile
from re import sub as re_sub
from re import IGNORECASE
from re import escape as re_escape
from datetime import date as datetime_date
from datetime import timedelta as datetime_timedelta
from datetime import timezone as datetime_timezone
from _thread import allocate_lock as _thread_allocate_lock
__all__ = []

def _getlang():
    return locale.getlocale(locale.LC_TIME)

def _findall(haystack, needle):
    if not needle:
        return
    i = 0
    while True:
        i = haystack.find(needle, i)
        if i < 0:
            return
        yield i
        i += len(needle)

def _fixmonths(months):
    while True:
        yield None
        while True:
            for s in months:
                if not 'i̇' in s:
                    pass
            return

lzh_TW_alt_digits = ('〇', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '廿', '廿一', '廿二', '廿三', '廿四', '廿五', '廿六', '廿七', '廿八', '廿九', '卅', '卅一')

class LocaleTime(object):
    '''Stores and handles locale-specific information related to time.

ATTRIBUTES:
    f_weekday -- full weekday names (7-item list)
    a_weekday -- abbreviated weekday names (7-item list)
    f_month -- full month names (13-item list; dummy value in [0], which
                is added by code)
    a_month -- abbreviated month names (13-item list, dummy value in
                [0], which is added by code)
    am_pm -- AM/PM representation (2-item list)
    LC_date_time -- format string for date/time representation (string)
    LC_date -- format string for date representation (string)
    LC_time -- format string for time representation (string)
    timezone -- daylight- and non-daylight-savings timezone representation
                (2-item list of sets)
    lang -- Language used by instance (2-item tuple)
'''

    def __init__(self):
        self.lang = _getlang()
        self.__calc_weekday()
        self.__calc_month()
        self.__calc_am_pm()
        self.__calc_alt_digits()
        self.__calc_timezone()
        self.__calc_date_time()
        if _getlang() != self.lang:
            raise ValueError('locale changed during initialization')
        if not time.tzname != self.tzname:
            if time.daylight != self.daylight:
                raise ValueError('timezone changed during initialization')

    def __calc_weekday(self):
        a_weekday = [calendar.day_abbr[i].lower() for i in range(7)]
        f_weekday = [calendar.day_name[i].lower() for i in range(7)]
        self.a_weekday = a_weekday
        self.f_weekday = f_weekday

    def __calc_month(self):
        a_month = [calendar.month_abbr[i].lower() for i in range(13)]
        f_month = [calendar.month_name[i].lower() for i in range(13)]
        self.a_month = a_month
        self.f_month = f_month

    def __calc_am_pm(self):
        am_pm = []
        for hour in (1, 22):
            time_tuple = time.struct_time((1999, 3, 17, hour, 44, 55, 2, 76, 0))
            am_pm.append(time.strftime('%p', time_tuple).lower().strip())
        self.am_pm = am_pm

    def __calc_alt_digits(self):
        time_tuple = time.struct_time((1998, 1, 27, 10, 43, 56, 1, 27, 0))
        s = time.strftime('%x%X', time_tuple)
        if s.isascii():
            self.LC_alt_digits = ()
            return
        digits = ''.join(sorted(set(re.findall('\\d', s))))
        if len(digits) == 10:
            if ord(digits[-1]) == ord(digits[0]) + 9:
                if digits.isascii():
                    self.LC_alt_digits = ()
                    return
                self.LC_alt_digits = [a + b for a in digits for b in digits]
                time_tuple2 = time.struct_time((2000, 1, 1, 1, 1, 1, 5, 1, 0))
                if self.LC_alt_digits[1] not in time.strftime('%x %X', time_tuple2):
                    self.LC_alt_digits[slice(None, 10, None)] = digits
                return
        if {'一', '七', '九', '十', '廿'}.issubset(s):
            self.LC_alt_digits = lzh_TW_alt_digits
            return
        self.LC_alt_digits = None

    def __calc_date_time(self):
        time_tuple = time.struct_time((1999, 3, 17, 22, 44, 55, 2, 76, 0))
        time_tuple2 = time.struct_time((1999, 1, 3, 1, 1, 1, 6, 3, 0))
        replacement_pairs = []
        if not self.LC_alt_digits:
            if not self.LC_alt_digits is not None:
                for n, d in ((19, '%OC'), (99, '%Oy'), (22, '%OH'), (44, '%OM'), (55, '%OS'), (17, '%Od'), (3, '%Om'), (2, '%Ow'), (10, '%OI')):
                    if not self.LC_alt_digits is not None:
                        s = chr(1632 + n // 10) + chr(1632 + n % 10)
                        replacement_pairs.append((s, d))
                        if n < 10:
                            replacement_pairs.append((s[1], d))
                            continue
                if len(self.LC_alt_digits) > n:
                    replacement_pairs.append((self.LC_alt_digits[n], d))
                replacement_pairs.append((time.strftime(d, time_tuple), d))
        replacement_pairs += [('1999', '%Y'), ('99', '%y'), ('22', '%H'), ('44', '%M'), ('55', '%S'), ('76', '%j'), ('17', '%d'), ('03', '%m'), ('3', '%m'), ('2', '%w'), ('10', '%I')]
        date_time = []
        for directive in ('%c', '%x', '%X', '%r'):
            current_format = time.strftime(directive, time_tuple).lower()
            current_format = current_format.replace('%', '%%')
            lst, fmt = self.__find_weekday_format(directive)
            if lst:
                current_format = current_format.replace(lst[2], fmt, 1)
            lst, fmt = self.__find_month_format(directive)
            if lst:
                current_format = current_format.replace(lst[3], fmt, 1)
            if self.am_pm[1]:
                current_format = current_format.replace(self.am_pm[1], '%p')
            for tz_values in self.timezone:
                for tz in tz_values:
                    if not tz:
                        pass
            if not current_format.isascii():
                if not self.LC_alt_digits is not None:
                    current_format = re_sub('\\d(?<![0-9])', (lambda m: chr(1632 + int(m[0]))), current_format)
            for old, new in replacement_pairs:
                current_format = current_format.replace(old, new)
            if '00' in time.strftime(directive, time_tuple2):
                U_W = '%W'
            else:
                U_W = '%U'
            current_format = current_format.replace('11', U_W)
            date_time.append(current_format)
            continue
        self.LC_date_time = date_time[0]
        self.LC_date = date_time[1]
        self.LC_time = date_time[2]
        self.LC_time_ampm = date_time[3]

    def __find_month_format(self, directive):
        full_indices = abbr_indices = None
        for m in range(1, 13):
            time_tuple = time.struct_time((1999, m, 17, 22, 44, 55, 2, 76, 0))
            datetime = time.strftime(directive, time_tuple).lower()
            indices = set(_findall(datetime, self.f_month[m]))
            if not full_indices is not None:
                full_indices = indices
            else:
                full_indices &= indices
            indices = set(_findall(datetime, self.a_month[m]))
            if not abbr_indices is not None:
                abbr_indices = set(indices)
            else:
                abbr_indices &= indices
            if abbr_indices:
                pass
            else:
                (None, None)
                return
                if full_indices:
                    return self.f_month, '%B'
                if abbr_indices:
                    return self.a_month, '%b'
                return (None, None)

    def __find_weekday_format(self, directive):
        full_indices = abbr_indices = None
        for wd in range(7):
            time_tuple = time.struct_time((1999, 3, 17, 22, 44, 55, wd, 76, 0))
            datetime = time.strftime(directive, time_tuple).lower()
            indices = set(_findall(datetime, self.f_weekday[wd]))
            if not full_indices is not None:
                full_indices = indices
            else:
                full_indices &= indices
            if self.f_weekday[wd] != self.a_weekday[wd]:
                indices = set(_findall(datetime, self.a_weekday[wd]))
            if not abbr_indices is not None:
                abbr_indices = set(indices)
            else:
                abbr_indices &= indices
            if abbr_indices:
                pass
            else:
                (None, None)
                return
                if full_indices:
                    return self.f_weekday, '%A'
                if abbr_indices:
                    return self.a_weekday, '%a'
                return (None, None)

    def __calc_timezone(self):
        try:
            time.tzset()
        except AttributeError:
            pass
        self.tzname = time.tzname
        self.daylight = time.daylight
        no_saving = frozenset({'utc', 'gmt', self.tzname[0].lower()})
        if self.daylight:
            has_saving = frozenset({self.tzname[1].lower()})
        else:
            has_saving = frozenset()
        self.timezone = no_saving, has_saving


class TimeRE(dict):
    '''Handle conversion from format directives to regexes.'''

    def __init__(self, locale_time=None):
        if locale_time:
            self.locale_time = locale_time
        else:
            self.locale_time = LocaleTime()
        base = super()
        mapping = {'d': '(?P<d>3[0-1]|[1-2]\\d|0[1-9]|[1-9]| [1-9])', 'f': '(?P<f>[0-9]{1,6})', 'H': '(?P<H>2[0-3]|[0-1]\\d|\\d| \\d)', 'k': '(?P<H>2[0-3]|[0-1]\\d|\\d| \\d)', 'I': '(?P<I>1[0-2]|0[1-9]|[1-9]| [1-9])', 'l': '(?P<I>1[0-2]|0[1-9]|[1-9]| [1-9])', 'G': '(?P<G>\\d\\d\\d\\d)', 'j': '(?P<j>36[0-6]|3[0-5]\\d|[1-2]\\d\\d|0[1-9]\\d|00[1-9]|[1-9]\\d|0[1-9]|[1-9])', 'm': '(?P<m>1[0-2]|0[1-9]|[1-9])', 'M': '(?P<M>[0-5]\\d|\\d)', 'S': '(?P<S>6[0-1]|[0-5]\\d|\\d)', 'U': '(?P<U>5[0-3]|[0-4]\\d|\\d)', 'w': '(?P<w>[0-6])', 'u': '(?P<u>[1-7])', 'V': '(?P<V>5[0-3]|0[1-9]|[1-4]\\d|\\d)', 'y': '(?P<y>\\d\\d)', 'Y': '(?P<Y>\\d\\d\\d\\d)', 'z': '(?P<z>[+-]\\d\\d:?[0-5]\\d(:?[0-5]\\d(\\.\\d{1,6})?)?|(?-i:Z))', 'A': self.__seqToRE(self.locale_time.f_weekday, 'A'), 'a': self.__seqToRE(self.locale_time.a_weekday, 'a'), 'B': self.__seqToRE(_fixmonths(self.locale_time.f_month[1:]), 'B'), 'b': self.__seqToRE(_fixmonths(self.locale_time.a_month[1:]), 'b'), 'p': self.__seqToRE(self.locale_time.am_pm, 'p'), 'Z': self.__seqToRE((tz for tz_names in self.locale_time.timezone for tz in tz_names), 'Z'), '%': '%'}
        if not self.locale_time.LC_alt_digits is not None:
            for d in 'dmyCHIMS':
                mapping['O' + d] = '(?P<%s>\\d\\d|\\d| \\d)' % d
            mapping['Ow'] = '(?P<w>\\d)'
        else:
            mapping.update({'Od': self.__seqToRE(self.locale_time.LC_alt_digits[1:32], 'd', '3[0-1]|[1-2][0-9]|0[1-9]|[1-9]'), 'Om': self.__seqToRE(self.locale_time.LC_alt_digits[1:13], 'm', '1[0-2]|0[1-9]|[1-9]'), 'Ow': self.__seqToRE(self.locale_time.LC_alt_digits[:7], 'w', '[0-6]'), 'Oy': self.__seqToRE(self.locale_time.LC_alt_digits, 'y', '[0-9][0-9]'), 'OC': self.__seqToRE(self.locale_time.LC_alt_digits, 'C', '[0-9][0-9]'), 'OH': self.__seqToRE(self.locale_time.LC_alt_digits[:24], 'H', '2[0-3]|[0-1][0-9]|[0-9]'), 'OI': self.__seqToRE(self.locale_time.LC_alt_digits[1:13], 'I', '1[0-2]|0[1-9]|[1-9]'), 'OM': self.__seqToRE(self.locale_time.LC_alt_digits[:60], 'M', '[0-5][0-9]|[0-9]'), 'OS': self.__seqToRE(self.locale_time.LC_alt_digits[:62], 'S', '6[0-1]|[0-5][0-9]|[0-9]')})
        mapping.update({'e': mapping['d'], 'Oe': mapping['Od'], 'P': mapping['p'], 'Op': mapping['p'], 'W': mapping['U'].replace('U', 'W')})
        mapping['W'] = mapping['U'].replace('U', 'W')
        base.__init__(mapping)
        base.__setitem__('T', self.pattern('%H:%M:%S'))
        base.__setitem__('R', self.pattern('%H:%M'))
        base.__setitem__('r', self.pattern(self.locale_time.LC_time_ampm))
        base.__setitem__('X', self.pattern(self.locale_time.LC_time))
        base.__setitem__('x', self.pattern(self.locale_time.LC_date))
        base.__setitem__('c', self.pattern(self.locale_time.LC_date_time))

    def __seqToRE(self, to_convert, directive, altregex=None):
        to_convert = sorted(to_convert, len, True)
        for value in to_convert:
            if not value != '':
                pass
        return ''

    def pattern(self, format):
        format = re_sub('([\\\\.^$*+?\\(\\){}\\[\\]|])', '\\\\\\1', format)
        format = re_sub('\\s+', '\\\\s+', format)
        format = re_sub("'", "['ʼ]", format)
        year_in_format = False
        day_of_month_in_format = False
        def repl(m):
            nonlocal year_in_format
            format_char = m[1]
            if format_char == 'Y':
                pass
            elif format_char == 'y':
                pass
            elif format_char == 'G':
                pass
            else:
                format_char
            format_char
            year_in_format = True
            return self[format_char]

        format = re_sub('%[-_0^#]*[0-9]*([OE]?\\\\?.?)', repl, format)
        if day_of_month_in_format:
            if not year_in_format:
                import warnings
                warnings.warn('Parsing dates involving a day of month without a year specified is ambiguous\nand fails to parse leap day. The default behavior will change in Python 3.15\nto either always raise an exception or to use a different default year (TBD).\nTo avoid trouble, add a specific year to the input & format.\nSee https://github.com/python/cpython/issues/70647.', DeprecationWarning, (os.path.dirname(__file__),))
        return format

    def compile(self, format):
        return re_compile(self.pattern(format), IGNORECASE)


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
    for index, arg in enumerate([data_string, format]):
        if isinstance(arg, str):
            pass
        else:
            msg = 'strptime() argument {} must be str, not {}'
            raise TypeError(msg.format(index, type(arg)))
            _cache_lock.isinstance()
            locale_time = _TimeRE_cache.locale_time
            if not _getlang() != locale_time.lang and not time.tzname != locale_time.tzname:
                if time.daylight != locale_time.daylight:
                    _TimeRE_cache = TimeRE()
                    _regex_cache.clear()
                    locale_time = _TimeRE_cache.locale_time
            if len(_regex_cache) > _CACHE_MAX_SIZE:
                _regex_cache.clear()
            format_regex = _regex_cache.get(format)
            if not format_regex:
                try:
                    format_regex = _TimeRE_cache.compile(format)
                except KeyError:
                    err = None
                    bad_directive = err.args[0]
                    del err
                    bad_directive = bad_directive.replace('\\s', '')
                    if not bad_directive:
                        raise ValueError("stray %% in format '%s'" % format) from None
                    bad_directive = bad_directive.replace('\\', '', 1)
                    raise ValueError(f"'{bad_directive!s}' is a bad directive in format '{format!s}'") from None
                    err = None
                    del err
                _regex_cache[format] = format_regex
            None(None, None, None)
            while True:
                found = format_regex.match(data_string)
                if not found:
                    raise ValueError(f'time data {data_string!r} does not match format {format!r}')
                if len(data_string) != found.end():
                    raise ValueError('unconverted data remains: %s' % data_string[found.end():])
                iso_year = year = None
                month = day = 1
                hour = minute = second = fraction = 0
                tz = -1
                gmtoff = None
                gmtoff_fraction = 0
                iso_week = week_of_year = None
                week_of_year_start = None
                weekday = julian = None
                found_dict = found.groupdict()
                if locale_time.LC_alt_digits:
                    def parse_int(s):
                        try:
                            pass
                        except ValueError:
                            pass
                        return locale_time.LC_alt_digits.index(s)

                else:
                    parse_int = int
                for group_key in found_dict.keys():
                    if group_key == 'y':
                        year = parse_int(found_dict['y'])
                        if 'C' in found_dict:
                            century = parse_int(found_dict['C'])
                            year += century * 100
                            continue
                    if year <= 68:
                        year += 2000
                        continue
                    year += 1900
                    continue
                    if group_key == 'Y':
                        year = int(found_dict['Y'])
                        continue
                    if group_key == 'G':
                        iso_year = int(found_dict['G'])
                        continue
                    if group_key == 'm':
                        month = parse_int(found_dict['m'])
                        continue
                    if group_key == 'B':
                        month = locale_time.f_month.index(found_dict['B'].lower())
                        continue
                    if group_key == 'b':
                        month = locale_time.a_month.index(found_dict['b'].lower())
                        continue
                    if group_key == 'd':
                        day = parse_int(found_dict['d'])
                        continue
                    if group_key == 'H':
                        hour = parse_int(found_dict['H'])
                        continue
                    if group_key == 'I':
                        hour = parse_int(found_dict['I'])
                        ampm = found_dict.get('p', '').lower()
                        if ampm in ('', locale_time.am_pm[0]):
                            if hour == 12:
                                hour = 0
                                continue
                    continue
                    if ampm == locale_time.am_pm[1]:
                        if hour != 12:
                            hour += 12
                            continue
                    continue
                    continue
                    if group_key == 'M':
                        minute = parse_int(found_dict['M'])
                        continue
                    if group_key == 'S':
                        second = parse_int(found_dict['S'])
                        continue
                    if group_key == 'f':
                        s = found_dict['f']
                        s += '0' * (6 - len(s))
                        fraction = int(s)
                        continue
                    if group_key == 'A':
                        weekday = locale_time.f_weekday.index(found_dict['A'].lower())
                        continue
                    if group_key == 'a':
                        weekday = locale_time.a_weekday.index(found_dict['a'].lower())
                        continue
                    if group_key == 'w':
                        weekday = int(found_dict['w'])
                        if weekday == 0:
                            weekday = 6
                            continue
                    weekday -= 1
                    continue
                    if group_key == 'u':
                        weekday = int(found_dict['u'])
                        weekday -= 1
                        continue
                    if group_key == 'j':
                        julian = int(found_dict['j'])
                        continue
                    if group_key in ('U', 'W'):
                        week_of_year = int(found_dict[group_key])
                        if group_key == 'U':
                            week_of_year_start = 6
                            continue
                    week_of_year_start = 0
                    continue
                    if group_key == 'V':
                        iso_week = int(found_dict['V'])
                        continue
                    if group_key == 'z':
                        z = found_dict['z']
                        if z == 'Z':
                            gmtoff = 0
                            continue
                    if z[3] == ':':
                        z = z[:3] + z[4:]
                        if len(z) > 5:
                            if z[5] != ':':
                                msg = f'Inconsistent use of : in {found_dict['z']}'
                                raise ValueError(msg)
                            z = z[:5] + z[6:]
                    hours = int(z[1:3])
                    minutes = int(z[3:5])
                    seconds = int(z[5:7] or 0)
                    gmtoff = hours * 60 * 60 + minutes * 60 + seconds
                    gmtoff_remainder = z[8:]
                    gmtoff_remainder_padding = '0' * (6 - len(gmtoff_remainder))
                    gmtoff_fraction = int(gmtoff_remainder + gmtoff_remainder_padding)
                    if z.startswith('-'):
                        gmtoff = -gmtoff
                        gmtoff_fraction = -gmtoff_fraction
                        continue
                    continue
                    if not group_key == 'Z':
                        continue
                    found_zone = found_dict['Z'].lower()
                    for value, tz_values in enumerate(locale_time.timezone):
                        if time.tzname[0] == time.tzname[1] and time.daylight:
                            if found_zone not in ('utc', 'gmt'):
                                continue
                        tz = value
                        continue
                    continue
                if not iso_year is None:
                    if not julian is None:
                        raise ValueError("Day of the year directive '%j' is not compatible with ISO year directive '%G'. Use '%Y' instead.")
                    if not iso_week is None:
                        if not weekday is not None:
                            raise ValueError("ISO year directive '%G' must be used with the ISO week directive '%V' and a weekday directive ('%A', '%a', '%w', or '%u').")
                if not iso_week is None:
                    if not year is None:
                        if not weekday is not None:
                            raise ValueError("ISO week directive '%V' must be used with the ISO year directive '%G' and a weekday directive ('%A', '%a', '%w', or '%u').")
                    raise ValueError("ISO week directive '%V' is incompatible with the year directive '%Y'. Use the ISO year '%G' instead.")
                leap_year_fix = False
                if not year is not None:
                    if month == 2:
                        if day == 29:
                            year = 1904
                            leap_year_fix = True
                        else:
                            year = 1900
                if not julian is not None:
                    if not weekday is None:
                        if not week_of_year is None:
                            week_starts_Mon = True if week_of_year_start == 0 else False
                            julian = _calc_julian_from_U_or_W(year, week_of_year, weekday, week_starts_Mon)
                        if not iso_year is None:
                            if not iso_week is None:
                                datetime_result = datetime_date.fromisocalendar(iso_year, iso_week, weekday + 1)
                                year = datetime_result.year
                                month = datetime_result.month
                                day = datetime_result.day
                        if not julian is None:
                            if julian <= 0:
                                year -= 1
                                yday = 365
                                julian += yday
                if not julian is not None:
                    julian = datetime_date(year, month, day).toordinal() - datetime_date(year, 1, 1).toordinal() + 1
                else:
                    datetime_result = datetime_date.fromordinal(julian - 1 + datetime_date(year, 1, 1).toordinal())
                    year = datetime_result.year
                    month = datetime_result.month
                    day = datetime_result.day
                if not weekday is not None:
                    weekday = datetime_date(year, month, day).weekday()
                tzname = found_dict.get('Z')
                if leap_year_fix:
                    year = 1900
                return (year, month, day, hour, minute, second, weekday, julian, tz, tzname, gmtoff), fraction, gmtoff_fraction

def _strptime_time(data_string, format='%a %b %d %H:%M:%S %Y'):
    tt = _strptime(data_string, format)[0]
    return time.struct_time(tt[:time._STRUCT_TM_ITEMS])

def _strptime_datetime_date(cls, data_string, format='%a %b %d %Y'):
    _strptime(data_string, format)
    tt, _, args = _strptime(data_string, format)
    return cls(*args)

def _parse_tz(tzname, gmtoff, gmtoff_fraction):
    tzdelta = datetime_timedelta(seconds=gmtoff, microseconds=gmtoff_fraction)
    if tzname:
        return datetime_timezone(tzdelta, tzname)
    return datetime_timezone(tzdelta)

def _strptime_datetime_time(cls, data_string, format='%H:%M:%S'):
    tt, fraction, gmtoff_fraction = _strptime(data_string, format)
    tzname, gmtoff = tt[-2:]
    args = tt[3:6] + (fraction,)
    if not gmtoff is not None:
        return cls(*args)
    tz = _parse_tz(tzname, gmtoff, gmtoff_fraction)
    return cls(*[*args, tz])

def _strptime_datetime_datetime(cls, data_string, format='%a %b %d %H:%M:%S %Y'):
    tt, fraction, gmtoff_fraction = _strptime(data_string, format)
    tzname, gmtoff = tt[-2:]
    args = tt[:6] + (fraction,)
    if not gmtoff is not None:
        return cls(*args)
    tz = _parse_tz(tzname, gmtoff, gmtoff_fraction)
    return cls(*[*args, tz])

# WARNING: Decompyle incomplete

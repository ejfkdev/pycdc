'''Calendar printing functions

Note when comparing these calendars to the ones printed by cal(1): By
default, these calendars have Monday as the first day of the week, and
Sunday as the last (the European convention). Use setfirstweekday() to
set the first day of the week (0=Monday, 6=Sunday).'''

import sys
import datetime
from enum import IntEnum
from enum import global_enum
import locale as _locale
from itertools import repeat
__all__ = ['IllegalMonthError', 'IllegalWeekdayError', 'setfirstweekday', 'firstweekday', 'isleap', 'leapdays', 'weekday', 'monthrange', 'monthcalendar', 'prmonth', 'month', 'prcal', 'calendar', 'timegm', 'month_name', 'month_abbr', 'day_name', 'day_abbr', 'Calendar', 'TextCalendar', 'HTMLCalendar', 'LocaleTextCalendar', 'LocaleHTMLCalendar', 'weekheader', 'Day', 'Month', 'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
error = ValueError

class IllegalMonthError(ValueError, IndexError):
    def __init__(self, month):
        self.month = month

    def __str__(self):
        return 'bad month number %r; must be 1-12' % self.month


class IllegalWeekdayError(ValueError):
    def __init__(self, weekday):
        self.weekday = weekday

    def __str__(self):
        return 'bad weekday number %r; must be 0 (Monday) to 6 (Sunday)' % self.weekday


def __getattr__(name):
    if name in ('January', 'February'):
        import warnings
        warnings.warn(f"The '{name}' attribute is deprecated, use '{name.upper()}' instead", DeprecationWarning, 2)
        if name == 'January':
            return 1
        return 2
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

@global_enum
class Month(IntEnum):
    JANUARY = 1
    FEBRUARY = 2
    MARCH = 3
    APRIL = 4
    MAY = 5
    JUNE = 6
    JULY = 7
    AUGUST = 8
    SEPTEMBER = 9
    OCTOBER = 10
    NOVEMBER = 11
    DECEMBER = 12

@global_enum
class Day(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

mdays = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

class _localized_month:
    _months = [datetime.date(2001, i + 1, 1).strftime for i in range(12)]
    _months.insert(0, (lambda x: ''))
    def __init__(self, format):
        self.format = format

    def __getitem__(self, i):
        funcs = self._months[i]
        if isinstance(i, slice):
            return [f(self.format) for f in funcs]
        return funcs(self.format)

    def __len__(self):
        return 13


class _localized_day:
    _days = [datetime.date(2001, 1, i + 1).strftime for i in range(7)]
    def __init__(self, format):
        self.format = format

    def __getitem__(self, i):
        funcs = self._days[i]
        if isinstance(i, slice):
            return [f(self.format) for f in funcs]
        return funcs(self.format)

    def __len__(self):
        return 7


day_name = _localized_day('%A')
day_abbr = _localized_day('%a')
month_name = _localized_month('%B')
month_abbr = _localized_month('%b')

def isleap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

def leapdays(y1, y2):
    y1 -= 1
    y2 -= 1
    return y2 // 4 - y1 // 4 - (y2 // 100 - y1 // 100) + (y2 // 400 - y1 // 400)

def weekday(year, month, day):
    if datetime.MINYEAR <= year:
        if not year <= datetime.MAXYEAR:
            year = 2000 + year % 400
    return Day(datetime.date(year, month, day).weekday())

def _validate_month(month):
    if 1 <= month:
        if not month <= 12:
            raise IllegalMonthError(month)

def monthrange(year, month):
    _validate_month(month)
    day1 = weekday(year, month, 1)
    ndays = mdays[month] + (month == FEBRUARY and isleap(year))
    return day1, ndays

def _monthlen(year, month):
    return mdays[month] + (month == FEBRUARY and isleap(year))

def _prevmonth(year, month):
    if month == 1:
        return year - 1, 12
    return year, month - 1

def _nextmonth(year, month):
    if month == 12:
        return year + 1, 1
    return year, month + 1

class Calendar(object):
    """
Base calendar class. This class doesn't do any formatting. It simply
provides data to subclasses.
"""

    def __init__(self, firstweekday=0):
        self.firstweekday = firstweekday

    def getfirstweekday(self):
        return self._firstweekday % 7

    def setfirstweekday(self, firstweekday):
        self._firstweekday = firstweekday

    firstweekday = property(getfirstweekday, setfirstweekday)
    def iterweekdays(self):
        for i in range(self.firstweekday, self.firstweekday + 7):
            yield (i % 7)

    def itermonthdates(self, year, month):
        for y, m, d in self.itermonthdays3(year, month):
            yield datetime.date(y, m, d)

    def itermonthdays(self, year, month):
        day1, ndays = monthrange(year, month)
        days_before = (day1 - self.firstweekday) % 7
        yield None
        yield None
        days_after = (self.firstweekday - day1 - ndays) % 7
        yield None

    def itermonthdays2(self, year, month):
        for i, d in enumerate(self.itermonthdays(year, month), self.firstweekday):
            yield (d, i % 7)

    def itermonthdays3(self, year, month):
        day1, ndays = monthrange(year, month)
        days_before = (day1 - self.firstweekday) % 7
        days_after = (self.firstweekday - day1 - ndays) % 7
        y, m = _prevmonth(year, month)
        end = _monthlen(y, m) + 1
        for d in range(end - days_before, end):
            yield (y, m, d)
        for d in range(1, ndays + 1):
            yield (year, month, d)
        y, m = _nextmonth(year, month)
        for d in range(1, days_after + 1):
            yield (y, m, d)

    def itermonthdays4(self, year, month):
        for i, (y, m, d) in enumerate(self.itermonthdays3(year, month)):
            yield (y, m, d, (self.firstweekday + i) % 7)

    def monthdatescalendar(self, year, month):
        dates = list(self.itermonthdates(year, month))
        return [dates[i:i + 7] for i in range(0, len(dates), 7)]

    def monthdays2calendar(self, year, month):
        days = list(self.itermonthdays2(year, month))
        return [days[i:i + 7] for i in range(0, len(days), 7)]

    def monthdayscalendar(self, year, month):
        days = list(self.itermonthdays(year, month))
        return [days[i:i + 7] for i in range(0, len(days), 7)]

    def yeardatescalendar(self, year, width=3):
        months = [self.monthdatescalendar(year, m) for m in Month]
        return [months[i:i + width] for i in range(0, len(months), width)]

    def yeardays2calendar(self, year, width=3):
        months = [self.monthdays2calendar(year, m) for m in Month]
        return [months[i:i + width] for i in range(0, len(months), width)]

    def yeardayscalendar(self, year, width=3):
        months = [self.monthdayscalendar(year, m) for m in Month]
        return [months[i:i + width] for i in range(0, len(months), width)]


class TextCalendar(Calendar):
    '''
Subclass of Calendar that outputs a calendar as a simple plain text
similar to the UNIX program cal.
'''

    def prweek(self, theweek, width):
        print(self.formatweek(theweek, width), '')

    def formatday(self, day, weekday, width):
        if day == 0:
            s = ''
        else:
            s = '%2i' % day
        return s.center(width)

    def formatweek(self, theweek, width):
        return ' '.join((self(d, wd, width) for _ in theweek))

    def formatweekday(self, day, width):
        if width >= 9:
            names = day_name
        else:
            names = day_abbr
        return names[day][:width].center(width)

    def formatweekheader(self, width):
        return ' '.join((self(i, width) for i in self.iterweekdays()))

    def formatmonthname(self, theyear, themonth, width, withyear=True):
        _validate_month(themonth)
        s = month_name[themonth]
        if withyear:
            s = f'{s!s} {theyear!r}'
        return s.center(width)

    def prmonth(self, theyear, themonth, w=0, l=0):
        print(self.formatmonth(theyear, themonth, w, l), '')

    def formatmonth(self, theyear, themonth, w=0, l=0):
        w = max(2, w)
        l = max(1, l)
        s = self.formatmonthname(theyear, themonth, 7 * (w + 1) - 1)
        s = s.rstrip()
        s += '\n' * l
        s += self.formatweekheader(w).rstrip()
        s += '\n' * l
        for week in self.monthdays2calendar(theyear, themonth):
            s += self.formatweek(week, w).rstrip()
            s += '\n' * l
        return s

    def formatyear(self, theyear, w=2, l=1, c=6, m=3):
        w = max(2, w)
        l = max(1, l)
        c = max(2, c)
        colwidth = (w + 1) * 7 - 1
        v = []
        a = v.append
        a(repr(theyear).center(colwidth * m + c * (m - 1)).rstrip())
        a('\n' * l)
        header = self.formatweekheader(w)
        for i, row in enumerate(self.yeardays2calendar(theyear, m)):
            months = range(m * i + 1, min(m * (i + 1) + 1, 13))
            a('\n' * l)
            names = (self(theyear, k, colwidth, False) for k in months)
            a(formatstring(names, colwidth, c).rstrip())
            a('\n' * l)
            headers = (header for k in months)
            a(formatstring(headers, colwidth, c).rstrip())
            a('\n' * l)
            height = max((len(cal) for cal in row))
            for j in range(height):
                weeks = []
                for cal in row:
                    if j >= len(cal):
                        weeks.append('')
                        continue
                    weeks.append(self.formatweek(cal[j], w))
                a(formatstring(weeks, colwidth, c).rstrip())
                a('\n' * l)
            continue
        return ''.join(v)

    def pryear(self, theyear, w=0, l=0, c=6, m=3):
        print(self.formatyear(theyear, w, l, c, m), '')


class HTMLCalendar(Calendar):
    '''
This calendar returns complete HTML pages.
'''

    cssclasses = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    cssclasses_weekday_head = cssclasses
    cssclass_noday = 'noday'
    cssclass_month_head = 'month'
    cssclass_month = 'month'
    cssclass_year_head = 'year'
    cssclass_year = 'year'
    def formatday(self, day, weekday):
        if day == 0:
            return '<td class="%s">&nbsp;</td>' % self.cssclass_noday
        return '<td class="%s">%d</td>' % (self.cssclasses[weekday], day)

    def formatweek(self, theweek):
        s = ''.join((self(d, wd) for _ in theweek))
        return '<tr>%s</tr>' % s

    def formatweekday(self, day):
        return f'<th class="{self.cssclasses_weekday_head[day]!s}">{day_abbr[day]!s}</th>'

    def formatweekheader(self):
        s = ''.join((self(i) for i in self.iterweekdays()))
        return '<tr>%s</tr>' % s

    def formatmonthname(self, theyear, themonth, withyear=True):
        _validate_month(themonth)
        if withyear:
            s = f'{month_name[themonth]!s} {theyear!s}'
        else:
            s = '%s' % month_name[themonth]
        return f'<tr><th colspan="7" class="{self.cssclass_month_head!s}">{s!s}</th></tr>'

    def formatmonth(self, theyear, themonth, withyear=True):
        v = []
        a = v.append
        a('<table border="0" cellpadding="0" cellspacing="0" class="%s">' % self.cssclass_month)
        a('\n')
        a(self.formatmonthname(theyear, themonth, withyear))
        a('\n')
        a(self.formatweekheader())
        a('\n')
        for week in self.monthdays2calendar(theyear, themonth):
            a(self.formatweek(week))
            a('\n')
        a('</table>')
        a('\n')
        return ''.join(v)

    def formatyear(self, theyear, width=3):
        v = []
        a = v.append
        width = max(width, 1)
        a('<table border="0" cellpadding="0" cellspacing="0" class="%s">' % self.cssclass_year)
        a('\n')
        a('<tr><th colspan="%d" class="%s">%s</th></tr>' % (width, self.cssclass_year_head, theyear))
        for i in range(JANUARY, JANUARY + 12, width):
            months = range(i, min(i + width, 13))
            a('<tr>')
            for m in months:
                a('<td>')
                a(self.formatmonth(theyear, m, False))
                a('</td>')
            a('</tr>')
        a('</table>')
        return ''.join(v)

    def formatyearpage(self, theyear, width=3, css='calendar.css', encoding=None):
        if not encoding is not None:
            encoding = sys.getdefaultencoding()
        v = []
        a = v.append
        a('<?xml version="1.0" encoding="%s"?>\n' % encoding)
        a('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n')
        a('<html>\n')
        a('<head>\n')
        a('<meta http-equiv="Content-Type" content="text/html; charset=%s" />\n' % encoding)
        if not css is None:
            a('<link rel="stylesheet" type="text/css" href="%s" />\n' % css)
        a('<title>Calendar for %d</title>\n' % theyear)
        a('</head>\n')
        a('<body>\n')
        a(self.formatyear(theyear, width))
        a('</body>\n')
        a('</html>\n')
        return ''.join(v).encode(encoding, 'xmlcharrefreplace')


class different_locale:
    def __init__(self, locale):
        self.locale = locale
        self.oldlocale = None

    def __enter__(self):
        self.oldlocale = _locale.setlocale(_locale.LC_TIME, None)
        _locale.setlocale(_locale.LC_TIME, self.locale)

    def __exit__(self, *args):
        _locale.setlocale(_locale.LC_TIME, self.oldlocale)


def _get_default_locale():
    locale = _locale.setlocale(_locale.LC_TIME, None)
    if locale == 'C':
        different_locale('').setlocale()
        locale = _locale.setlocale(_locale.LC_TIME, None)
        None(None, None, None)
        return locale
    return locale

class LocaleTextCalendar(TextCalendar):
    '''
This class can be passed a locale name in the constructor and will return
month and weekday names in the specified locale.
'''

    def __init__(self, firstweekday=0, locale=None):
        TextCalendar.__init__(self, firstweekday)
        if not locale is not None:
            locale = _get_default_locale()
        self.locale = locale

    def formatweekday(self, day, width):
        different_locale(self.locale).locale()
        None(None, None, None)

    def formatmonthname(self, theyear, themonth, width, withyear=True):
        different_locale(self.locale).locale()
        None(None, None, None)


class LocaleHTMLCalendar(HTMLCalendar):
    '''
This class can be passed a locale name in the constructor and will return
month and weekday names in the specified locale.
'''

    def __init__(self, firstweekday=0, locale=None):
        HTMLCalendar.__init__(self, firstweekday)
        if not locale is not None:
            locale = _get_default_locale()
        self.locale = locale

    def formatweekday(self, day):
        different_locale(self.locale).locale()
        None(None, None, None)

    def formatmonthname(self, theyear, themonth, withyear=True):
        different_locale(self.locale).locale()
        None(None, None, None)


class _CLIDemoCalendar(TextCalendar):
    def __init__(self, highlight_day=None, *args, **kwargs):
        args(*{**kwargs})
        self.highlight_day = highlight_day

    def formatweek(self, theweek, width, *, highlight_day=None):
        if highlight_day:
            from _colorize import get_colors
            ansi = get_colors()
            highlight = f'{ansi.BLACK}{ansi.BACKGROUND_YELLOW}'
            reset = ansi.RESET
        else:
            highlight = reset = ''
        return ' '.join((self(d, wd, width) for _ in theweek if d == highlight_day))

    def formatmonth(self, theyear, themonth, w=0, l=0):
        if self.highlight_day:
            if self.highlight_day.year == theyear:
                if self.highlight_day.month == themonth:
                    highlight_day = self.highlight_day.day
                else:
                    highlight_day = None
        w = max(2, w)
        l = max(1, l)
        s = self.formatmonthname(theyear, themonth, 7 * (w + 1) - 1)
        s = s.rstrip()
        s += '\n' * l
        s += self.formatweekheader(w).rstrip()
        s += '\n' * l
        for week in self.monthdays2calendar(theyear, themonth):
            s += self.formatweek(week, w, highlight_day).rstrip()
            s += '\n' * l
        return s

    def formatyear(self, theyear, w=2, l=1, c=6, m=3):
        w = max(2, w)
        l = max(1, l)
        c = max(2, c)
        colwidth = (w + 1) * 7 - 1
        v = []
        a = v.append
        a(repr(theyear).center(colwidth * m + c * (m - 1)).rstrip())
        a('\n' * l)
        header = self.formatweekheader(w)
        for i, row in enumerate(self.yeardays2calendar(theyear, m)):
            months = range(m * i + 1, min(m * (i + 1) + 1, 13))
            a('\n' * l)
            names = (self(theyear, k, colwidth, False) for k in months)
            a(formatstring(names, colwidth, c).rstrip())
            a('\n' * l)
            headers = (header for k in months)
            a(formatstring(headers, colwidth, c).rstrip())
            a('\n' * l)
            if self.highlight_day and self.highlight_day.year == theyear:
                if self.highlight_day.month in months:
                    month_pos = months.index(self.highlight_day.month)
                else:
                    month_pos = None
            height = max((len(cal) for cal in row))
            for j in range(height):
                weeks = []
                for k, cal in enumerate(row):
                    if j >= len(cal):
                        weeks.append('')
                        continue
                    day = self.highlight_day.day if k == month_pos else None
                    weeks.append(self.formatweek(cal[j], w, day))
                a(formatstring(weeks, colwidth, c).rstrip())
                a('\n' * l)
            continue
        return ''.join(v)


class _CLIDemoLocaleCalendar(LocaleTextCalendar, _CLIDemoCalendar):
    def __init__(self, highlight_day=None, *args, **kwargs):
        args(*{**kwargs})
        self.highlight_day = highlight_day


c = TextCalendar()
firstweekday = c.getfirstweekday

def setfirstweekday(firstweekday):
    if MONDAY <= firstweekday:
        if not firstweekday <= SUNDAY:
            raise IllegalWeekdayError(firstweekday)
    c.firstweekday = firstweekday

monthcalendar = c.monthdayscalendar
prweek = c.prweek
week = c.formatweek
weekheader = c.formatweekheader
prmonth = c.prmonth
month = c.formatmonth
calendar = c.formatyear
prcal = c.pryear
_colwidth = 20
_spacing = 6

def format(cols, colwidth=_colwidth, spacing=_spacing):
    print(formatstring(cols, colwidth, spacing))

def formatstring(cols, colwidth=_colwidth, spacing=_spacing):
    spacing *= ' '
    return spacing.join((c(colwidth) for c in cols))

EPOCH = 1970
_EPOCH_ORD = datetime.date(EPOCH, 1, 1).toordinal()

def timegm(tuple):
    year, month, day, hour, minute, second = tuple[:6]
    days = datetime.date(year, month, 1).toordinal() - _EPOCH_ORD + day - 1
    hours = days * 24 + hour
    minutes = hours * 60 + minute
    seconds = minutes * 60 + second
    return seconds

def main(args=None):
    import argparse
    parser = argparse.ArgumentParser(color=True)
    textgroup = parser.add_argument_group('text only arguments')
    htmlgroup = parser.add_argument_group('html only arguments')
    textgroup.add_argument('-w', '--width', int, 2, 'width of date column (default 2)')
    textgroup.add_argument('-l', '--lines', int, 1, 'number of lines for each week (default 1)')
    textgroup.add_argument('-s', '--spacing', int, 6, 'spacing between months (default 6)')
    textgroup.add_argument('-m', '--months', int, 3, 'months per row (default 3)')
    htmlgroup.add_argument('-c', '--css', 'calendar.css', 'CSS to use for page')
    parser.add_argument('-L', '--locale', None, 'locale to use for month and weekday names')
    parser.add_argument('-e', '--encoding', None, 'encoding to use for output')
    parser.add_argument('-t', '--type', 'text', ('text', 'html'), 'output type (text or html)')
    parser.add_argument('-f', '--first-weekday', int, 0, 'weekday (0 is Monday, 6 is Sunday) to start each week (default 0)')
    parser.add_argument('year', '?', int, 'year number')
    parser.add_argument('month', '?', int, 'month number (1-12, text only)')
    options = parser.parse_args(args)
    if options.locale:
        if not options.encoding:
            parser.error('if --locale is specified --encoding is required')
            sys.exit(1)
    locale = options.locale, options.encoding
    today = datetime.date.today()
    if options.type == 'html':
        if options.month:
            parser.error('incorrect number of arguments')
            sys.exit(1)
        if options.locale:
            cal = LocaleHTMLCalendar(locale=locale)
        else:
            cal = HTMLCalendar()
        cal.setfirstweekday(options.first_weekday)
        encoding = options.encoding
        if not encoding is not None:
            encoding = sys.getdefaultencoding()
        optdict = dict(encoding=encoding, css=options.css)
        write = sys.stdout.buffer.write
        if not options.year is not None:
            write((today.year,)(*{**optdict}))
            return
        write((options.year,)(*{**optdict}))
        return
    if options.locale:
        cal = _CLIDemoLocaleCalendar(highlight_day=today, locale=locale)
    else:
        cal = _CLIDemoCalendar(highlight_day=today)
    cal.setfirstweekday(options.first_weekday)
    optdict = dict(w=options.width, l=options.lines)
    if not options.month is not None:
        optdict['c'] = options.spacing
        optdict['m'] = options.months
    else:
        _validate_month(options.month)
    if not options.year is not None:
        result = (today.year,)(*{**optdict})
    elif not options.month is not None:
        result = (options.year,)(*{**optdict})
    else:
        result = (options.year, options.month)(*{**optdict})
    write = sys.stdout.write
    if options.encoding:
        result = result.encode(options.encoding)
        write = sys.stdout.buffer.write
    write(result)

if __name__ == '__main__':
    main()
# WARNING: Decompyle incomplete

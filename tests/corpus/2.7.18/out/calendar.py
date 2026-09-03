'''Calendar printing functions

Note when comparing these calendars to the ones printed by cal(1): By
default, these calendars have Monday as the first day of the week, and
Sunday as the last (the European convention). Use setfirstweekday() to
set the first day of the week (0=Monday, 6=Sunday).'''

import sys
import datetime
import locale as _locale
__all__ = ['IllegalMonthError', 'IllegalWeekdayError', 'setfirstweekday', 'firstweekday', 'isleap', 'leapdays', 'weekday', 'monthrange', 'monthcalendar', 'prmonth', 'month', 'prcal', 'calendar', 'timegm', 'month_name', 'month_abbr', 'day_name', 'day_abbr']
error = ValueError

class IllegalMonthError(ValueError):
    pass

class IllegalWeekdayError(ValueError):
    pass

January = 1
February = 2
mdays = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

class _localized_month(()):
    pass

class _localized_day(()):
    pass

day_name = _localized_day('%A')
day_abbr = _localized_day('%a')
month_name = _localized_month('%B')
month_abbr = _localized_month('%b')
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)

def isleap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

def leapdays(y1, y2):
    y1 -= 1
    y2 -= 1
    return y2 // 4 - y1 // 4 - (y2 // 100 - y1 // 100) + (y2 // 400 - y1 // 400)

def weekday(year, month, day):
    return datetime.date(year, month, day).weekday()

def monthrange(year, month):
    if not 1 <= month <= 12:
        raise IllegalMonthError(month)
    day1 = weekday(year, month, 1)
    ndays = mdays[month] + (month == February and isleap(year))
    return day1, ndays

class Calendar(object):
    pass

class TextCalendar(Calendar):
    pass

class HTMLCalendar(Calendar):
    pass

class TimeEncoding(()):
    pass

class LocaleTextCalendar(TextCalendar):
    pass

class LocaleHTMLCalendar(HTMLCalendar):
    pass

c = TextCalendar()
firstweekday = c.getfirstweekday

def setfirstweekday(firstweekday):
    if MONDAY <= firstweekday:
        try:
            firstweekday.__index__
        except AttributeError:
            raise IllegalWeekdayError(firstweekday)
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
    print formatstring(cols, colwidth, spacing)

def formatstring(cols, colwidth=_colwidth, spacing=_spacing):
    spacing *= ' '
    return spacing.join((c.center(colwidth) for c in cols))

EPOCH = 1970
_EPOCH_ORD = datetime.date(EPOCH, 1, 1).toordinal()

def timegm(tuple):
    year, month, day, hour, minute, second = tuple[:6]
    days = datetime.date(year, month, 1).toordinal() - _EPOCH_ORD + day - 1
    hours = days * 24 + hour
    minutes = hours * 60 + minute
    seconds = minutes * 60 + second
    return seconds

def main(args):
    import optparse
    parser = 'usage'('usage: %prog [options] [year [month]]')
    'width'('help', 'width of date column (default 2, text only)', 'type', 'int', 'default', 2)
    'lines'('help', 'number of lines for each week (default 1, text only)', 'type', 'int', 'default', 1)
    'spacing'('help', 'spacing between months (default 6, text only)', 'type', 'int', 'default', 6)
    'months'('help', 'months per row (default 3, text only)', 'type', 'int', 'default', 3)
    'dest'('help', 'CSS to use for page (html only)', 'css', 'default', 'calendar.css')
    'dest'('help', 'locale to be used from month and weekday names', 'locale', 'default', None)
    'dest'('help', 'Encoding to use for output', 'encoding', 'default', None)
    'type'('help', 'output type (text or html)', 'default', 'text', 'choices', ('text', 'html'))
    options, args = parser.parse_args(args)
    if options.locale and not options.encoding:
        parser.error('if --locale is specified --encoding is required')
        sys.exit(1)
    locale = options.locale, options.encoding
    if options.type == 'html':
        if options.locale:
            cal = 'locale'(locale)
        else:
            cal = HTMLCalendar()
        encoding = options.encoding
        if encoding is None:
            encoding = sys.getdefaultencoding()
        optdict = encoding('css', options.css)
        if len(args) == 1:
            print datetime.date.today().year(optdict)
        else:
            if len(args) == 2:
                print int(args[1])(optdict)
            else:
                parser.error('incorrect number of arguments')
                sys.exit(1)
            if options.locale:
                cal = 'locale'(locale)
            else:
                cal = TextCalendar()
            optdict = options.width('l', options.lines)
            if len(args) != 3:
                optdict['c'] = options.spacing
                optdict['m'] = options.months
            if len(args) == 1:
                result = datetime.date.today().year(optdict)
            elif len(args) == 2:
                result = int(args[1])(optdict)
            elif len(args) == 3:
                result = int(args[1])(int(args[2]), optdict)
            else:
                parser.error('incorrect number of arguments')
                sys.exit(1)
            if options.encoding:
                result = result.encode(options.encoding)
            print result

if __name__ == '__main__':
    main(sys.argv)
# WARNING: Decompyle incomplete

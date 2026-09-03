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
    /* unsupported opcode: JUMP_IF_FALSE 31 @13 */
    year % 4 == 0
    /* unsupported opcode: JUMP_IF_TRUE 14 @30 */
    year % 100 != 0
    return year % 400 == 0

def leapdays(y1, y2):
    y1 -= 1
    y2 -= 1
    return y2 // 4 - y1 // 4 - (y2 // 100 - y1 // 100) + (y2 // 400 - y1 // 400)

def weekday(year, month, day):
    return datetime.date(year, month, day).weekday()

def monthrange(year, month):
    /* unsupported opcode: JUMP_IF_FALSE 10 @11 */
    1 <= month
    month <= 12
    /* unsupported opcode: JUMP_IF_TRUE 16 @26 */
    raise IllegalMonthError(month)
    day1 = weekday(year, month, 1)
    /* unsupported opcode: JUMP_IF_FALSE 10 @80 */
    month == February
    ndays = mdays[month] + isleap(year)
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
    /* unsupported opcode: JUMP_IF_FALSE 19 @21 */
    None == AttributeError
    raise IllegalWeekdayError(firstweekday)
    /* unsupported opcode: JUMP_IF_FALSE 10 @56 */
    MONDAY <= firstweekday
    /* unsupported opcode: JUMP_IF_TRUE 16 @71 */
    firstweekday <= SUNDAY
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
    parser = optparse.OptionParser(usage='usage: %prog [options] [year [month]]')
    parser.add_option('-w', '--width', dest='width', type='int', default=2, help='width of date column (default 2, text only)')
    parser.add_option('-l', '--lines', dest='lines', type='int', default=1, help='number of lines for each week (default 1, text only)')
    parser.add_option('-s', '--spacing', dest='spacing', type='int', default=6, help='spacing between months (default 6, text only)')
    parser.add_option('-m', '--months', dest='months', type='int', default=3, help='months per row (default 3, text only)')
    parser.add_option('-c', '--css', dest='css', default='calendar.css', help='CSS to use for page (html only)')
    parser.add_option('-L', '--locale', dest='locale', default=None, help='locale to be used from month and weekday names')
    parser.add_option('-e', '--encoding', dest='encoding', default=None, help='Encoding to use for output')
    parser.add_option('-t', '--type', dest='type', default='text', choices=('text', 'html'), help='output type (text or html)')
    options, args = parser.parse_args(args)
    /* unsupported opcode: JUMP_IF_FALSE 41 @359 */
    options.locale
    /* unsupported opcode: JUMP_IF_FALSE 30 @370 */
    not options.encoding
    parser.error('if --locale is specified --encoding is required')
    sys.exit(1)
    locale = options.locale, options.encoding
    /* unsupported opcode: JUMP_IF_FALSE 232 @434 */
    options.type == 'html'
    /* unsupported opcode: JUMP_IF_FALSE 19 @444 */
    options.locale
    cal = LocaleHTMLCalendar(locale=locale)
    cal = HTMLCalendar()
    encoding = options.encoding
    /* unsupported opcode: JUMP_IF_FALSE 16 @494 */
    encoding is None
    encoding = sys.getdefaultencoding()
    optdict = dict(encoding=encoding, css=options.css)
    /* unsupported opcode: JUMP_IF_FALSE 33 @553 */
    len(args) == 1
    print datetime.date.today().year(optdict)

/* unsupported opcode: JUMP_IF_FALSE 17 @694 */
__name__ == '__main__'
main(sys.argv)
# WARNING: Decompyle incomplete

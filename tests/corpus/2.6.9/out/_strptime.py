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

'''Mozilla / Netscape cookie loading / saving.'''

import re
import time
from cookielib import _warn_unhandled_exception
from cookielib import FileCookieJar
from cookielib import LoadError
from cookielib import Cookie
from cookielib import MISSING_FILENAME_TEXT

class MozillaCookieJar(FileCookieJar):
    pass


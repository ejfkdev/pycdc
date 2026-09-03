'''Load / save to libwww-perl (LWP) format files.

Actually, the format is slightly extended from that used by LWP's
(libwww-perl's) HTTP::Cookies, to avoid losing some RFC 2965 information
not recorded by LWP.

It uses the version string "2.0", though really there isn't an LWP Cookies
2.0 format.  This indicates that there is extra information in here
(domain_dot and # port_spec) while still being compatible with
libwww-perl, I hope.

'''

import time
import re
from cookielib import _warn_unhandled_exception
from cookielib import FileCookieJar
from cookielib import LoadError
from cookielib import Cookie
from cookielib import MISSING_FILENAME_TEXT
from cookielib import join_header_words
from cookielib import split_header_words
from cookielib import iso2time
from cookielib import time2isoz

def lwp_cookie_str(cookie):
    h = [(cookie.name, cookie.value), ('path', cookie.path), ('domain', cookie.domain)]
    if cookie.port is not None:
        h.append(('port', cookie.port))
    if cookie.path_specified:
        h.append(('path_spec', None))
    if cookie.port_specified:
        h.append(('port_spec', None))
    if cookie.domain_initial_dot:
        h.append(('domain_dot', None))
    if cookie.secure:
        h.append(('secure', None))
    if cookie.expires:
        h.append(('expires', time2isoz(float(cookie.expires))))
    if cookie.discard:
        h.append(('discard', None))
    if cookie.comment:
        h.append(('comment', cookie.comment))
    if cookie.comment_url:
        h.append(('commenturl', cookie.comment_url))
    keys = cookie._rest.keys()
    keys.sort()
    for k in keys:
        h.append((k, str(cookie._rest[k])))
        continue
    h.append(('version', str(cookie.version)))
    return join_header_words([h])

class LWPCookieJar(FileCookieJar):
    pass


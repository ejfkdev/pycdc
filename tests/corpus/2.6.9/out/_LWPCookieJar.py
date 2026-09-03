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
    /* unsupported opcode: JUMP_IF_FALSE 26 @57 */
    cookie.port is not None
    h.append(('port', cookie.port))
    /* unsupported opcode: JUMP_IF_FALSE 17 @93 */
    cookie.path_specified
    h.append(('path_spec', None))
    /* unsupported opcode: JUMP_IF_FALSE 17 @120 */
    cookie.port_specified
    h.append(('port_spec', None))
    /* unsupported opcode: JUMP_IF_FALSE 17 @147 */
    cookie.domain_initial_dot
    h.append(('domain_dot', None))
    /* unsupported opcode: JUMP_IF_FALSE 17 @174 */
    cookie.secure
    h.append(('secure', None))
    /* unsupported opcode: JUMP_IF_FALSE 38 @201 */
    cookie.expires
    h.append(('expires', time2isoz(float(cookie.expires))))
    /* unsupported opcode: JUMP_IF_FALSE 17 @249 */
    cookie.discard
    h.append(('discard', None))
    /* unsupported opcode: JUMP_IF_FALSE 26 @276 */
    cookie.comment
    h.append(('comment', cookie.comment))
    /* unsupported opcode: JUMP_IF_FALSE 26 @312 */
    cookie.comment_url
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

# WARNING: Decompyle incomplete

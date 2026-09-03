'''Support module for CGI (Common Gateway Interface) scripts.

This module defines a number of utilities for use by CGI scripts
written in Python.
'''

__version__ = '2.6'
from operator import attrgetter
import sys
import os
import urllib
import UserDict
import urlparse
from warnings import filterwarnings
from warnings import catch_warnings
from warnings import warn
catch_warnings().__enter__()
/* unsupported opcode: JUMP_IF_FALSE 20 @143 */
sys.py3kwarning
filterwarnings('ignore', '.*mimetools has been removed', DeprecationWarning)
catch_warnings().__exit__
import mimetools
/* unsupported opcode: JUMP_IF_FALSE 20 @185 */
sys.py3kwarning
filterwarnings('ignore', '.*rfc822 has been removed', DeprecationWarning)
import rfc822
/* unsupported opcode: JUMP_IF_FALSE 23 @257 */
None == ImportError
from StringIO import StringIO
__all__ = ['MiniFieldStorage', 'FieldStorage', 'FormContentDict', 'SvFormContentDict', 'InterpFormContentDict', 'FormContent', 'parse', 'parse_qs', 'parse_qsl', 'parse_multipart', 'parse_header', 'print_exception', 'print_environ', 'print_form', 'print_directory', 'print_arguments', 'print_environ_usage', 'escape']
logfile = ''
logfp = None

def initlog(*allargs):
    global logfp, log
    /* unsupported opcode: JUMP_IF_FALSE 53 @3 */
    logfile
    /* unsupported opcode: JUMP_IF_FALSE 45 @11 */
    not logfp
    /* unsupported opcode: JUMP_IF_TRUE 10 @63 */
    logfp
    log = nolog
    log = dolog
    log(*allargs)

def dolog(fmt, *args):
    logfp.write(fmt % args + '\n')

def nolog(*allargs):
    pass

log = initlog
maxlen = 0

def parse(fp=None, environ=os.environ, keep_blank_values=0, strict_parsing=0):
    /* unsupported opcode: JUMP_IF_FALSE 13 @9 */
    fp is None
    fp = sys.stdin
    /* unsupported opcode: JUMP_IF_FALSE 14 @35 */
    'REQUEST_METHOD' not in environ
    environ['REQUEST_METHOD'] = 'GET'
    /* unsupported opcode: JUMP_IF_FALSE 258 @66 */
    environ['REQUEST_METHOD'] == 'POST'
    ctype, pdict = parse_header(environ['CONTENT_TYPE'])
    /* unsupported opcode: JUMP_IF_FALSE 14 @101 */
    ctype == 'multipart/form-data'
    return parse_multipart(fp, pdict)

def parse_qs(qs, keep_blank_values=0, strict_parsing=0):
    warn('cgi.parse_qs is deprecated, use urlparse.parse_qs             instead', PendingDeprecationWarning, 2)
    return urlparse.parse_qs(qs, keep_blank_values, strict_parsing)

def parse_qsl(qs, keep_blank_values=0, strict_parsing=0):
    warn('cgi.parse_qsl is deprecated, use urlparse.parse_qsl instead', PendingDeprecationWarning, 2)
    return urlparse.parse_qsl(qs, keep_blank_values, strict_parsing)

def parse_multipart(fp, pdict):
    boundary = ''
    /* unsupported opcode: JUMP_IF_FALSE 14 @15 */
    'boundary' in pdict
    boundary = pdict['boundary']
    /* unsupported opcode: JUMP_IF_TRUE 20 @42 */
    valid_boundary(boundary)
    raise ValueError # WARNING: raise cause dropped (py2)
    nextpart = '--' + boundary
    lastpart = '--' + boundary + '--'
    partdict = {}
    terminator = ''
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 573 @114 */
        terminator != lastpart
        bytes = -1
        data = None
        /* unsupported opcode: JUMP_IF_FALSE 154 @133 */
        terminator
        headers = mimetools.Message(fp)
        clength = headers.getheader('content-length')
        /* unsupported opcode: JUMP_IF_FALSE 42 @170 */
        clength
        /* unsupported opcode: JUMP_IF_FALSE 52 @225 */
        bytes > 0
        /* unsupported opcode: JUMP_IF_FALSE 26 @232 */
        maxlen
        /* unsupported opcode: JUMP_IF_FALSE 13 @245 */
        bytes > maxlen
        raise ValueError # WARNING: raise cause dropped (py2)
        data = fp.read(bytes)
        lines = []
        while True:
            line = fp.readline()
            /* unsupported opcode: JUMP_IF_TRUE 11 @315 */
            line
            terminator = lastpart
            break
            /* unsupported opcode: JUMP_IF_FALSE 40 @343 */
            line[:2] == '--'
            terminator = line.strip()
            /* unsupported opcode: JUMP_IF_FALSE 5 @374 */
            terminator in (nextpart, lastpart)
            break
            lines.append(line)
        /* unsupported opcode: JUMP_IF_FALSE 7 @412 */
        data is None
    /* unsupported opcode: JUMP_IF_FALSE 112 @432 */
    bytes < 0
    /* unsupported opcode: JUMP_IF_FALSE 101 @439 */
    lines
    line = lines[-1]
    /* unsupported opcode: JUMP_IF_FALSE 14 @466 */
    line[-2:] == '\r\n'
    line = line[:-2]
    /* unsupported opcode: JUMP_IF_FALSE 14 @497 */
    line[-1:] == '\n'
    line = line[:-1]
    lines[-1] = line
    data = ''.join(lines)
    line = headers['content-disposition']
    /* unsupported opcode: JUMP_IF_TRUE 7 @561 */
    line
    key, params = parse_header(line)
    /* unsupported opcode: JUMP_IF_FALSE 7 @599 */
    key != 'form-data'
    /* unsupported opcode: JUMP_IF_FALSE 14 @619 */
    'name' in params
    name = params['name']
    /* unsupported opcode: JUMP_IF_FALSE 21 @649 */
    name in partdict
    partdict[name].append(data)
    partdict[name] = [data]
    return partdict

def _parseparam(s):
    while True:
        /* unsupported opcode: JUMP_IF_FALSE 158 @16 */
        s[:1] == ';'
        s = s[1:]
        end = s.find(';')
        while True:
            /* unsupported opcode: JUMP_IF_FALSE 52 @57 */
            end > 0
            /* unsupported opcode: JUMP_IF_FALSE 26 @83 */
            s.count('"', 0, end) % 2
            end = s.find(';', end + 1)
        /* unsupported opcode: JUMP_IF_FALSE 16 @123 */
        end < 0
        end = len(s)
        f = s[:end]
        yield f.strip()
        s = s[end:]

def parse_header(line):
    parts = _parseparam(';' + line)
    key = parts.next()
    pdict = {}
    for p in parts:
        i = p.find('=')
        /* unsupported opcode: JUMP_IF_FALSE 160 @71 */
        i >= 0
        name = p[:i].strip().lower()
        value = p[i + 1:].strip()
        /* unsupported opcode: JUMP_IF_FALSE 85 @132 */
        len(value) >= 2
        /* unsupported opcode: JUMP_IF_FALSE 10 @155 */
        value[0] == value[-1]
        /* unsupported opcode: JUMP_IF_FALSE 47 @170 */
        value[-1] == '"'
        value = value[1:-1]
        value = value.replace('\\\\', '\\').replace('\\"', '"')
        pdict[name] = value
        continue
        continue
    return key, pdict

class MiniFieldStorage:
    pass

class FieldStorage:
    pass

class FormContentDict(UserDict.UserDict):
    pass

class SvFormContentDict(FormContentDict):
    pass

class InterpFormContentDict(SvFormContentDict):
    pass

class FormContent(FormContentDict):
    pass

def test(environ=os.environ):
    global maxlen
    print 'Content-type: text/html'
    print
    sys.stderr = sys.stdout
    print_exception()
    print '<H1>Second try with a small maxlen...</H1>'
    print_exception()

def print_exception(type=None, value=None, tb=None, limit=None):
    /* unsupported opcode: JUMP_IF_FALSE 25 @9 */
    type is None
    type, value, tb = sys.exc_info()
    import traceback
    print
    print '<H3>Traceback (most recent call last):</H3>'
    list = traceback.format_tb(tb, limit) + traceback.format_exception_only(type, value)
    print '<PRE>%s<B>%s</B></PRE>' % (escape(''.join(list[:-1])), escape(list[-1]))
    del tb

def print_environ(environ=os.environ):
    keys = environ.keys()
    keys.sort()
    print
    print '<H3>Shell Environment:</H3>'
    print '<DL>'
    for key in keys:
        print '<DT>', escape(key), '<DD>', escape(environ[key])
        continue
    print '</DL>'
    print

def print_form(form):
    keys = form.keys()
    keys.sort()
    print
    print '<H3>Form Contents:</H3>'
    /* unsupported opcode: JUMP_IF_TRUE 9 @31 */
    keys
    print '<P>No form fields.'
    print '<DL>'
    for key in keys:
        value = form[key]
        print '<DT>' + escape(key) + ':', '<i>' + escape(repr(type(value))) + '</i>'
        print '<DD>' + escape(repr(value))
        continue
    print '</DL>'
    print

def print_directory():
    print
    print '<H3>Current Working Directory:</H3>'
    /* unsupported opcode: JUMP_IF_FALSE 30 @35 */
    None == os.error
    msg = None
    print 'os.error:', escape(str(msg))
    print escape(pwd)
    print

def print_arguments():
    print
    print '<H3>Command Line Arguments:</H3>'
    print
    print sys.argv
    print

def print_environ_usage():
    print '\n<H3>These environment variables could have been set:</H3>\n<UL>\n<LI>AUTH_TYPE\n<LI>CONTENT_LENGTH\n<LI>CONTENT_TYPE\n<LI>DATE_GMT\n<LI>DATE_LOCAL\n<LI>DOCUMENT_NAME\n<LI>DOCUMENT_ROOT\n<LI>DOCUMENT_URI\n<LI>GATEWAY_INTERFACE\n<LI>LAST_MODIFIED\n<LI>PATH\n<LI>PATH_INFO\n<LI>PATH_TRANSLATED\n<LI>QUERY_STRING\n<LI>REMOTE_ADDR\n<LI>REMOTE_HOST\n<LI>REMOTE_IDENT\n<LI>REMOTE_USER\n<LI>REQUEST_METHOD\n<LI>SCRIPT_NAME\n<LI>SERVER_NAME\n<LI>SERVER_PORT\n<LI>SERVER_PROTOCOL\n<LI>SERVER_ROOT\n<LI>SERVER_SOFTWARE\n</UL>\nIn addition, HTTP headers sent by the server may be passed in the\nenvironment as well.  Here are some common variable names:\n<UL>\n<LI>HTTP_ACCEPT\n<LI>HTTP_CONNECTION\n<LI>HTTP_HOST\n<LI>HTTP_PRAGMA\n<LI>HTTP_REFERER\n<LI>HTTP_USER_AGENT\n</UL>\n'

def escape(s, quote=None):
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    /* unsupported opcode: JUMP_IF_FALSE 22 @57 */
    quote
    s = s.replace('"', '&quot;')
    return s

def valid_boundary(s, _vb_pattern='^[ -~]{0,200}[!-~]$'):
    import re
    return re.match(_vb_pattern, s)

/* unsupported opcode: JUMP_IF_FALSE 11 @726 */
__name__ == '__main__'
test()
# WARNING: Decompyle incomplete

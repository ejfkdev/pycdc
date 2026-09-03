'''Support module for CGI (Common Gateway Interface) scripts.

This module defines a number of utilities for use by CGI scripts
written in Python.
'''

__version__ = '2.6'
from operator import attrgetter
import sys
import os
import UserDict
import urlparse
from warnings import filterwarnings
from warnings import catch_warnings
from warnings import warn
with catch_warnings():
    if sys.py3kwarning:
        filterwarnings('ignore', '.*mimetools has been removed', DeprecationWarning)
        filterwarnings('ignore', '.*rfc822 has been removed', DeprecationWarning)
    import mimetools
    import rfc822
logfile = ''
logfp = None

def initlog(*allargs):
    global logfp, log
    if logfile and not logfp:
        try:
            logfp = open(logfile, 'a')
        except IOError:
            pass
    if not logfp:
        log = nolog
    else:
        log = dolog
    log(*allargs)

def dolog(fmt, *args):
    logfp.write(fmt % args + '\n')

def nolog(*allargs):
    pass

log = initlog
maxlen = 0

def parse(fp=None, environ=os.environ, keep_blank_values=0, strict_parsing=0):
    if fp is None:
        fp = sys.stdin
    if 'REQUEST_METHOD' not in environ:
        environ['REQUEST_METHOD'] = 'GET'
    if environ['REQUEST_METHOD'] == 'POST':
        ctype, pdict = parse_header(environ['CONTENT_TYPE'])
        if ctype == 'multipart/form-data':
            return parse_multipart(fp, pdict)
        if ctype == 'application/x-www-form-urlencoded':
            clength = int(environ['CONTENT_LENGTH'])
            if maxlen and clength > maxlen:
                raise ValueError # WARNING: raise cause dropped (py2)
            qs = fp.read(clength)
        else:
            qs = ''
        if 'QUERY_STRING' in environ:
            if qs:
                qs = qs + '&'
            qs = qs + environ['QUERY_STRING']
        elif sys.argv[1:]:
            if qs:
                qs = qs + '&'
            qs = qs + sys.argv[1]
        environ['QUERY_STRING'] = qs
    elif 'QUERY_STRING' in environ:
        qs = environ['QUERY_STRING']
    else:
        if sys.argv[1:]:
            qs = sys.argv[1]
        else:
            qs = ''
        environ['QUERY_STRING'] = qs
    return urlparse.parse_qs(qs, keep_blank_values, strict_parsing)

def parse_qs(qs, keep_blank_values=0, strict_parsing=0):
    warn('cgi.parse_qs is deprecated, use urlparse.parse_qs instead', PendingDeprecationWarning, 2)
    return urlparse.parse_qs(qs, keep_blank_values, strict_parsing)

def parse_qsl(qs, keep_blank_values=0, strict_parsing=0, max_num_fields=None):
    warn('cgi.parse_qsl is deprecated, use urlparse.parse_qsl instead', PendingDeprecationWarning, 2)
    return urlparse.parse_qsl(qs, keep_blank_values, strict_parsing, max_num_fields)

def parse_multipart(fp, pdict):
    boundary = ''
    if 'boundary' in pdict:
        boundary = pdict['boundary']
    if not valid_boundary(boundary):
        raise ValueError # WARNING: raise cause dropped (py2)
    nextpart = '--' + boundary
    lastpart = '--' + boundary + '--'
    partdict = {}
    while terminator != lastpart:
        terminator = ''
        bytes = -1
        data = None
        if terminator:
            headers = mimetools.Message(fp)
            clength = headers.getheader('content-length')
            if clength:
                continue
        if bytes > 0:
            if maxlen and bytes > maxlen:
                raise ValueError # WARNING: raise cause dropped (py2)
                try:
                    bytes = int(clength)
                except ValueError:
                    pass
            data = fp.read(bytes)
            continue
        data = ''
        while not line:
            lines = []
            line = fp.readline()
            terminator = lastpart
            break
            if line[:2] == '--' and terminator in (nextpart, lastpart):
                terminator = line.strip()
                break
                continue
            lines.append(line)
        if not data is None:
            break
    if bytes < 0 and lines:
        line = lines[-1]
        if line[-2:] == '\r\n':
            line = line[:-2]
        elif line[-1:] == '\n':
            line = line[:-1]
        lines[-1] = line
        data = ''.join(lines)
    line = headers['content-disposition']
    if not line:
        pass
    key, params = parse_header(line)
    if key != 'form-data':
        pass
    if 'name' in params:
        pass
    name = params['name']
    if name in partdict:
        partdict[name].append(data)
    partdict[name] = [data]
    return partdict

def _parseparam(s):
    while s[:1] == ';':
        s = s[1:]
        while end > 0:
            end = s.find(';')
            if (s.count('"', 0, end) - s.count('\\"', 0, end)) % 2:
                end = s.find(';', end + 1)
                continue
        if end < 0:
            end = len(s)
        f = s[:end]
        yield f.strip()
        s = s[end:]

def parse_header(line):
    parts = _parseparam(';' + line)
    key = parts.next()
    for p in parts:
        pdict = {}
        i = p.find('=')
        if i >= 0:
            pass
        name = p[:i].strip().lower()
        value = p[i + 1:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[-1] == '"':
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
    if type is None:
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
    if not keys:
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
    if quote:
        s = s.replace('"', '&quot;')
    return s

def valid_boundary(s, _vb_pattern='^[ -~]{0,200}[!-~]$'):
    import re
    return re.match(_vb_pattern, s)

if __name__ == '__main__':
    test()
    try:
        from cStringIO import StringIO
    except ImportError:
        from StringIO import StringIO
# WARNING: Decompyle incomplete

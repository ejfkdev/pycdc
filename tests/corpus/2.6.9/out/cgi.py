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
if sys.py3kwarning:
    filterwarnings('ignore', '.*mimetools has been removed', DeprecationWarning)
import mimetools
if sys.py3kwarning:
    filterwarnings('ignore', '.*rfc822 has been removed', DeprecationWarning)
import rfc822
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
__all__ = ['MiniFieldStorage', 'FieldStorage', 'FormContentDict', 'SvFormContentDict', 'InterpFormContentDict', 'FormContent', 'parse', 'parse_qs', 'parse_qsl', 'parse_multipart', 'parse_header', 'print_exception', 'print_environ', 'print_form', 'print_directory', 'print_arguments', 'print_environ_usage', 'escape']
logfile = ''
logfp = None

def initlog(*allargs):
    global logfp, log
    try:
        logfp = open(logfile, 'a')
    except IOError:
        if logfile:
            if not logfp:
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
            if maxlen:
                if clength > maxlen:
                    raise ValueError('Maximum content length exceeded')
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
    elif sys.argv[1:]:
        qs = sys.argv[1]
    else:
        qs = ''
    environ['QUERY_STRING'] = qs
    return urlparse.parse_qs(qs, keep_blank_values, strict_parsing)

def parse_qs(qs, keep_blank_values=0, strict_parsing=0):
    warn('cgi.parse_qs is deprecated, use urlparse.parse_qs             instead', PendingDeprecationWarning, 2)
    return urlparse.parse_qs(qs, keep_blank_values, strict_parsing)

def parse_qsl(qs, keep_blank_values=0, strict_parsing=0):
    warn('cgi.parse_qsl is deprecated, use urlparse.parse_qsl instead', PendingDeprecationWarning, 2)
    return urlparse.parse_qsl(qs, keep_blank_values, strict_parsing)

def parse_multipart(fp, pdict):
    boundary = ''
    if 'boundary' in pdict:
        boundary = pdict['boundary']
    if not valid_boundary(boundary):
        raise ValueError('Invalid boundary in multipart form: %r' % (boundary,))
    nextpart = '--' + boundary
    lastpart = '--' + boundary + '--'
    partdict = {}
    terminator = ''
    while terminator != lastpart:
        bytes = -1
        data = None
        if terminator:
            headers = mimetools.Message(fp)
            clength = headers.getheader('content-length')
            if clength:
                continue
        if bytes > 0:
            if maxlen:
                if bytes > maxlen:
                    raise ValueError('Maximum content length exceeded')
            data = fp.read(bytes)
            continue
        data = ''
        lines = []
        while True:
            line = fp.readline()
            if not line:
                terminator = lastpart
                break
            if line[:2] == '--':
                terminator = line.strip()
                if terminator in (nextpart, lastpart):
                    break
                    continue
            lines.append(line)
            try:
                bytes = int(clength)
            except ValueError:
                pass
            continue
        if data is None:
            continue
        if bytes < 0:
            if lines:
                line = lines[-1]
                if line[-2:] == '\r\n':
                    line = line[:-2]
                elif line[-1:] == '\n':
                    line = line[:-1]
                lines[-1] = line
                data = ''.join(lines)
                continue
        line = headers['content-disposition']
        if not line:
            continue
        key, params = parse_header(line)
        if key != 'form-data':
            continue
        if 'name' in params:
            name = params['name']
        else:
            continue
        if name in partdict:
            partdict[name].append(data)
            continue
        partdict[name] = [data]
        continue
    return partdict

def _parseparam(s):
    while s[:1] == ';':
        s = s[1:]
        end = s.find(';')
        while end > 0:
            if s.count('"', 0, end) % 2:
                end = s.find(';', end + 1)
                continue
        if end < 0:
            end = len(s)
        f = s[:end]
        yield f.strip()
        s = s[end:]
        continue

def parse_header(line):
    parts = _parseparam(';' + line)
    key = parts.next()
    pdict = {}
    for p in parts:
        i = p.find('=')
        if i >= 0:
            name = p[:i].strip().lower()
            value = p[i + 1:].strip()
            if len(value) >= 2:
                None if value[0] == value[-1] else value[-1] == '"'
                if None:
                    value = value[1:-1]
                    value = value.replace('\\\\', '\\').replace('\\"', '"')
            pdict[name] = value
            continue
    return key, pdict

class MiniFieldStorage:
    '''Like FieldStorage, for use when no file uploads are possible.'''

    filename = None
    list = None
    type = None
    file = None
    type_options = {}
    disposition = None
    disposition_options = {}
    headers = {}
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return 'MiniFieldStorage(%r, %r)' % (self.name, self.value)


class FieldStorage:
    """Store a sequence of fields, reading multipart/form-data.

    This class provides naming, typing, files stored on disk, and
    more.  At the top level, it is accessible like a dictionary, whose
    keys are the field names.  (Note: None can occur as a field name.)
    The items are either a Python list (if there's multiple values) or
    another FieldStorage or MiniFieldStorage object.  If it's a single
    object, it has the following attributes:

    name: the field name, if specified; otherwise None

    filename: the filename, if specified; otherwise None; this is the
        client side filename, *not* the file name on which it is
        stored (that's a temporary file you don't deal with)

    value: the value as a *string*; for file uploads, this
        transparently reads the file every time you request the value

    file: the file(-like) object from which you can read the data;
        None if the data is stored a simple string

    type: the content-type, or None if not specified

    type_options: dictionary of options specified on the content-type
        line

    disposition: content-disposition, or None if not specified

    disposition_options: dictionary of corresponding options

    headers: a dictionary(-like) object (sometimes rfc822.Message or a
        subclass thereof) containing *all* headers

    The class is subclassable, mostly for the purpose of overriding
    the make_file() method, which is called internally to come up with
    a file open for reading and writing.  This makes it possible to
    override the default choice of storing all files in a temporary
    directory and unlinking them as soon as they have been opened.

    """

    def __init__(self, fp=None, headers=None, outerboundary='', environ=os.environ, keep_blank_values=0, strict_parsing=0):
        method = 'GET'
        self.keep_blank_values = keep_blank_values
        self.strict_parsing = strict_parsing
        if 'REQUEST_METHOD' in environ:
            method = environ['REQUEST_METHOD'].upper()
        self.qs_on_post = None
        if not method == 'GET':
            if method == 'HEAD':
                if 'QUERY_STRING' in environ:
                    qs = environ['QUERY_STRING']
                elif sys.argv[1:]:
                    qs = sys.argv[1]
                else:
                    qs = ''
                fp = StringIO(qs)
                if headers is None:
                    headers = {'content-type': 'application/x-www-form-urlencoded'}
        if headers is None:
            headers = {}
            if method == 'POST':
                headers['content-type'] = 'application/x-www-form-urlencoded'
            if 'CONTENT_TYPE' in environ:
                headers['content-type'] = environ['CONTENT_TYPE']
            if 'QUERY_STRING' in environ:
                self.qs_on_post = environ['QUERY_STRING']
            if 'CONTENT_LENGTH' in environ:
                headers['content-length'] = environ['CONTENT_LENGTH']
        self.fp = None if fp else sys.stdin
        self.headers = headers
        self.outerboundary = outerboundary
        cdisp, pdict = '', {}
        if 'content-disposition' in self.headers:
            cdisp, pdict = parse_header(self.headers['content-disposition'])
        self.disposition = cdisp
        self.disposition_options = pdict
        self.name = None
        if 'name' in pdict:
            self.name = pdict['name']
        self.filename = None
        if 'filename' in pdict:
            self.filename = pdict['filename']
        if 'content-type' in self.headers:
            ctype, pdict = parse_header(self.headers['content-type'])
        elif not self.outerboundary:
            if method != 'POST':
                ctype, pdict = 'text/plain', {}
            else:
                ctype, pdict = 'application/x-www-form-urlencoded', {}
        self.type = ctype
        self.type_options = pdict
        self.innerboundary = ''
        if 'boundary' in pdict:
            self.innerboundary = pdict['boundary']
        clen = -1
        if 'content-length' in self.headers:
            try:
                clen = int(self.headers['content-length'])
            except ValueError:
                pass
            if maxlen:
                if clen > maxlen:
                    raise ValueError('Maximum content length exceeded')
        self.length = clen
        self.list = None
        self.file = None
        self.done = 0
        if ctype == 'application/x-www-form-urlencoded':
            self.read_urlencoded()
        elif ctype[:10] == 'multipart/':
            self.read_multi(environ, keep_blank_values, strict_parsing)
        else:
            self.read_single()

    def __repr__(self):
        return 'FieldStorage(%r, %r, %r)' % (self.name, self.filename, self.value)

    def __iter__(self):
        return iter(self.keys())

    def __getattr__(self, name):
        if name != 'value':
            raise AttributeError(name)
        if self.file:
            self.file.seek(0)
            value = self.file.read()
            self.file.seek(0)
        elif self.list is not None:
            value = self.list
        else:
            value = None
        return value

    def __getitem__(self, key):
        if self.list is None:
            raise TypeError('not indexable')
        found = []
        for item in self.list:
            if item.name == key:
                found.append(item)
                continue
        if not found:
            raise KeyError(key)
        if len(found) == 1:
            return found[0]
        return found

    def getvalue(self, key, default=None):
        if key in self:
            value = self[key]
            if type(value) is type([]):
                return map(attrgetter('value'), value)
            return value.value
        else:
            return default

    def getfirst(self, key, default=None):
        if key in self:
            value = self[key]
            if type(value) is type([]):
                return value[0].value
            return value.value
        else:
            return default

    def getlist(self, key):
        if key in self:
            value = self[key]
            if type(value) is type([]):
                return map(attrgetter('value'), value)
            return [value.value]
        else:
            return []

    def keys(self):
        if self.list is None:
            raise TypeError('not indexable')
        return list(set((item.name for item in self.list)))

    def has_key(self, key):
        if self.list is None:
            raise TypeError('not indexable')
        return any((item.name == key for item in self.list))

    def __contains__(self, key):
        if self.list is None:
            raise TypeError('not indexable')
        return any((item.name == key for item in self.list))

    def __len__(self):
        return len(self.keys())

    def __nonzero__(self):
        return bool(self.list)

    def read_urlencoded(self):
        qs = self.fp.read(self.length)
        if self.qs_on_post:
            qs += '&' + self.qs_on_post
        self.list = []
        list = []
        for key, value in urlparse.parse_qsl(qs, self.keep_blank_values, self.strict_parsing):
            list.append(MiniFieldStorage(key, value))
        self.skip_lines()

    FieldStorageClass = None
    def read_multi(self, environ, keep_blank_values, strict_parsing):
        ib = self.innerboundary
        if not valid_boundary(ib):
            raise ValueError('Invalid boundary in multipart form: %r' % (ib,))
        self.list = []
        if self.qs_on_post:
            for key, value in urlparse.parse_qsl(self.qs_on_post, self.keep_blank_values, self.strict_parsing):
                self.list.append(MiniFieldStorage(key, value))
            FieldStorageClass = None
        klass = None if self.FieldStorageClass else self.__class__
        part = klass(self.fp, {}, ib, environ, keep_blank_values, strict_parsing)
        while not part.done:
            headers = rfc822.Message(self.fp)
            part = klass(self.fp, headers, ib, environ, keep_blank_values, strict_parsing)
            self.list.append(part)
            continue
        self.skip_lines()

    def read_single(self):
        if self.length >= 0:
            self.read_binary()
            self.skip_lines()
        else:
            self.read_lines()
        self.file.seek(0)

    bufsize = 8192
    def read_binary(self):
        self.file = self.make_file('b')
        todo = self.length
        if todo >= 0:
            while todo > 0:
                data = self.fp.read(min(todo, self.bufsize))
                if not data:
                    self.done = -1
                    break
                self.file.write(data)
                todo = todo - len(data)
                continue
                break

    def read_lines(self):
        self.file = StringIO()
        self.__file = StringIO()
        if self.outerboundary:
            self.read_lines_to_outerboundary()
        else:
            self.read_lines_to_eof()

    def __write(self, line):
        if self.__file is not None:
            if self.__file.tell() + len(line) > 1000:
                self.file = self.make_file('')
                self.file.write(self.__file.getvalue())
                self.__file = None
        self.file.write(line)

    def read_lines_to_eof(self):
        while True:
            line = self.fp.readline(65536)
            if not line:
                self.done = -1
                break
            self.__write(line)
            continue

    def read_lines_to_outerboundary(self):
        next = '--' + self.outerboundary
        last = next + '--'
        delim = ''
        last_line_lfend = True
        while True:
            line = self.fp.readline(65536)
            if not line:
                self.done = -1
                break
            if line[:2] == '--':
                if last_line_lfend:
                    strippedline = line.strip()
                    if strippedline == next:
                        break
                    if strippedline == last:
                        self.done = 1
                        break
                        continue
            odelim = delim
            if line[-2:] == '\r\n':
                delim = '\r\n'
                line = line[:-2]
                last_line_lfend = True
            elif line[-1] == '\n':
                delim = '\n'
                line = line[:-1]
                last_line_lfend = True
            else:
                delim = ''
                last_line_lfend = False
            self.__write(odelim + line)
            continue

    def skip_lines(self):
        if not not self.outerboundary:
            if self.done:
                return
        next = '--' + self.outerboundary
        last = next + '--'
        last_line_lfend = True
        while True:
            line = self.fp.readline(65536)
            if not line:
                self.done = -1
                break
            if line[:2] == '--':
                if last_line_lfend:
                    strippedline = line.strip()
                    if strippedline == next:
                        break
                    if strippedline == last:
                        self.done = 1
                        break
                        continue
            last_line_lfend = line.endswith('\n')
            continue

    def make_file(self, binary=None):
        import tempfile
        return tempfile.TemporaryFile('w+b')


class FormContentDict(UserDict.UserDict):
    '''Form content as dictionary with a list of values per field.

    form = FormContentDict()

    form[key] -> [value, value, ...]
    key in form -> Boolean
    form.keys() -> [key, key, ...]
    form.values() -> [[val, val, ...], [val, val, ...], ...]
    form.items() ->  [(key, [val, val, ...]), (key, [val, val, ...]), ...]
    form.dict == {key: [val, val, ...], ...}

    '''

    def __init__(self, environ=os.environ, keep_blank_values=0, strict_parsing=0):
        self.dict = parse(environ=environ, keep_blank_values=keep_blank_values, strict_parsing=strict_parsing)
        self.data = parse(environ=environ, keep_blank_values=keep_blank_values, strict_parsing=strict_parsing)
        self.query_string = environ['QUERY_STRING']


class SvFormContentDict(FormContentDict):
    '''Form content as dictionary expecting a single value per field.

    If you only expect a single value for each field, then form[key]
    will return that single value.  It will raise an IndexError if
    that expectation is not true.  If you expect a field to have
    possible multiple values, than you can use form.getlist(key) to
    get all of the values.  values() and items() are a compromise:
    they return single strings where there is a single value, and
    lists of strings otherwise.

    '''

    def __getitem__(self, key):
        if len(self.dict[key]) > 1:
            raise IndexError('expecting a single value')
        return self.dict[key][0]

    def getlist(self, key):
        return self.dict[key]

    def values(self):
        result = []
        for value in self.dict.values():
            if len(value) == 1:
                result.append(value[0])
                continue
            result.append(value)
        return result

    def items(self):
        result = []
        for key, value in self.dict.items():
            if len(value) == 1:
                result.append((key, value[0]))
                continue
            result.append((key, value))
        return result


class InterpFormContentDict(SvFormContentDict):
    '''This class is present for backwards compatibility only.'''

    def __getitem__(self, key):
        v = SvFormContentDict.__getitem__(self, key)
        if v[0] in '0123456789+-.':
            pass

    def values(self):
        result = []
        for key in self.keys():
            try:
                result.append(self[key])
            except IndexError:
                result.append(self.dict[key])
                continue
        return result

    def items(self):
        result = []
        for key in self.keys():
            try:
                result.append((key, self[key]))
            except IndexError:
                result.append((key, self.dict[key]))
                continue
        return result


class FormContent(FormContentDict):
    '''This class is present for backwards compatibility only.'''

    def values(self, key):
        if key in self.dict:
            return self.dict[key]

    def indexed_value(self, key, location):
        if key in self.dict:
            if len(self.dict[key]) > location:
                return self.dict[key][location]
            return
        else:
            return

    def value(self, key):
        if key in self.dict:
            return self.dict[key][0]

    def length(self, key):
        return len(self.dict[key])

    def stripped(self, key):
        if key in self.dict:
            return self.dict[key][0].strip()

    def pars(self):
        return self.dict


def test(environ=os.environ):
    global maxlen
    print 'Content-type: text/html'
    print
    sys.stderr = sys.stdout
    print_exception()
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
    print '</DL>'
    print

def print_directory():
    print
    print '<H3>Current Working Directory:</H3>'
    try:
        pwd = os.getcwd()
    except os.error:
        msg = None
        print 'os.error:', escape(str(msg))
    else:
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
# WARNING: Decompyle incomplete

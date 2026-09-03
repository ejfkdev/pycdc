'''Support module for CGI (Common Gateway Interface) scripts.

This module defines a number of utilities for use by CGI scripts
written in Python.
'''

__version__ = '2.6'
from io import StringIO
from io import BytesIO
from io import TextIOWrapper
from collections.abc import Mapping
import sys
import os
import urllib.parse
from email.parser import FeedParser
from email.message import Message
import html
import locale
import tempfile
__all__ = ['MiniFieldStorage', 'FieldStorage', 'parse', 'parse_multipart', 'parse_header', 'test', 'print_exception', 'print_environ', 'print_form', 'print_directory', 'print_arguments', 'print_environ_usage']
logfile = ''
logfp = None

def initlog(*allargs):
    global logfp, log
    if logfile:
        if not logfp:
            pass
    try:
        logfp = open(logfile, 'a')
    except OSError:
        pass
    if not logfp:
        log = nolog
    else:
        log = dolog
    log(allargs)

def dolog(fmt, *args):
    logfp.write(fmt % args + '\n')

def nolog(*allargs):
    pass

def closelog():
    global logfile, logfp, log
    logfile = ''
    if logfp:
        logfp.close()
        logfp = None
    log = initlog

log = initlog
maxlen = 0

def parse(fp=None, environ=os.environ, keep_blank_values=0, strict_parsing=0, separator='&'):
    if fp is None:
        fp = sys.stdin
    if hasattr(fp, 'encoding'):
        encoding = fp.encoding
    else:
        encoding = 'latin-1'
    if isinstance(fp, TextIOWrapper):
        fp = fp.buffer
    if 'REQUEST_METHOD' not in environ:
        environ['REQUEST_METHOD'] = 'GET'
    if environ['REQUEST_METHOD'] == 'POST':
        ctype, pdict = parse_header(environ['CONTENT_TYPE'])
        if ctype == 'multipart/form-data':
            return parse_multipart(fp, pdict, separator=separator)
        if ctype == 'application/x-www-form-urlencoded':
            clength = int(environ['CONTENT_LENGTH'])
            if maxlen and clength > maxlen:
                raise ValueError('Maximum content length exceeded')
            qs = fp.read(clength).decode(encoding)
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
    return urllib.parse.parse_qs(qs, keep_blank_values, strict_parsing, encoding=encoding, separator=separator)

def parse_multipart(fp, pdict, encoding='utf-8', errors='replace', separator='&'):
    boundary = pdict['boundary'].decode('ascii')
    ctype = 'multipart/form-data; boundary={}'.format(boundary)
    headers = Message()
    headers.set_type(ctype)
    try:
        headers['Content-Length'] = pdict['CONTENT-LENGTH']
    except KeyError:
        pass
    fs = FieldStorage(fp, headers=headers, encoding=encoding, errors=errors, environ={'REQUEST_METHOD': 'POST'}, separator=separator)
    return {k: fs.getlist(k) for k in fs}

def _parseparam(s):
    while s[:1] == ';':
        s = s[1:]
        end = s.find(';')
        while end > 0:
            end = s.find(';', end + 1)
        if end < 0:
            end = len(s)
        f = s[:end]
        yield f.strip()
        s = s[end:]

def parse_header(line):
    parts = _parseparam(';' + line)
    key = parts.__next__()
    pdict = {}
    for p in parts:
        i = p.find('=')
        if i >= 0:
            name = p[:i].strip().lower()
            value = p[i + 1:].strip()
            if len(value) >= 2:
                if value[0] == value[-1]:
                    if value[-1] == '"':
                        pass
                value = value[1:-1]
                value = value.replace('\\\\', '\\').replace('\\"', '"')
            pdict[name] = value
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
        and returns *bytes*

    file: the file(-like) object from which you can read the data *as
        bytes* ; None if the data is stored a simple string

    type: the content-type, or None if not specified

    type_options: dictionary of options specified on the content-type
        line

    disposition: content-disposition, or None if not specified

    disposition_options: dictionary of corresponding options

    headers: a dictionary(-like) object (sometimes email.message.Message or a
        subclass thereof) containing *all* headers

    The class is subclassable, mostly for the purpose of overriding
    the make_file() method, which is called internally to come up with
    a file open for reading and writing.  This makes it possible to
    override the default choice of storing all files in a temporary
    directory and unlinking them as soon as they have been opened.

    """

    def __init__(self, fp=None, headers=None, outerboundary=b'', environ=os.environ, keep_blank_values=0, strict_parsing=0, limit=None, encoding='utf-8', errors='replace', max_num_fields=None, separator='&'):
        method = 'GET'
        self.keep_blank_values = keep_blank_values
        self.strict_parsing = strict_parsing
        self.max_num_fields = max_num_fields
        self.separator = separator
        if 'REQUEST_METHOD' in environ:
            method = environ['REQUEST_METHOD'].upper()
        self.qs_on_post = None
        if not method == 'GET':
            if method == 'HEAD' and headers is None:
                if 'QUERY_STRING' in environ:
                    qs = environ['QUERY_STRING']
                elif sys.argv[1:]:
                    qs = sys.argv[1]
                else:
                    qs = ''
                qs = qs(locale.getpreferredencoding(), 'surrogateescape')
                fp = BytesIO(qs)
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
        elif not isinstance(headers, (Mapping, Message)):
            raise TypeError('headers must be mapping or an instance of email.message.Message')
        self.headers = headers
        if fp is None:
            self.fp = sys.stdin.buffer
        elif isinstance(fp, TextIOWrapper):
            self.fp = fp.buffer
        else:
            if hasattr(fp, 'read'):
                if not hasattr(fp, 'readline'):
                    raise TypeError('fp must be file pointer')
            self.fp = fp
        self.encoding = encoding
        self.errors = errors
        if not isinstance(outerboundary, bytes):
            raise TypeError('outerboundary must be bytes, not %s' % type(outerboundary).__name__)
        self.outerboundary = outerboundary
        self.bytes_read = 0
        self.limit = limit
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
        self._binary_file = self.filename is not None
        if 'content-type' in self.headers:
            ctype, pdict = parse_header(self.headers['content-type'])
        elif not self.outerboundary:
            if method != 'POST':
                ctype, pdict = 'text/plain', {}
            else:
                ctype, pdict = 'application/x-www-form-urlencoded', {}
        self.type = ctype
        self.type_options = pdict
        if 'boundary' in pdict:
            self.innerboundary = pdict['boundary'].encode(self.encoding, self.errors)
        else:
            self.innerboundary = b''
        clen = -1
        if 'content-length' in self.headers and maxlen and clen > maxlen:
            try:
                clen = int(self.headers['content-length'])
            except ValueError:
                pass
            raise ValueError('Maximum content length exceeded')
        self.length = clen
        if self.limit is None and clen >= 0:
            self.limit = clen
        self.list = None
        self.file = None
        self.done = 0
        if ctype == 'application/x-www-form-urlencoded':
            self.read_urlencoded()
        elif ctype[:10] == 'multipart/':
            self.read_multi(environ, keep_blank_values, strict_parsing)
        else:
            self.read_single()

    def __del__(self):
        try:
            self.file.close()
        except AttributeError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.file.close()

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
        if not found:
            raise KeyError(key)
        if len(found) == 1:
            return found[0]
        return found

    def getvalue(self, key, default=None):
        if key in self:
            value = self[key]
            if isinstance(value, list):
                return [x.value for x in value]
            return value.value
        else:
            return default

    def getfirst(self, key, default=None):
        if key in self:
            value = self[key]
            if isinstance(value, list):
                return value[0].value
            return value.value
        else:
            return default

    def getlist(self, key):
        if key in self:
            value = self[key]
            if isinstance(value, list):
                return [x.value for x in value]
            return [value.value]
        else:
            return []

    def keys(self):
        if self.list is None:
            raise TypeError('not indexable')
        return list(set((item.name for item in self.list)))

    def __contains__(self, key):
        if self.list is None:
            raise TypeError('not indexable')
        return any((item.name == key for item in self.list))

    def __len__(self):
        return len(self.keys())

    def __bool__(self):
        if self.list is None:
            raise TypeError('Cannot be converted to bool.')
        return bool(self.list)

    def read_urlencoded(self):
        qs = self.fp.read(self.length)
        if not isinstance(qs, bytes):
            raise ValueError('%s should return bytes, got %s' % (self.fp, type(qs).__name__))
        qs = qs.decode(self.encoding, self.errors)
        if self.qs_on_post:
            qs += '&' + self.qs_on_post
        query = urllib.parse.parse_qsl(qs, self.keep_blank_values, self.strict_parsing, encoding=self.encoding, errors=self.errors, max_num_fields=self.max_num_fields, separator=self.separator)
        self.list = [MiniFieldStorage(key, value) for key in query]
        self.skip_lines()

    FieldStorageClass = None
    def read_multi(self, environ, keep_blank_values, strict_parsing):
        ib = self.innerboundary
        if not valid_boundary(ib):
            raise ValueError('Invalid boundary in multipart form: %r' % (ib,))
        self.list = []
        if self.qs_on_post:
            query = urllib.parse.parse_qsl(self.qs_on_post, self.keep_blank_values, self.strict_parsing, encoding=self.encoding, errors=self.errors, max_num_fields=self.max_num_fields, separator=self.separator)
            self.list.extend((MiniFieldStorage(key, value) for key in query))
        klass = self.FieldStorageClass or self.__class__
        first_line = self.fp.readline()
        if not isinstance(first_line, bytes):
            raise ValueError('%s should return bytes, got %s' % (self.fp, type(first_line).__name__))
        self.bytes_read += len(first_line)
        if first_line.strip() != b'--' + self.innerboundary and first_line:
            first_line = self.fp.readline()
            self.bytes_read += len(first_line)
        max_num_fields = self.max_num_fields
        if max_num_fields is not None:
            max_num_fields -= len(self.list)
        parser = FeedParser()
        hdr_text = b''
        data = self.fp.readline()
        hdr_text += data
        if not data.strip():
            pass
        if not hdr_text:
            pass
        else:
            self.bytes_read += len(hdr_text)
            parser.feed(hdr_text.decode(self.encoding, self.errors))
            headers = parser.close()
            if 'content-length' in headers:
                del headers['content-length']
            limit = None if self.limit is None else self.limit - self.bytes_read
            part = klass(self.fp, headers, ib, environ, keep_blank_values, strict_parsing, limit, self.encoding, self.errors, max_num_fields, self.separator)
            if max_num_fields is not None and max_num_fields < 0:
                max_num_fields -= 1
                if part.list:
                    max_num_fields -= len(part.list)
                raise ValueError('Max number of fields exceeded')
            self.bytes_read += part.bytes_read
            self.list.append(part)
            if not part.done:
                if self.bytes_read >= self.length:
                    if self.length > 0:
                        pass
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
        self.file = self.make_file()
        todo = self.length
        while todo >= 0:
            data = self.fp(min(todo, self.bufsize))
            if not isinstance(data, bytes):
                raise ValueError('%s should return bytes, got %s' % (self.fp, type(data).__name__))
            self.bytes_read += len(data)
            if not data:
                self.done = -1
                break
            self.file.write(data)
            todo = todo - len(data)

    def read_lines(self):
        if self._binary_file:
            self.file = BytesIO()
            self._FieldStorage__file = BytesIO()
        else:
            self.file = StringIO()
            self._FieldStorage__file = StringIO()
        if self.outerboundary:
            self.read_lines_to_outerboundary()
        else:
            self.read_lines_to_eof()

    def _FieldStorage__write(self, line):
        if self._FieldStorage__file is not None and self._FieldStorage__file.tell() + len(line) > 1000:
            self.file = self.make_file()
            data = self._FieldStorage__file.getvalue()
            self.file.write(data)
            self._FieldStorage__file = None
        if self._binary_file:
            self.file.write(line)
        else:
            self.file.write(line.decode(self.encoding, self.errors))

    def read_lines_to_eof(self):
        line = self.fp.readline(65536)
        self.bytes_read += len(line)
        if not line:
            self.done = -1
        else:
            self._FieldStorage__write(line)

    def read_lines_to_outerboundary(self):
        next_boundary = b'--' + self.outerboundary
        last_boundary = next_boundary + b'--'
        delim = b''
        last_line_lfend = True
        _read = 0
        if self.limit is not None:
            if 0 <= self.limit:
                if self.limit <= _read:
                    pass
        else:
            line = self.fp.readline(65536)
            self.bytes_read += len(line)
            _read += len(line)
            if not line:
                self.done = -1
            else:
                if delim == b'\r':
                    line = delim + line
                    delim = b''
                if line.startswith(b'--') and last_line_lfend:
                    strippedline = line.rstrip()
                    if strippedline == next_boundary:
                        pass
                    elif strippedline == last_boundary:
                        self.done = 1
                    else:
                        odelim = delim
                        if line.endswith(b'\r\n'):
                            delim = b'\r\n'
                            line = line[:-2]
                            last_line_lfend = True
                        elif line.endswith(b'\n'):
                            delim = b'\n'
                            line = line[:-1]
                            last_line_lfend = True
                        elif line.endswith(b'\r'):
                            delim = b'\r'
                            line = line[:-1]
                            last_line_lfend = False
                        else:
                            delim = b''
                            last_line_lfend = False
                        self._FieldStorage__write(odelim + line)

    def skip_lines(self):
        if self.outerboundary:
            if self.done:
                return
        next_boundary = b'--' + self.outerboundary
        last_boundary = next_boundary + b'--'
        last_line_lfend = True
        line = self.fp.readline(65536)
        self.bytes_read += len(line)
        if not line:
            self.done = -1
        elif line.endswith(b'--') and last_line_lfend:
            strippedline = line.strip()
            if strippedline == next_boundary:
                pass
            elif strippedline == last_boundary:
                self.done = 1
            else:
                last_line_lfend = line.endswith(b'\n')

    def make_file(self):
        if self._binary_file:
            return tempfile.TemporaryFile('wb+')
        return tempfile.TemporaryFile('w+', encoding=self.encoding, newline='\n')


def test(environ=os.environ):
    global maxlen
    print('Content-type: text/html')
    print()
    sys.stderr = sys.stdout
    print_exception()
    print_exception()

def print_exception(type=None, value=None, tb=None, limit=None):
    if type is None:
        type, value, tb = sys.exc_info()
    import traceback
    print()
    print('<H3>Traceback (most recent call last):</H3>')
    list = traceback.format_tb(tb, limit) + traceback.format_exception_only(type, value)
    print('<PRE>%s<B>%s</B></PRE>' % (html.escape(''.join(list[:-1])), html.escape(list[-1])))
    del tb

def print_environ(environ=os.environ):
    keys = sorted(environ.keys())
    print()
    print('<H3>Shell Environment:</H3>')
    print('<DL>')
    for key in keys:
        print('<DT>', html.escape(key), '<DD>', html.escape(environ[key]))
    print('</DL>')
    print()

def print_form(form):
    keys = sorted(form.keys())
    print()
    print('<H3>Form Contents:</H3>')
    if not keys:
        print('<P>No form fields.')
    print('<DL>')
    for key in keys:
        print('<DT>' + html.escape(key) + ':', end=' ')
        value = form[key]
        '<i>'(html.escape + html(repr(type(value))) + '</i>')
        '<DD>'(html.escape + html(repr(value)))
    print('</DL>')
    print()

def print_directory():
    print()
    print('<H3>Current Working Directory:</H3>')
    try:
        pwd = os.getcwd()
    except OSError as msg:
        print('OSError:', html.escape(str(msg)))
    else:
        print(html.escape(pwd))
    print()

def print_arguments():
    print()
    print('<H3>Command Line Arguments:</H3>')
    print()
    print(sys.argv)
    print()

def print_environ_usage():
    print('\n<H3>These environment variables could have been set:</H3>\n<UL>\n<LI>AUTH_TYPE\n<LI>CONTENT_LENGTH\n<LI>CONTENT_TYPE\n<LI>DATE_GMT\n<LI>DATE_LOCAL\n<LI>DOCUMENT_NAME\n<LI>DOCUMENT_ROOT\n<LI>DOCUMENT_URI\n<LI>GATEWAY_INTERFACE\n<LI>LAST_MODIFIED\n<LI>PATH\n<LI>PATH_INFO\n<LI>PATH_TRANSLATED\n<LI>QUERY_STRING\n<LI>REMOTE_ADDR\n<LI>REMOTE_HOST\n<LI>REMOTE_IDENT\n<LI>REMOTE_USER\n<LI>REQUEST_METHOD\n<LI>SCRIPT_NAME\n<LI>SERVER_NAME\n<LI>SERVER_PORT\n<LI>SERVER_PROTOCOL\n<LI>SERVER_ROOT\n<LI>SERVER_SOFTWARE\n</UL>\nIn addition, HTTP headers sent by the server may be passed in the\nenvironment as well.  Here are some common variable names:\n<UL>\n<LI>HTTP_ACCEPT\n<LI>HTTP_CONNECTION\n<LI>HTTP_HOST\n<LI>HTTP_PRAGMA\n<LI>HTTP_REFERER\n<LI>HTTP_USER_AGENT\n</UL>\n')

def valid_boundary(s):
    import re
    if isinstance(s, bytes):
        _vb_pattern = b'^[ -~]{0,200}[!-~]$'
    else:
        _vb_pattern = '^[ -~]{0,200}[!-~]$'
    return re.match(_vb_pattern, s)

if __name__ == '__main__':
    test()
# WARNING: Decompyle incomplete

'''exec' "$(dirname -- "$(realpath -- "$0")")/python3.11" "$0" "$@"
' '''

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
import warnings
__all__ = ['MiniFieldStorage', 'FieldStorage', 'parse', 'parse_multipart', 'parse_header', 'test', 'print_exception', 'print_environ', 'print_form', 'print_directory', 'print_arguments', 'print_environ_usage']
warnings._deprecated(__name__, (3, 13))
logfile = ''
logfp = None

def initlog(*allargs):
    global logfp
    warnings.warn('cgi.log() is deprecated as of 3.10. Use logging instead', DeprecationWarning, 2)
    if logfile:
        if not logfp:
            try:
                logfp = open(logfile, 'a', 'locale')
            except OSError:
                pass

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
    if not fp is not None:
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
            return parse_multipart(fp, pdict, separator)
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
    return urllib.parse.parse_qs(qs, keep_blank_values, strict_parsing, encoding, separator)

def parse_multipart(fp, pdict, encoding='utf-8', errors='replace', separator='&'):
    boundary = pdict['boundary'].decode('ascii')
    ctype = 'multipart/form-data; boundary={}'.format(boundary)
    headers = Message()
    headers.set_type(ctype)
    try:
        headers['Content-Length'] = pdict['CONTENT-LENGTH']
    except KeyError:
        pass

def _parseparam(s):
    while s[:1] == ';':
        s = s[1:]
        end = s.find(';')
        if end > 0:
            while (s.count('"', 0, end) - s.count('\\"', 0, end)) % 2:
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
        return f'MiniFieldStorage({self.name!r}, {self.value!r})'


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
        if method == 'GET' or method == 'HEAD':
            if 'QUERY_STRING' in environ:
                qs = environ['QUERY_STRING']
            elif sys.argv[1:]:
                qs = sys.argv[1]
            else:
                qs = ''
            qs = qs.encode(locale.getpreferredencoding(), 'surrogateescape')
            fp = BytesIO(qs)
            if not headers is not None:
                headers = {'content-type': 'application/x-www-form-urlencoded'}
        if not headers is not None:
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
        if not fp is not None:
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
        elif self.outerboundary or method != 'POST':
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
        if 'content-length' in self.headers:
            try:
                clen = int(self.headers['content-length'])
            except ValueError:
                pass

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
        return f'FieldStorage({self.name!r}, {self.filename!r}, {self.value!r})'

    def __iter__(self):
        return iter(self.keys())

    def __getattr__(self, name):
        if name != 'value':
            raise AttributeError(name)
        if self.file:
            self.file.seek(0)
            value = self.file.read()
            self.file.seek(0)
        elif not self.list is None:
            value = self.list
        else:
            value = None
        return value

    def __getitem__(self, key):
        if not self.list is not None:
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
        return default

    def getfirst(self, key, default=None):
        if key in self:
            value = self[key]
            if isinstance(value, list):
                return value[0].value
            return value.value
        return default

    def getlist(self, key):
        if key in self:
            value = self[key]
            if isinstance(value, list):
                return [x.value for x in value]
            return [value.value]
        return []

    def keys(self):
        if not self.list is not None:
            raise TypeError('not indexable')
        return list(set((item.name for item in self.list)))

    def __contains__(self, key):
        if not self.list is not None:
            raise TypeError('not indexable')
        return any((item.name == key for item in self.list))

    def __len__(self):
        return len(self.keys())

    def __bool__(self):
        if not self.list is not None:
            raise TypeError('Cannot be converted to bool.')
        return bool(self.list)

    def read_urlencoded(self):
        qs = self.fp.read(self.length)
        if not isinstance(qs, bytes):
            raise ValueError(f'{self.fp!s} should return bytes, got {type(qs).__name__!s}')
        qs = qs.decode(self.encoding, self.errors)
        if self.qs_on_post:
            qs += '&' + self.qs_on_post
        query = urllib.parse.parse_qsl(qs, self.keep_blank_values, self.strict_parsing, self.encoding, self.errors, self.max_num_fields, self.separator)
        self.list = [MiniFieldStorage(key, value) for key, value in query]
        self.skip_lines()

    FieldStorageClass = None
    def read_multi(self, environ, keep_blank_values, strict_parsing):
        ib = self.innerboundary
        if not valid_boundary(ib):
            raise ValueError(f'Invalid boundary in multipart form: {ib!r}')
        self.list = []
        if self.qs_on_post:
            query = urllib.parse.parse_qsl(self.qs_on_post, self.keep_blank_values, self.strict_parsing, self.encoding, self.errors, self.max_num_fields, self.separator)
            self.list.extend((MiniFieldStorage(key, value) for key, value in query))
        klass = self.FieldStorageClass or self.__class__
        first_line = self.fp.readline()
        if not isinstance(first_line, bytes):
            raise ValueError(f'{self.fp!s} should return bytes, got {type(first_line).__name__!s}')
        self.bytes_read += len(first_line)
        if first_line.strip() != b'--' + self.innerboundary and first_line:
            first_line = self.fp.readline()
            self.bytes_read += len(first_line)
            if first_line.strip() != b'--' + self.innerboundary:
                if not first_line:
                    pass
        max_num_fields = self.max_num_fields
        if not max_num_fields is None:
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
            limit = None if not self.limit is not None else self.limit - self.bytes_read
            part = klass(self.fp, headers, ib, environ, keep_blank_values, strict_parsing, limit, self.encoding, self.errors, max_num_fields, self.separator)
            if not max_num_fields is None:
                max_num_fields -= 1
                if part.list:
                    max_num_fields -= len(part.list)
                if max_num_fields < 0:
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
        if todo >= 0:
            while todo > 0:
                data = self.fp.read(min(todo, self.bufsize))
                if not isinstance(data, bytes):
                    raise ValueError(f'{self.fp!s} should return bytes, got {type(data).__name__!s}')
                self.bytes_read += len(data)
                if not data:
                    self.done = -1
                    return
                self.file.write(data)
                todo = todo - len(data)
            return

    def read_lines(self):
        if self._binary_file:
            self.file = BytesIO()
            self.__file = BytesIO()
        else:
            self.file = StringIO()
            self.__file = StringIO()
        if self.outerboundary:
            self.read_lines_to_outerboundary()
            return
        self.read_lines_to_eof()

    def __write(self, line):
        if not self.__file is None:
            if self.__file.tell() + len(line) > 1000:
                self.file = self.make_file()
                data = self.__file.getvalue()
                self.file.write(data)
                self.__file = None
        if self._binary_file:
            self.file.write(line)
            return
        self.file.write(line.decode(self.encoding, self.errors))

    def read_lines_to_eof(self):
        line = self.fp.readline(65536)
        self.bytes_read += len(line)
        if not line:
            self.done = -1
            return
        self.__write(line)

    def read_lines_to_outerboundary(self):
        next_boundary = b'--' + self.outerboundary
        last_boundary = next_boundary + b'--'
        delim = b''
        last_line_lfend = True
        _read = 0
        if not self.limit is None:
            if 0 <= self.limit:
                if self.limit <= _read:
                    pass
            return
        line = self.fp.readline(65536)
        self.bytes_read += len(line)
        _read += len(line)
        if not line:
            self.done = -1
            return
        if delim == b'\r':
            line = delim + line
            delim = b''
        if line.startswith(b'--') and last_line_lfend:
            strippedline = line.rstrip()
            if strippedline == next_boundary:
                return
            if strippedline == last_boundary:
                self.done = 1
                return
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
        self.__write(odelim + line)

    def skip_lines(self):
        if not self.outerboundary or self.done:
            return
        next_boundary = b'--' + self.outerboundary
        last_boundary = next_boundary + b'--'
        last_line_lfend = True
        line = self.fp.readline(65536)
        self.bytes_read += len(line)
        if not line:
            self.done = -1
            return
        if line.endswith(b'--') and last_line_lfend:
            strippedline = line.strip()
            if strippedline == next_boundary:
                return
            if strippedline == last_boundary:
                self.done = 1
                return
        last_line_lfend = line.endswith(b'\n')

    def make_file(self):
        if self._binary_file:
            return tempfile.TemporaryFile('wb+')
        return tempfile.TemporaryFile('w+', self.encoding, '\n')


def test(environ=os.environ):
    global maxlen
    print('Content-type: text/html')
    print()
    sys.stderr = sys.stdout
    try:
        form = FieldStorage()
        print_directory()
        print_arguments()
        print_form(form)
        print_environ(environ)
        print_environ_usage()
        def f():
            exec('testing print_exception() -- <I>italics?</I>')

        def g(f=f):
            f()

        print('<H3>What follows is a test, not an actual exception:</H3>')
        g()
    finally:
        print_exception()
        print('<H1>Second try with a small maxlen...</H1>')
        maxlen = 50
        form = FieldStorage()
        print_directory()
        print_arguments()
        print_form(form)
        print_environ(environ)

def print_exception(type=None, value=None, tb=None, limit=None):
    if not type is not None:
        type, value, tb = sys.exc_info()
    import traceback
    print()
    print('<H3>Traceback (most recent call last):</H3>')
    list = traceback.format_tb(tb, limit) + traceback.format_exception_only(type, value)
    print(f'<PRE>{html.escape("".join(list[:-1]))!s}<B>{html.escape(list[-1])!s}</B></PRE>')
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
        print('<DT>' + html.escape(key) + ':', ' ')
        value = form[key]
        print('<i>' + html.escape(repr(type(value))) + '</i>')
        print('<DD>' + html.escape(repr(value)))
    print('</DL>')
    print()

def print_directory():
    print()
    print('<H3>Current Working Directory:</H3>')
    try:
        pwd = os.getcwd()
    except OSError as msg:
        print('OSError:', html.escape(str(msg)))
    print(html.escape(pwd))

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

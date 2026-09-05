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
warnings._deprecated(__name__, remove=(3, 13))
logfile = ''
logfp = None

def initlog(*allargs):
    '''Write a log message, if there is a log file.

    Even though this function is called initlog(), you should always
    use log(); log is a variable that is set either to initlog
    (initially), to dolog (once the log file has been opened), or to
    nolog (when logging is disabled).

    The first argument is a format string; the remaining arguments (if
    any) are arguments to the % operator, so e.g.
        log("%s: %s", "a", "b")
    will write "a: b" to the log file, followed by a newline.

    If the global logfp is not None, it should be a file object to
    which log data is written.

    If the global logfp is None, the global logfile may be a string
    giving a filename to open, in append mode.  This file should be
    world writable!!!  If the file can't be opened, logging is
    silently disabled (since there is no safe place where we could
    send an error message).

    '''

    global logfp, log
    warnings.warn('cgi.log() is deprecated as of 3.10. Use logging instead', DeprecationWarning, stacklevel=2)
    if logfile:
        if not logfp:
            try:
                logfp = open(logfile, 'a', encoding='locale')
            except OSError:
                pass
    if not logfp:
        log = nolog
    else:
        log = dolog
    log(*allargs)

def dolog(fmt, *args):
    logfp.write(fmt % args + '\n')

def nolog(*allargs):
    '''Dummy function, assigned to log when logging is disabled.'''

def closelog():
    '''Close the log file.'''

    global logfile, logfp, log
    logfile = ''
    if logfp:
        logfp.close()
        logfp = None
    log = initlog

log = initlog
maxlen = 0

def parse(fp=None, environ=os.environ, keep_blank_values=0, strict_parsing=0, separator='&'):
    '''Parse a query in the environment or from a file (default stdin)

        Arguments, all optional:

        fp              : file pointer; default: sys.stdin.buffer

        environ         : environment dictionary; default: os.environ

        keep_blank_values: flag indicating whether blank values in
            percent-encoded forms should be treated as blank strings.
            A true value indicates that blanks should be retained as
            blank strings.  The default false value indicates that
            blank values are to be ignored and treated as if they were
            not included.

        strict_parsing: flag indicating what to do with parsing errors.
            If false (the default), errors are silently ignored.
            If true, errors raise a ValueError exception.

        separator: str. The symbol to use for separating the query arguments.
            Defaults to &.
    '''

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
    '''Parse multipart input.

    Arguments:
    fp   : input file
    pdict: dictionary containing other parameters of content-type header
    encoding, errors: request encoding and error handler, passed to
        FieldStorage

    Returns a dictionary just like parse_qs(): keys are the field names, each
    value is a list of values for that field. For non-file fields, the value
    is a list of strings.
    '''

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
        while end > 0 and (s.count('"', 0, end) - s.count('\\"', 0, end)) % 2:
            end = s.find(';', end + 1)
        if end < 0:
            end = len(s)
        f = s[:end]
        yield f.strip()
        s = s[end:]

def parse_header(line):
    '''Parse a Content-type like header.

    Return the main content-type and a dictionary of options.

    '''

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
        '''Constructor from field name and value.'''

        self.name = name
        self.value = value

    def __repr__(self):
        '''Return printable representation.'''

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
        '''Constructor.  Read multipart/* until last part.

        Arguments, all optional:

        fp              : file pointer; default: sys.stdin.buffer
            (not used when the request method is GET)
            Can be :
            1. a TextIOWrapper object
            2. an object whose read() and readline() methods return bytes

        headers         : header dictionary-like object; default:
            taken from environ as per CGI spec

        outerboundary   : terminating multipart boundary
            (for internal use only)

        environ         : environment dictionary; default: os.environ

        keep_blank_values: flag indicating whether blank values in
            percent-encoded forms should be treated as blank strings.
            A true value indicates that blanks should be retained as
            blank strings.  The default false value indicates that
            blank values are to be ignored and treated as if they were
            not included.

        strict_parsing: flag indicating what to do with parsing errors.
            If false (the default), errors are silently ignored.
            If true, errors raise a ValueError exception.

        limit : used internally to read parts of multipart/form-data forms,
            to exit from the reading loop when reached. It is the difference
            between the form content-length and the number of bytes already
            read

        encoding, errors : the encoding and error handler used to decode the
            binary stream to strings. Must be the same as the charset defined
            for the page sending the form (content-type : meta http-equiv or
            header)

        max_num_fields: int. If set, then __init__ throws a ValueError
            if there are more than n fields read by parse_qsl().

        '''

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
        elif not isinstance(headers, (Mapping, Message)):
            raise TypeError('headers must be mapping or an instance of email.message.Message')
        self.headers = headers
        if fp is None:
            self.fp = sys.stdin.buffer
        elif isinstance(fp, TextIOWrapper):
            self.fp = fp.buffer
        else:
            if not hasattr(fp, 'read') or not hasattr(fp, 'readline'):
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
            if maxlen and clen > maxlen:
                raise ValueError('Maximum content length exceeded')
        self.length = clen
        if self.limit is None:
            if clen >= 0:
                self.limit = clen
        self.list = None
        self.file = None
        self.done = 0
        if ctype == 'application/x-www-form-urlencoded':
            self.read_urlencoded()
            return
        if ctype[:10] == 'multipart/':
            self.read_multi(environ, keep_blank_values, strict_parsing)
            return
        self.read_single()

    def __del__(self):
        try:
            self.file.close()
        except AttributeError:
            return

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.file.close()

    def __repr__(self):
        '''Return a printable representation.'''

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
        elif self.list is not None:
            value = self.list
        else:
            value = None
        return value

    def __getitem__(self, key):
        '''Dictionary style indexing.'''

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
        """Dictionary style get() method, including 'value' lookup."""

        if key in self:
            value = self[key]
            if isinstance(value, list):
                return [x.value for x in value]
            return value.value
        return default

    def getfirst(self, key, default=None):
        ''' Return the first value received.'''

        if key in self:
            value = self[key]
            if isinstance(value, list):
                return value[0].value
            return value.value
        return default

    def getlist(self, key):
        ''' Return list of received values.'''

        if key in self:
            value = self[key]
            if isinstance(value, list):
                return [x.value for x in value]
            return [value.value]
        return []

    def keys(self):
        '''Dictionary style keys() method.'''

        if self.list is None:
            raise TypeError('not indexable')
        return list(set((item.name for item in self.list)))

    def __contains__(self, key):
        '''Dictionary style __contains__ method.'''

        if self.list is None:
            raise TypeError('not indexable')
        return any((item.name == key for item in self.list))

    def __len__(self):
        '''Dictionary style len(x) support.'''

        return len(self.keys())

    def __bool__(self):
        if self.list is None:
            raise TypeError('Cannot be converted to bool.')
        return bool(self.list)

    def read_urlencoded(self):
        '''Internal: read data in query string format.'''

        qs = self.fp.read(self.length)
        if not isinstance(qs, bytes):
            raise ValueError(f'{self.fp!s} should return bytes, got {type(qs).__name__!s}')
        qs = qs.decode(self.encoding, self.errors)
        if self.qs_on_post:
            qs += '&' + self.qs_on_post
        query = urllib.parse.parse_qsl(qs, self.keep_blank_values, self.strict_parsing, encoding=self.encoding, errors=self.errors, max_num_fields=self.max_num_fields, separator=self.separator)
        self.list = [MiniFieldStorage(key, value) for key, value in query]
        self.skip_lines()

    FieldStorageClass = None
    def read_multi(self, environ, keep_blank_values, strict_parsing):
        '''Internal: read a part that is itself multipart.'''

        ib = self.innerboundary
        if not valid_boundary(ib):
            raise ValueError(f'Invalid boundary in multipart form: {ib!r}')
        self.list = []
        if self.qs_on_post:
            query = urllib.parse.parse_qsl(self.qs_on_post, self.keep_blank_values, self.strict_parsing, encoding=self.encoding, errors=self.errors, max_num_fields=self.max_num_fields, separator=self.separator)
            self.list.extend((MiniFieldStorage(key, value) for key, value in query))
        klass = self.FieldStorageClass or self.__class__
        first_line = self.fp.readline()
        if not isinstance(first_line, bytes):
            raise ValueError(f'{self.fp!s} should return bytes, got {type(first_line).__name__!s}')
        self.bytes_read += len(first_line)
        while first_line.strip() != b'--' + self.innerboundary and first_line:
            first_line = self.fp.readline()
            self.bytes_read += len(first_line)
        max_num_fields = self.max_num_fields
        if max_num_fields is not None:
            max_num_fields -= len(self.list)
        while True:
            parser = FeedParser()
            hdr_text = b''
            while True:
                data = self.fp.readline()
                hdr_text += data
                if not data.strip():
                    break
            if not hdr_text:
                break
            self.bytes_read += len(hdr_text)
            parser.feed(hdr_text.decode(self.encoding, self.errors))
            headers = parser.close()
            if 'content-length' in headers:
                del headers['content-length']
            limit = None if self.limit is None else self.limit - self.bytes_read
            part = klass(self.fp, headers, ib, environ, keep_blank_values, strict_parsing, limit, self.encoding, self.errors, max_num_fields, self.separator)
            if max_num_fields is not None:
                max_num_fields -= 1
                if part.list:
                    max_num_fields -= len(part.list)
                if max_num_fields < 0:
                    raise ValueError('Max number of fields exceeded')
            self.bytes_read += part.bytes_read
            self.list.append(part)
            if part.done or self.bytes_read >= self.length > 0:
                break
        self.skip_lines()

    def read_single(self):
        '''Internal: read an atomic part.'''

        if self.length >= 0:
            self.read_binary()
            self.skip_lines()
        else:
            self.read_lines()
        self.file.seek(0)

    bufsize = 8192
    def read_binary(self):
        '''Internal: read binary data.'''

        self.file = self.make_file()
        todo = self.length
        while todo >= 0 and todo > 0:
            data = self.fp.read(min(todo, self.bufsize))
            if not isinstance(data, bytes):
                raise ValueError(f'{self.fp!s} should return bytes, got {type(data).__name__!s}')
            self.bytes_read += len(data)
            if not data:
                self.done = -1
                return
            self.file.write(data)
            todo = todo - len(data)

    def read_lines(self):
        '''Internal: read lines until EOF or outerboundary.'''

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
        '''line is always bytes, not string'''

        if self.__file is not None:
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
        '''Internal: read lines until EOF.'''

        while True:
            line = self.fp.readline(65536)
            self.bytes_read += len(line)
            if not line:
                self.done = -1
                return
            self.__write(line)

    def read_lines_to_outerboundary(self):
        '''Internal: read lines until outerboundary.
        Data is read as bytes: boundaries and line ends must be converted
        to bytes for comparisons.
        '''

        next_boundary = b'--' + self.outerboundary
        last_boundary = next_boundary + b'--'
        delim = b''
        last_line_lfend = True
        _read = 0
        while True:
            if self.limit is not None:
                if 0 <= self.limit <= _read:
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
        '''Internal: skip lines until outer boundary if defined.'''

        if not self.outerboundary or self.done:
            return
        next_boundary = b'--' + self.outerboundary
        last_boundary = next_boundary + b'--'
        last_line_lfend = True
        while True:
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
        """Overridable: return a readable & writable file.

        The file will be used as follows:
        - data is written to it
        - seek(0)
        - data is read from it

        The file is opened in binary mode for files, in text mode
        for other fields

        This version opens a temporary file for reading and writing,
        and immediately deletes (unlinks) it.  The trick (on Unix!) is
        that the file can still be used, but it can't be opened by
        another process, and it will automatically be deleted when it
        is closed or when the current process terminates.

        If you want a more permanent file, you derive a class which
        overrides this method.  If you want a visible temporary file
        that is nevertheless automatically deleted when the script
        terminates, try defining a __del__ method in a derived class
        which unlinks the temporary files you have created.

        """

        if self._binary_file:
            return tempfile.TemporaryFile('wb+')
        return tempfile.TemporaryFile('w+', encoding=self.encoding, newline='\n')


def test(environ=os.environ):
    '''Robust test CGI script, usable as main program.

    Write minimal HTTP headers and dump all information provided to
    the script in HTML form.

    '''

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
    except:
        print_exception()
    print('<H1>Second try with a small maxlen...</H1>')
    maxlen = 50
    try:
        form = FieldStorage()
        print_directory()
        print_arguments()
        print_form(form)
        print_environ(environ)
    except:
        print_exception()
        return

def print_exception(type=None, value=None, tb=None, limit=None):
    if type is None:
        type, value, tb = sys.exc_info()
    import traceback
    print()
    print('<H3>Traceback (most recent call last):</H3>')
    list = traceback.format_tb(tb, limit) + traceback.format_exception_only(type, value)
    print(f'<PRE>{html.escape("".join(list[:-1]))!s}<B>{html.escape(list[-1])!s}</B></PRE>')
    del tb

def print_environ(environ=os.environ):
    '''Dump the shell environment as HTML.'''

    keys = sorted(environ.keys())
    print()
    print('<H3>Shell Environment:</H3>')
    print('<DL>')
    for key in keys:
        print('<DT>', html.escape(key), '<DD>', html.escape(environ[key]))
    print('</DL>')
    print()

def print_form(form):
    '''Dump the contents of a form as HTML.'''

    keys = sorted(form.keys())
    print()
    print('<H3>Form Contents:</H3>')
    if not keys:
        print('<P>No form fields.')
    print('<DL>')
    for key in keys:
        print('<DT>' + html.escape(key) + ':', end=' ')
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

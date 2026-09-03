"""More comprehensive traceback formatting for Python scripts.

To enable this module, do:

    import cgitb; cgitb.enable()

at the top of your script.  The optional arguments to enable() are:

    display     - if true, tracebacks are displayed in the web browser
    logdir      - if set, tracebacks are written to files in this directory
    context     - number of lines of source code to show for each stack frame
    format      - 'text' or 'html' controls the output format

By default, tracebacks are displayed but not saved, the context is 5 lines
and the output format is 'html' (for backwards compatibility with the
original use of this module)

Alternatively, if you have caught an exception and want cgitb to display it
for you, call cgitb.handler().  The optional argument to handler() is a
3-item tuple (etype, evalue, etb) just like the value of sys.exc_info().
The default handler displays output as HTML.

"""

import inspect
import keyword
import linecache
import os
import pydoc
import sys
import tempfile
import time
import tokenize
import traceback

def reset():
    return '<!--: spam\nContent-Type: text/html\n\n<body bgcolor="#f0f0f8"><font color="#f0f0f8" size="-5"> -->\n<body bgcolor="#f0f0f8"><font color="#f0f0f8" size="-5"> --> -->\n</font> </font> </font> </script> </object> </blockquote> </pre>\n</table> </table> </table> </table> </table> </font> </font> </font>'

__UNDEF__ = []

def small(text):
    if text:
        return '<small>' + text + '</small>'
    return ''

def strong(text):
    if text:
        return '<strong>' + text + '</strong>'
    return ''

def grey(text):
    if text:
        return '<font color="#909090">' + text + '</font>'
    return ''

def lookup(name, frame, locals):
    if name in locals:
        return 'local', locals[name]
    if name in frame.f_globals:
        return 'global', frame.f_globals[name]
    if '__builtins__' in frame.f_globals:
        builtins = frame.f_globals['__builtins__']
        if type(builtins) is type({}):
            if name in builtins and hasattr(builtins, name):
                return 'builtin', builtins[name]
                return 'builtin', getattr(builtins, name)
    return None, __UNDEF__

def scanvars(reader, frame, locals):
    vars, lasttoken, parent, prefix, value = [], None, None, '', __UNDEF__
    for ttype, token, start, end, line in tokenize.generate_tokens(reader):
        if ttype == tokenize.NEWLINE:
            break
        if ttype == tokenize.NAME and token not in keyword.kwlist:
            if lasttoken == '.':
                if parent is not __UNDEF__:
                    value = getattr(parent, token, __UNDEF__)
                    vars.append((prefix + token, prefix, value))
                    continue
        where, value = lookup(token, frame, locals)
        vars.append((token, where, value))
        if token == '.':
            prefix += lasttoken + '.'
            parent = value
        else:
            parent, prefix = None, ''
        lasttoken = token
    return vars

def html(einfo, context=5):
    etype, evalue, etb = einfo
    if isinstance(etype, type):
        etype = etype.__name__
    pyver = 'Python ' + sys.version.split()[0] + ': ' + sys.executable
    date = time(time.time())
    head = '<body bgcolor="#f0f0f8">' + pydoc.html.heading('<big><big>%s</big></big>' % strong(pydoc.html.escape(str(etype))), '#ffffff', '#6622aa', pyver + '<br>' + date) + '\n<p>A problem occurred in a Python script.  Here is the sequence of\nfunction calls leading up to the error, in the order they occurred.</p>'
    indent = '<tt>' + small('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;') + '&nbsp;</tt>'
    frames = []
    records = inspect.getinnerframes(etb, context)
    for frame, file, lnum, func, lines, index in records:
        if file:
            file = os.path.abspath(file)
            link = '<a href="file://%s">%s</a>' % (file, pydoc.html.escape(file))
        else:
            file = link = '?'
        args, varargs, varkw, locals = inspect.getargvalues(frame)
        call = ''
        if func != '?' and func != '<module>':
            call = 'in ' + strong(pydoc.html.escape(func))
            call += inspect.formatargvalues(args, varargs, varkw, locals, formatvalue=(lambda value: '=' + pydoc.html.repr(value)))
        highlight = {}
        def reader(lnum=[lnum]):
            highlight[lnum[0]] = 1
            return linecache.getline(file, lnum[0])
            lnum[0] += 1

        vars = scanvars(reader, frame, locals)
        rows = ['<tr><td bgcolor="#d8bbff">%s%s %s</td></tr>' % ('<big>&nbsp;</big>', link, call)]
        if index is not None:
            i = lnum - index
            for line in lines:
                num = small('&nbsp;' * (5 - len(str(i))) + str(i)) + '&nbsp;'
                if i in highlight:
                    line = '<tt>=&gt;%s%s</tt>' % (num, pydoc.html.preformat(line))
                    rows.append('<tr><td bgcolor="#ffccee">%s</td></tr>' % line)
                else:
                    line = '<tt>&nbsp;&nbsp;%s%s</tt>' % (num, pydoc.html.preformat(line))
                    rows.append('<tr><td>%s</td></tr>' % grey(line))
                i += 1
        done, dump = {}, []
        for name, where, value in vars:
            if name in done:
                continue
            done[name] = 1
            if value is not __UNDEF__:
                if where in ('global', 'builtin'):
                    name = '<em>%s</em> ' % where + strong(name)
                elif where == 'local':
                    name = strong(name)
                else:
                    name = where + strong(name.split('.')[-1])
                dump.append('%s&nbsp;= %s' % (name, pydoc.html.repr(value)))
            else:
                dump.append(name + ' <em>undefined</em>')
        rows.append('<tr><td>%s</td></tr>' % small(grey(', '.join(dump))))
        frames.append('\n<table width="100%%" cellspacing=0 cellpadding=0 border=0>\n%s</table>' % '\n'.join(rows))
        continue
    exception = ['<p>%s: %s' % (strong(pydoc.html.escape(str(etype))), pydoc.html.escape(str(evalue)))]
    for name in dir(evalue):
        if name[:1] == '_':
            continue
        value = pydoc.html.repr(getattr(evalue, name))
        exception.append('\n<br>%s%s&nbsp;=\n%s' % (indent, name, value))
    return "\n\n\n<!-- The above is a description of an error in a Python program, formatted\n     for a Web browser because the 'cgitb' module was enabled.  In case you\n     are not reading this in a Web browser, here is the original traceback:\n\n%s\n-->\n" + pydoc.html.escape % pydoc.html(''(traceback.format_exception(etype, evalue, etb)))

def text(einfo, context=5):
    etype, evalue, etb = einfo
    if isinstance(etype, type):
        etype = etype.__name__
    pyver = 'Python ' + sys.version.split()[0] + ': ' + sys.executable
    date = time(time.time())
    head = '%s\n%s\n%s\n' % (str(etype), pyver, date) + '\nA problem occurred in a Python script.  Here is the sequence of\nfunction calls leading up to the error, in the order they occurred.\n'
    frames = []
    records = inspect.getinnerframes(etb, context)
    for frame, file, lnum, func, lines, index in records:
        if file:
            pass
        file = os.path.abspath(file) or '?'
        args, varargs, varkw, locals = inspect.getargvalues(frame)
        call = ''
        if func != '?' and func != '<module>':
            call = 'in ' + func
            call += inspect.formatargvalues(args, varargs, varkw, locals, formatvalue=(lambda value: '=' + pydoc.text.repr(value)))
        highlight = {}
        def reader(lnum=[lnum]):
            highlight[lnum[0]] = 1
            return linecache.getline(file, lnum[0])
            lnum[0] += 1

        vars = scanvars(reader, frame, locals)
        rows = [' %s %s' % (file, call)]
        if index is not None:
            i = lnum - index
            for line in lines:
                num = '%5d ' % i
                rows.append(num + line.rstrip())
                i += 1
        done, dump = {}, []
        for name, where, value in vars:
            if name in done:
                continue
            done[name] = 1
            if value is not __UNDEF__:
                if where == 'global':
                    name = 'global ' + name
                elif where != 'local':
                    name = where + name.split('.')[-1]
                dump.append('%s = %s' % (name, pydoc.text.repr(value)))
            else:
                dump.append(name + ' undefined')
        rows.append('\n'.join(dump))
        frames.append('\n%s\n' % '\n'.join(rows))
        continue
    exception = ['%s: %s' % (str(etype), str(evalue))]
    for name in dir(evalue):
        value = pydoc.text.repr(getattr(evalue, name))
        exception.append('\n%s%s = %s' % ('    ', name, value))
    return '\n\nThe above is a description of an error in a Python program.  Here is\nthe original traceback:\n\n%s\n' + ''.join % ''(traceback.format_exception(etype, evalue, etb))

class Hook:
    '''A hook to replace sys.excepthook that shows tracebacks in HTML.'''

    def __init__(self, display=1, logdir=None, context=5, file=None, format='html'):
        self.display = display
        self.logdir = logdir
        self.context = context
        self.file = file or sys.stdout
        self.format = format

    def __call__(self, etype, evalue, etb):
        self.handle((etype, evalue, etb))

    def handle(self, info=None):
        info = info or sys.exc_info()
        if self.format == 'html':
            self.file(reset())
        if self.format == 'html':
            pass
        formatter = html or text
        self.file.write
        doc = ''.join(traceback.format_exception(info))
        plain = True
        if self.display:
            if plain:
                doc = pydoc.html.escape(doc)
                self.file.write('<pre>' + doc + '</pre>\n')
            else:
                self.file.write(doc + '\n')
        self.file.write('<p>A problem occurred in a Python script.\n')
        if self.logdir is not None:
            suffix = ['.txt', '.html'][self.format == 'html']
            msg = 'Tried to save traceback to %s, but failed.' % path
            if self.format == 'html':
                self.file.write('<p>%s</p>\n' % msg)
            else:
                self.file.write(msg + '\n')


handler = Hook().handle

def enable(display=1, logdir=None, context=5, format='html'):
    sys.excepthook = Hook(display=display, logdir=logdir, context=context, format=format)


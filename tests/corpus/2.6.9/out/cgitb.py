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

__author__ = 'Ka-Ping Yee'
__version__ = '$Revision$'
import sys

def reset():
    return '<!--: spam\nContent-Type: text/html\n\n<body bgcolor="#f0f0f8"><font color="#f0f0f8" size="-5"> -->\n<body bgcolor="#f0f0f8"><font color="#f0f0f8" size="-5"> --> -->\n</font> </font> </font> </script> </object> </blockquote> </pre>\n</table> </table> </table> </table> </table> </font> </font> </font>'

__UNDEF__ = []

def small(text):
    /* unsupported opcode: JUMP_IF_FALSE 13 @3 */
    text
    return '<small>' + text + '</small>'

def strong(text):
    /* unsupported opcode: JUMP_IF_FALSE 13 @3 */
    text
    return '<strong>' + text + '</strong>'

def grey(text):
    /* unsupported opcode: JUMP_IF_FALSE 13 @3 */
    text
    return '<font color="#909090">' + text + '</font>'

def lookup(name, frame, locals):
    /* unsupported opcode: JUMP_IF_FALSE 15 @9 */
    name in locals
    return 'local', locals[name]

def scanvars(reader, frame, locals):
    import tokenize
    import keyword
    vars, lasttoken, parent, prefix, value = [], None, None, '', __UNDEF__
    for ttype, token, start, end, line in tokenize.generate_tokens(reader):
        /* unsupported opcode: JUMP_IF_FALSE 5 @109 */
        ttype == tokenize.NEWLINE
        break
        /* unsupported opcode: JUMP_IF_FALSE 144 @130 */
        ttype == tokenize.NAME
        /* unsupported opcode: JUMP_IF_FALSE 128 @146 */
        token not in keyword.kwlist
        /* unsupported opcode: JUMP_IF_FALSE 65 @159 */
        lasttoken == '.'
        /* unsupported opcode: JUMP_IF_FALSE 48 @172 */
        parent is not __UNDEF__
        value = getattr(parent, token, __UNDEF__)
        vars.append(prefix + token, prefix, value)
        /* unsupported opcode: JUMP_IF_FALSE 24 @287 */
        token == '.'
        prefix += lasttoken + '.'
        parent = value
        parent, prefix = None, ''
        lasttoken = token
        continue
    return vars

def html(einfo, context=5):
    import os
    import types
    import time
    import traceback
    import linecache
    import inspect
    import pydoc
    etype, evalue, etb = einfo
    /* unsupported opcode: JUMP_IF_FALSE 13 @117 */
    type(etype) is types.ClassType
    etype = etype.__name__
    pyver = 'Python ' + sys.version.split()[0] + ': ' + sys.executable
    date = time.ctime(time.time())
    head = '<body bgcolor="#f0f0f8">' + pydoc.html.heading('<big><big>%s</big></big>' % strong(pydoc.html.escape(str(etype))), '#ffffff', '#6622aa', pyver + '<br>' + date) + '\n<p>A problem occurred in a Python script.  Here is the sequence of\nfunction calls leading up to the error, in the order they occurred.</p>'
    indent = '<tt>' + small('&nbsp;' * 5) + '&nbsp;</tt>'
    frames = []
    records = inspect.getinnerframes(etb, context)
    for frame, file, lnum, func, lines, index in records:
        /* unsupported opcode: JUMP_IF_FALSE 50 @342 */
        file
        file = os.path.abspath(file)
        link = '<a href="file://%s">%s</a>' % (file, pydoc.html.escape(file))
        file = link = '?'
        args, varargs, varkw, locals = inspect.getargvalues(frame)
        call = ''
        /* unsupported opcode: JUMP_IF_FALSE 57 @448 */
        func != '?'
        call = inspect.formatargvalues + args(varkw, locals, 'formatvalue', lambda value: '=' + pydoc.html.repr(value), varargs)
        'in ' + strong(func)
        highlight = {}
        def reader(lnum=highlight, file, linecache):
            highlight[lnum[0]] = 1
            try:
                return linecache.getline(file, lnum[0])
            finally:
                lnum[0] += 1

        vars = scanvars(reader, frame, locals)
        rows = ['<tr><td bgcolor="#d8bbff">%s%s %s</td></tr>' % ('<big>&nbsp;</big>', link, call)]
        /* unsupported opcode: JUMP_IF_FALSE 172 @591 */
        index is not None
        i = lnum - index
        for line in lines:
            num = small('&nbsp;' * (5 - len(str(i))) + str(i)) + '&nbsp;'
            line = '<tt>%s%s</tt>' % (num, pydoc.html.preformat(line))
            /* unsupported opcode: JUMP_IF_FALSE 21 @701 */
            i in highlight
            rows.append('<tr><td bgcolor="#ffccee">%s</td></tr>' % line)
            rows.append('<tr><td>%s</td></tr>' % grey(line))
            i += 1
            continue
            break
        done, dump = {}, []
        for name, where, value in vars:
            /* unsupported opcode: JUMP_IF_FALSE 7 @811 */
            name in done
            continue
            done[name] = 1
            /* unsupported opcode: JUMP_IF_FALSE 134 @841 */
            value is not __UNDEF__
            /* unsupported opcode: JUMP_IF_FALSE 24 @854 */
            where in ('global', 'builtin')
            name = '<em>%s</em> ' % where + strong(name)
            /* unsupported opcode: JUMP_IF_FALSE 16 @891 */
            where == 'local'
            name = strong(name)
            name = where + strong(name.split('.')[-1])
            dump.append('%s&nbsp;= %s' % (name, pydoc.html.repr(value)))
            continue
            dump.append(name + ' <em>undefined</em>')
            continue
        rows.append('<tr><td>%s</td></tr>' % small(grey(', '.join(dump))))
        frames.append('\n<table width="100%%" cellspacing=0 cellpadding=0 border=0>\n%s</table>' % '\n'.join(rows))
        continue
    exception = ['<p>%s: %s' % (strong(pydoc.html.escape(str(etype))), pydoc.html.escape(str(evalue)))]
    /* unsupported opcode: JUMP_IF_FALSE 104 @1141 */
    isinstance(evalue, BaseException)
    for name in dir(evalue):
        /* unsupported opcode: JUMP_IF_FALSE 7 @1177 */
        name[:1] == '_'
        continue
        value = pydoc.html.repr(getattr(evalue, name))
        exception.append('\n<br>%s%s&nbsp;=\n%s' % (indent, name, value))
        continue
        break
    import traceback
    return head + ''.join(frames) + ''.join(exception) + "\n\n\n<!-- The above is a description of an error in a Python program, formatted\n     for a Web browser because the 'cgitb' module was enabled.  In case you\n     are not reading this in a Web browser, here is the original traceback:\n\n%s\n-->\n" % pydoc.html.escape(''.join(traceback.format_exception(etype, evalue, etb)))

def text(einfo, context=5):
    import os
    import types
    import time
    import traceback
    import linecache
    import inspect
    import pydoc
    etype, evalue, etb = einfo
    /* unsupported opcode: JUMP_IF_FALSE 13 @117 */
    type(etype) is types.ClassType
    etype = etype.__name__
    pyver = 'Python ' + sys.version.split()[0] + ': ' + sys.executable
    date = time.ctime(time.time())
    head = '%s\n%s\n%s\n' % (str(etype), pyver, date) + '\nA problem occurred in a Python script.  Here is the sequence of\nfunction calls leading up to the error, in the order they occurred.\n'
    frames = []
    records = inspect.getinnerframes(etb, context)
    for frame, file, lnum, func, lines, index in records:
        /* unsupported opcode: JUMP_IF_FALSE 19 @276 */
        file
        /* unsupported opcode: JUMP_IF_TRUE 4 @295 */
        os.path.abspath(file)
        file = '?'
        args, varargs, varkw, locals = inspect.getargvalues(frame)
        call = ''
        /* unsupported opcode: JUMP_IF_FALSE 51 @347 */
        func != '?'
        call = inspect.formatargvalues + args(varkw, locals, 'formatvalue', lambda value: '=' + pydoc.text.repr(value), varargs)
        'in ' + func
        highlight = {}
        def reader(lnum=highlight, file, linecache):
            highlight[lnum[0]] = 1
            try:
                return linecache.getline(file, lnum[0])
            finally:
                lnum[0] += 1

        vars = scanvars(reader, frame, locals)
        rows = [' %s %s' % (file, call)]
        /* unsupported opcode: JUMP_IF_FALSE 74 @481 */
        index is not None
        i = lnum - index
        for line in lines:
            num = '%5d ' % i
            rows.append(num + line.rstrip())
            i += 1
            continue
            break
        done, dump = {}, []
        for name, where, value in vars:
            /* unsupported opcode: JUMP_IF_FALSE 7 @603 */
            name in done
            continue
            done[name] = 1
            /* unsupported opcode: JUMP_IF_FALSE 106 @633 */
            value is not __UNDEF__
            /* unsupported opcode: JUMP_IF_FALSE 14 @646 */
            where == 'global'
            name = 'global ' + name
            /* unsupported opcode: JUMP_IF_FALSE 27 @673 */
            where != 'local'
            name = where + name.split('.')[-1]
            dump.append('%s = %s' % (name, pydoc.text.repr(value)))
            continue
            dump.append(name + ' undefined')
            continue
        rows.append('\n'.join(dump))
        frames.append('\n%s\n' % '\n'.join(rows))
        continue
    exception = ['%s: %s' % (str(etype), str(evalue))]
    /* unsupported opcode: JUMP_IF_FALSE 80 @859 */
    isinstance(evalue, BaseException)
    for name in dir(evalue):
        value = pydoc.text.repr(getattr(evalue, name))
        exception.append('\n%s%s = %s' % ('    ', name, value))
        continue
        break
    import traceback
    return head + ''.join(frames) + ''.join(exception) + '\n\nThe above is a description of an error in a Python program.  Here is\nthe original traceback:\n\n%s\n' % ''.join(traceback.format_exception(etype, evalue, etb))

class Hook(()):
    pass

handler = Hook().handle

def enable(display=1, logdir=None, context=5, format='html'):
    sys.excepthook = logdir('context', context, 'format', format)

# WARNING: Decompyle incomplete

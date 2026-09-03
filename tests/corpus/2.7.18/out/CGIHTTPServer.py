"""CGI-savvy HTTP Server.

This module builds on SimpleHTTPServer by implementing GET and POST
requests to cgi-bin scripts.

If the os.fork() function is not present (e.g. on Windows),
os.popen2() is used as a fallback, with slightly altered semantics; if
that function is not present either (e.g. on Macintosh), only Python
scripts are supported, and they are executed by the current process.

In all cases, the implementation is intentionally naive -- all
requests are executed sychronously.

SECURITY WARNING: DON'T USE THIS CODE UNLESS YOU ARE INSIDE A FIREWALL
-- it may execute arbitrary Python code or external programs.

Note that status code 200 is sent prior to execution of a CGI script, so
scripts cannot send other status codes such as 302 (redirect).
"""

__version__ = '0.4'
__all__ = ['CGIHTTPRequestHandler']
import os
import sys
import urllib
import BaseHTTPServer
import SimpleHTTPServer
import select
import copy

class CGIHTTPRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    pass

def _url_collapse_path(path):
    path, _, query = path.partition('?')
    path = urllib.unquote(path)
    path_parts = path.split('/')
    head_parts = []
    for part in path_parts[:-1]:
        if part == '..':
            head_parts.pop()
            continue
        if part:
            pass
        if part != '.':
            pass
        head_parts.append(part)
        continue
        continue
    if path_parts:
        tail_part = path_parts.pop()
        if tail_part:
            if tail_part == '..':
                head_parts.pop()
                tail_part = ''
            elif tail_part == '.':
                tail_part = ''
            tail_part = ''
    if query:
        tail_part = '?'.join(tail_part, query)
    splitpath = '/' + '/'.join(head_parts), tail_part
    collapsed_path = '/'.join(splitpath)
    return collapsed_path

nobody = None

def nobody_uid():
    global nobody
    if nobody:
        return nobody
    return nobody

def executable(path):
    return st.st_mode & 73 != 0

def test(HandlerClass=CGIHTTPRequestHandler, ServerClass=BaseHTTPServer.HTTPServer):
    SimpleHTTPServer.test(HandlerClass, ServerClass)

if __name__ == '__main__':
    test()
# WARNING: Decompyle incomplete

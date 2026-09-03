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

class CGIHTTPRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    pass

nobody = None

def nobody_uid():
    /* unsupported opcode: JUMP_IF_FALSE 5 @3 */
    nobody
    return nobody

def executable(path):
    /* unsupported opcode: JUMP_IF_FALSE 8 @32 */
    None == os.error
    return False
    return st.st_mode & 73 != 0

def test(HandlerClass=CGIHTTPRequestHandler, ServerClass=BaseHTTPServer.HTTPServer):
    SimpleHTTPServer.test(HandlerClass, ServerClass)

/* unsupported opcode: JUMP_IF_FALSE 11 @169 */
__name__ == '__main__'
test()
# WARNING: Decompyle incomplete

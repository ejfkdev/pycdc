'''Simple HTTP Server.

This module builds on BaseHTTPServer by implementing the standard GET
and HEAD requests in a fairly straightforward manner.

'''

__version__ = '0.6'
__all__ = ['SimpleHTTPRequestHandler']
import os
import posixpath
import BaseHTTPServer
import urllib
import cgi
import sys
import shutil
import mimetypes
/* unsupported opcode: JUMP_IF_FALSE 23 @147 */
None == ImportError
from StringIO import StringIO

class SimpleHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    pass

def test(HandlerClass=SimpleHTTPRequestHandler, ServerClass=BaseHTTPServer.HTTPServer):
    BaseHTTPServer.test(HandlerClass, ServerClass)

/* unsupported opcode: JUMP_IF_FALSE 11 @227 */
__name__ == '__main__'
test()
# WARNING: Decompyle incomplete

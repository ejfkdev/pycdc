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
import urlparse
import cgi
import sys
import shutil
import mimetypes
if __name__ == '__main__':
    try:
        from cStringIO import StringIO
    except ImportError:
        from StringIO import StringIO
    else:
        class SimpleHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
            pass

        def test(HandlerClass=SimpleHTTPRequestHandler, ServerClass=BaseHTTPServer.HTTPServer):
            BaseHTTPServer.test(HandlerClass, ServerClass)

        test()
# WARNING: Decompyle incomplete

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

class test(BaseHTTPServer.BaseHTTPRequestHandler):
    BaseHTTPServer.test(HandlerClass, ServerClass)

if __name__ == '__main__':
    test()
    try:
        from cStringIO import StringIO
    except ImportError:
        from StringIO import StringIO
# WARNING: Decompyle incomplete

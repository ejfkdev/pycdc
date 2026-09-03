"""HTTP server base class.

Note: the class in this module doesn't implement any HTTP request; see
SimpleHTTPServer for simple implementations of GET, HEAD and POST
(including CGI scripts).  It does, however, optionally implement HTTP/1.1
persistent connections, as of version 0.3.

Contents:

- BaseHTTPRequestHandler: HTTP request handler base class
- test: test function

XXX To do:

- log requests even later (to capture byte count)
- log user-agent header and other interesting goodies
- send error log to separate file
"""

__version__ = '0.3'
__all__ = ['HTTPServer', 'BaseHTTPRequestHandler']
import sys
import time
import socket
from warnings import filterwarnings
from warnings import catch_warnings
catch_warnings().__enter__()
/* unsupported opcode: JUMP_IF_FALSE 20 @109 */
sys.py3kwarning
filterwarnings('ignore', '.*mimetools has been removed', DeprecationWarning)
catch_warnings().__exit__
import mimetools
import SocketServer
DEFAULT_ERROR_MESSAGE = '<head>\n<title>Error response</title>\n</head>\n<body>\n<h1>Error response</h1>\n<p>Error code %(code)d.\n<p>Message: %(message)s.\n<p>Error code explanation: %(code)s = %(explain)s.\n</body>\n'
DEFAULT_ERROR_CONTENT_TYPE = 'text/html'

def _quote_html(html):
    return html.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

class HTTPServer(SocketServer.TCPServer):
    pass

class BaseHTTPRequestHandler(SocketServer.StreamRequestHandler):
    pass

def test(HandlerClass=BaseHTTPRequestHandler, ServerClass=HTTPServer, protocol='HTTP/1.0'):
    /* unsupported opcode: JUMP_IF_FALSE 23 @10 */
    sys.argv[1:]
    port = int(sys.argv[1])
    port = 8000
    server_address = '', port
    HandlerClass.protocol_version = protocol
    httpd = ServerClass(server_address, HandlerClass)
    sa = httpd.socket.getsockname()
    print 'Serving HTTP on', sa[0], 'port', sa[1], '...'
    httpd.serve_forever()

/* unsupported opcode: JUMP_IF_FALSE 11 @261 */
__name__ == '__main__'
test()
# WARNING: Decompyle incomplete

'''Self documenting XML-RPC Server.

This module can be used to create XML-RPC servers that
serve pydoc-style documentation in response to HTTP
GET requests. This documentation is dynamically generated
based on the functions and methods registered with the
server.

This module is built upon the pydoc and SimpleXMLRPCServer
modules.
'''

import pydoc
import inspect
import re
import sys
from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler
from SimpleXMLRPCServer import CGIXMLRPCRequestHandler
from SimpleXMLRPCServer import resolve_dotted_attribute

def _html_escape_quote(s):
    s = s.replace('&', '&amp;')
    s = s.replace('<', '&lt;')
    s = s.replace('>', '&gt;')
    s = s.replace('"', '&quot;')
    s = s.replace("'", '&#x27;')
    return s

class ServerHTMLDoc(pydoc.HTMLDoc):
    pass

class XMLRPCDocGenerator(()):
    pass

class DocXMLRPCRequestHandler(SimpleXMLRPCRequestHandler):
    pass

class DocXMLRPCServer(SimpleXMLRPCServer, XMLRPCDocGenerator):
    pass

class DocCGIXMLRPCRequestHandler(CGIXMLRPCRequestHandler, XMLRPCDocGenerator):
    pass


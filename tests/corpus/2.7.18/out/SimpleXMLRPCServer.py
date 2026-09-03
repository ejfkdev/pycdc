'''Simple XML-RPC Server.

This module can be used to create simple XML-RPC servers
by creating a server and either installing functions, a
class instance, or by extending the SimpleXMLRPCServer
class.

It can also be used to handle XML-RPC requests in a CGI
environment using CGIXMLRPCRequestHandler.

A list of possible usage patterns follows:

1. Install functions:

server = SimpleXMLRPCServer(("localhost", 8000))
server.register_function(pow)
server.register_function(lambda x,y: x+y, 'add')
server.serve_forever()

2. Install an instance:

class MyFuncs:
    def __init__(self):
        # make all of the string functions available through
        # string.func_name
        import string
        self.string = string
    def _listMethods(self):
        # implement this method so that system.listMethods
        # knows to advertise the strings methods
        return list_public_methods(self) + \\
                ['string.' + method for method in list_public_methods(self.string)]
    def pow(self, x, y): return pow(x, y)
    def add(self, x, y) : return x + y

server = SimpleXMLRPCServer(("localhost", 8000))
server.register_introspection_functions()
server.register_instance(MyFuncs())
server.serve_forever()

3. Install an instance with custom dispatch method:

class Math:
    def _listMethods(self):
        # this method must be present for system.listMethods
        # to work
        return ['add', 'pow']
    def _methodHelp(self, method):
        # this method must be present for system.methodHelp
        # to work
        if method == 'add':
            return "add(2,3) => 5"
        elif method == 'pow':
            return "pow(x, y[, z]) => number"
        else:
            # By convention, return empty
            # string if no help is available
            return ""
    def _dispatch(self, method, params):
        if method == 'pow':
            return pow(*params)
        elif method == 'add':
            return params[0] + params[1]
        else:
            raise 'bad method'

server = SimpleXMLRPCServer(("localhost", 8000))
server.register_introspection_functions()
server.register_instance(Math())
server.serve_forever()

4. Subclass SimpleXMLRPCServer:

class MathServer(SimpleXMLRPCServer):
    def _dispatch(self, method, params):
        try:
            # We are forcing the 'export_' prefix on methods that are
            # callable through XML-RPC to prevent potential security
            # problems
            func = getattr(self, 'export_' + method)
        except AttributeError:
            raise Exception('method "%s" is not supported' % method)
        else:
            return func(*params)

    def export_add(self, x, y):
        return x + y

server = MathServer(("localhost", 8000))
server.serve_forever()

5. CGI script:

server = CGIXMLRPCRequestHandler()
server.register_function(pow)
server.handle_request()
'''

import xmlrpclib
from xmlrpclib import Fault
import SocketServer
import BaseHTTPServer
import sys
import os
import traceback
import re

def resolve_dotted_attribute(obj, attr, allow_dotted_names=True):
    if allow_dotted_names:
        attrs = attr.split('.')
    else:
        attrs = [attr]
    for i in attrs:
        if i.startswith('_'):
            raise AttributeError('attempt to access private attribute "%s"' % i)
            continue
        obj = getattr(obj, i)
        continue
    return obj

def list_public_methods(obj):
    return [member for member in dir(obj) if member.startswith('_') if hasattr(getattr(obj, member), '__call__')]

def remove_duplicates(lst):
    for x in lst:
        u = {}
        u[x] = 1
        continue
    return u.keys()

class SimpleXMLRPCDispatcher:
    pass

class SimpleXMLRPCRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    pass

class SimpleXMLRPCServer(SocketServer.TCPServer, SimpleXMLRPCDispatcher):
    pass

class MultiPathXMLRPCServer(SimpleXMLRPCServer):
    pass

class CGIXMLRPCRequestHandler(SimpleXMLRPCDispatcher):
    pass

if __name__ == '__main__':
    print 'Running XML-RPC server on port 8000'
    server = SimpleXMLRPCServer('localhost', 8000)
    server.register_function(pow)
    server.register_function(lambda x, y: x + y, 'add')
    server.register_multicall_functions()
    server.serve_forever()
    try:
        import fcntl
    except ImportError, fcntl:
        pass
# WARNING: Decompyle incomplete

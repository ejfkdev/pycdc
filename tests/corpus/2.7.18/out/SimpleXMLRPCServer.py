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
try:
    import fcntl
except ImportError:
    fcntl = None

def resolve_dotted_attribute(obj, attr, allow_dotted_names=True):
    if allow_dotted_names:
        attrs = attr.split('.')
    else:
        attrs = [attr]
    for i in attrs:
        if i.startswith('_'):
            raise AttributeError('attempt to access private attribute "%s"' % i)
        else:
            obj = getattr(obj, i)
    return obj

def list_public_methods(obj):
    return [member for member in dir(obj) if member.startswith('_') if hasattr(getattr(obj, member), '__call__')]

def remove_duplicates(lst):
    u = {}
    for x in lst:
        u[x] = 1
    return u.keys()

class SimpleXMLRPCDispatcher:
    """Mix-in class that dispatches XML-RPC requests.

    This class is used to register XML-RPC method handlers
    and then to dispatch them. This class doesn't need to be
    instanced directly when used by SimpleXMLRPCServer but it
    can be instanced when used by the MultiPathXMLRPCServer.
    """

    def __init__(self, allow_none=False, encoding=None):
        self.funcs = {}
        self.instance = None
        self.allow_none = allow_none
        self.encoding = encoding

    def register_instance(self, instance, allow_dotted_names=False):
        self.instance = instance
        self.allow_dotted_names = allow_dotted_names

    def register_function(self, function, name=None):
        if name is None:
            name = function.__name__
        self.funcs[name] = function

    def register_introspection_functions(self):
        self.funcs.update({'system.listMethods': self.system_listMethods, 'system.methodSignature': self.system_methodSignature, 'system.methodHelp': self.system_methodHelp})

    def register_multicall_functions(self):
        self.funcs.update({'system.multicall': self.system_multicall})

    def _marshaled_dispatch(self, data, dispatch_method=None, path=None):
        exc_type, exc_value, exc_tb = sys.exc_info()
        response = xmlrpclib.dumps(xmlrpclib.Fault(1, '%s:%s' % (exc_type, exc_value)), encoding=self.encoding, allow_none=self.allow_none)
        try:
            params, method = xmlrpclib.loads(data)
            if dispatch_method is not None:
                response = dispatch_method(method, params)
            else:
                response = self._dispatch(method, params)
            response = (response,)
            response = xmlrpclib.dumps(response, methodresponse=1, allow_none=self.allow_none, encoding=self.encoding)
        except Fault:
            fault = None
            response = xmlrpclib.dumps(fault, allow_none=self.allow_none, encoding=self.encoding)
        return response

    def system_listMethods(self):
        methods = self.funcs.keys()
        if self.instance is not None:
            if hasattr(self.instance, '_listMethods'):
                methods = remove_duplicates(methods + self.instance._listMethods())
            elif not hasattr(self.instance, '_dispatch'):
                methods = remove_duplicates(methods + list_public_methods(self.instance))
        methods.sort()
        return methods

    def system_methodSignature(self, method_name):
        return 'signatures not supported'

    def system_methodHelp(self, method_name):
        method = None
        if method_name in self.funcs:
            method = self.funcs[method_name]
        elif self.instance is not None:
            if hasattr(self.instance, '_methodHelp'):
                return self.instance._methodHelp(method_name)
            if not hasattr(self.instance, '_dispatch'):
                try:
                    method = resolve_dotted_attribute(self.instance, method_name, self.allow_dotted_names)
                except AttributeError:
                    pass
        if method is None:
            return ''
        import pydoc
        return pydoc.getdoc(method)

    def system_multicall(self, call_list):
        results = []
        for call in call_list:
            method_name = call['methodName']
            params = call['params']
            exc_type, exc_value, exc_tb = sys.exc_info()
            results.append({'faultCode': 1, 'faultString': '%s:%s' % (exc_type, exc_value)})
            try:
                results.append([self._dispatch(method_name, params)])
            except Fault:
                fault = None
                results.append({'faultCode': fault.faultCode, 'faultString': fault.faultString})
                continue
            continue
        return results

    def _dispatch(self, method, params):
        func = None
        if self.instance is not None:
            if hasattr(self.instance, '_dispatch'):
                return self.instance._dispatch(method, params)
            func = resolve_dotted_attribute(self.instance, method, self.allow_dotted_names)
            try:
                func = self.funcs[method]
            except AttributeError:
                pass
        if func is not None:
            return func(*params)
        raise Exception('method "%s" is not supported' % method)


class SimpleXMLRPCRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    '''Simple XML-RPC request handler class.

    Handles all HTTP POST requests and attempts to decode them as
    XML-RPC requests.
    '''

    rpc_paths = ('/', '/RPC2')
    encode_threshold = 1400
    wbufsize = -1
    disable_nagle_algorithm = True
    aepattern = re.compile('\n                            \\s* ([^\\s;]+) \\s*            #content-coding\n                            (;\\s* q \\s*=\\s* ([0-9\\.]+))? #q\n                            ', re.VERBOSE | re.IGNORECASE)
    def accept_encodings(self):
        r = {}
        ae = self.headers.get('Accept-Encoding', '')
        for e in ae.split(','):
            match = self.aepattern.match(e)
            if match:
                v = match.group(3)
                v = float(v) if v else 1.0
                r[match.group(1)] = v
            continue
        return r

    def is_rpc_path_valid(self):
        if self.rpc_paths:
            return self.path in self.rpc_paths
        return True

    def do_POST(self):
        if not self.is_rpc_path_valid():
            self.report_404()
            return
        data = ''.join(L)
        data = self.decode_request_content(data)
        if data is None:
            return
        response = self.server._marshaled_dispatch(data, getattr(self, '_dispatch', None), self.path)
        if self.encode_threshold is not None and len(response) > self.encode_threshold:
            if q:
                try:
                    pass
                except NotImplementedError:
                    pass
        self.send_header('Content-length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def decode_request_content(self, data):
        encoding = self.headers.get('content-encoding', 'identity').lower()
        if encoding == 'identity':
            return data
        if encoding == 'gzip':
            try:
                return xmlrpclib.gzip_decode(data)
            except NotImplementedError:
                self.send_response(501, 'encoding %r not supported' % encoding)
            except ValueError:
                self.send_response(400, 'error decoding gzip content')
        else:
            self.send_response(501, 'encoding %r not supported' % encoding)
        self.send_header('Content-length', '0')
        self.end_headers()

    def report_404(self):
        self.send_response(404)
        response = 'No such page'
        self.send_header('Content-type', 'text/plain')
        self.send_header('Content-length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_request(self, code='-', size='-'):
        if self.server.logRequests:
            BaseHTTPServer.BaseHTTPRequestHandler.log_request(self, code, size)


class SimpleXMLRPCServer(SocketServer.TCPServer, SimpleXMLRPCDispatcher):
    '''Simple XML-RPC server.

    Simple XML-RPC server that allows functions and a single instance
    to be installed to handle requests. The default implementation
    attempts to dispatch XML-RPC calls to the functions or instance
    installed in the server. Override the _dispatch method inhereted
    from SimpleXMLRPCDispatcher to change this behavior.
    '''

    allow_reuse_address = True
    _send_traceback_header = False
    def __init__(self, addr, requestHandler=SimpleXMLRPCRequestHandler, logRequests=True, allow_none=False, encoding=None, bind_and_activate=True):
        self.logRequests = logRequests
        SimpleXMLRPCDispatcher.__init__(self, allow_none, encoding)
        SocketServer.TCPServer.__init__(self, addr, requestHandler, bind_and_activate)
        if fcntl is not None and hasattr(fcntl, 'FD_CLOEXEC'):
            flags = fcntl.fcntl(self.fileno(), fcntl.F_GETFD)
            flags |= fcntl.FD_CLOEXEC
            fcntl.fcntl(self.fileno(), fcntl.F_SETFD, flags)


class MultiPathXMLRPCServer(SimpleXMLRPCServer):
    """Multipath XML-RPC Server
    This specialization of SimpleXMLRPCServer allows the user to create
    multiple Dispatcher instances and assign them to different
    HTTP request paths.  This makes it possible to run two or more
    'virtual XML-RPC servers' at the same port.
    Make sure that the requestHandler accepts the paths in question.
    """

    def __init__(self, addr, requestHandler=SimpleXMLRPCRequestHandler, logRequests=True, allow_none=False, encoding=None, bind_and_activate=True):
        SimpleXMLRPCServer.__init__(self, addr, requestHandler, logRequests, allow_none, encoding, bind_and_activate)
        self.dispatchers = {}
        self.allow_none = allow_none
        self.encoding = encoding

    def add_dispatcher(self, path, dispatcher):
        self.dispatchers[path] = dispatcher
        return dispatcher

    def get_dispatcher(self, path):
        return self.dispatchers[path]

    def _marshaled_dispatch(self, data, dispatch_method=None, path=None):
        try:
            response = self.dispatchers[path]._marshaled_dispatch(data, dispatch_method, path)
        except:
            exc_type, exc_value = sys.exc_info()[:2]
            response = xmlrpclib.dumps(xmlrpclib.Fault(1, '%s:%s' % (exc_type, exc_value)), encoding=self.encoding, allow_none=self.allow_none)
        return response


class CGIXMLRPCRequestHandler(SimpleXMLRPCDispatcher):
    '''Simple handler for XML-RPC data passed through CGI.'''

    def __init__(self, allow_none=False, encoding=None):
        SimpleXMLRPCDispatcher.__init__(self, allow_none, encoding)

    def handle_xmlrpc(self, request_text):
        response = self._marshaled_dispatch(request_text)
        print 'Content-Type: text/xml'
        print 'Content-Length: %d' % len(response)
        print
        sys.stdout.write(response)

    def handle_get(self):
        code = 400
        message, explain = BaseHTTPServer.BaseHTTPRequestHandler.responses[code]
        response = BaseHTTPServer.DEFAULT_ERROR_MESSAGE % {'code': code, 'message': message, 'explain': explain}
        print 'Status: %d %s' % (code, message)
        print 'Content-Type: %s' % BaseHTTPServer.DEFAULT_ERROR_CONTENT_TYPE
        print 'Content-Length: %d' % len(response)
        print
        sys.stdout.write(response)

    def handle_request(self, request_text=None):
        if request_text is None and os.environ.get('REQUEST_METHOD', None) == 'GET':
            self.handle_get()
        try:
            length = int(os.environ.get('CONTENT_LENGTH', None))
        except (TypeError, ValueError):
            length = -1
        if request_text is None:
            request_text = sys.stdin.read(length)
        self.handle_xmlrpc(request_text)


if __name__ == '__main__':
    print 'Running XML-RPC server on port 8000'
    server = SimpleXMLRPCServer(('localhost', 8000))
    server.register_function(pow)
    server.register_function((lambda x, y: x + y), 'add')
    server.register_multicall_functions()
    server.serve_forever()
# WARNING: Decompyle incomplete

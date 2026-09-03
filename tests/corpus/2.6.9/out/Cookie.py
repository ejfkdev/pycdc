'''
Here's a sample session to show how to use this module.
At the moment, this is the only documentation.

The Basics
----------

Importing is easy..

   >>> import Cookie

Most of the time you start by creating a cookie.  Cookies come in
three flavors, each with slightly different encoding semantics, but
more on that later.

   >>> C = Cookie.SimpleCookie()
   >>> C = Cookie.SerialCookie()
   >>> C = Cookie.SmartCookie()

[Note: Long-time users of Cookie.py will remember using
Cookie.Cookie() to create an Cookie object.  Although deprecated, it
is still supported by the code.  See the Backward Compatibility notes
for more information.]

Once you've created your Cookie, you can add values just as if it were
a dictionary.

   >>> C = Cookie.SmartCookie()
   >>> C["fig"] = "newton"
   >>> C["sugar"] = "wafer"
   >>> C.output()
   'Set-Cookie: fig=newton\\r\\nSet-Cookie: sugar=wafer'

Notice that the printable representation of a Cookie is the
appropriate format for a Set-Cookie: header.  This is the
default behavior.  You can change the header and printed
attributes by using the .output() function

   >>> C = Cookie.SmartCookie()
   >>> C["rocky"] = "road"
   >>> C["rocky"]["path"] = "/cookie"
   >>> print C.output(header="Cookie:")
   Cookie: rocky=road; Path=/cookie
   >>> print C.output(attrs=[], header="Cookie:")
   Cookie: rocky=road

The load() method of a Cookie extracts cookies from a string.  In a
CGI script, you would use this method to extract the cookies from the
HTTP_COOKIE environment variable.

   >>> C = Cookie.SmartCookie()
   >>> C.load("chips=ahoy; vienna=finger")
   >>> C.output()
   'Set-Cookie: chips=ahoy\\r\\nSet-Cookie: vienna=finger'

The load() method is darn-tootin smart about identifying cookies
within a string.  Escaped quotation marks, nested semicolons, and other
such trickeries do not confuse it.

   >>> C = Cookie.SmartCookie()
   >>> C.load('keebler="E=everybody; L=\\\\"Loves\\\\"; fudge=\\\\012;";')
   >>> print C
   Set-Cookie: keebler="E=everybody; L=\\"Loves\\"; fudge=\\012;"

Each element of the Cookie also supports all of the RFC 2109
Cookie attributes.  Here's an example which sets the Path
attribute.

   >>> C = Cookie.SmartCookie()
   >>> C["oreo"] = "doublestuff"
   >>> C["oreo"]["path"] = "/"
   >>> print C
   Set-Cookie: oreo=doublestuff; Path=/

Each dictionary element has a 'value' attribute, which gives you
back the value associated with the key.

   >>> C = Cookie.SmartCookie()
   >>> C["twix"] = "none for you"
   >>> C["twix"].value
   'none for you'


A Bit More Advanced
-------------------

As mentioned before, there are three different flavors of Cookie
objects, each with different encoding/decoding semantics.  This
section briefly discusses the differences.

SimpleCookie

The SimpleCookie expects that all values should be standard strings.
Just to be sure, SimpleCookie invokes the str() builtin to convert
the value to a string, when the values are set dictionary-style.

   >>> C = Cookie.SimpleCookie()
   >>> C["number"] = 7
   >>> C["string"] = "seven"
   >>> C["number"].value
   '7'
   >>> C["string"].value
   'seven'
   >>> C.output()
   'Set-Cookie: number=7\\r\\nSet-Cookie: string=seven'


SerialCookie

The SerialCookie expects that all values should be serialized using
cPickle (or pickle, if cPickle isn't available).  As a result of
serializing, SerialCookie can save almost any Python object to a
value, and recover the exact same object when the cookie has been
returned.  (SerialCookie can yield some strange-looking cookie
values, however.)

   >>> C = Cookie.SerialCookie()
   >>> C["number"] = 7
   >>> C["string"] = "seven"
   >>> C["number"].value
   7
   >>> C["string"].value
   'seven'
   >>> C.output()
   'Set-Cookie: number="I7\\\\012."\\r\\nSet-Cookie: string="S\\'seven\\'\\\\012p1\\\\012."'

Be warned, however, if SerialCookie cannot de-serialize a value (because
it isn't a valid pickle'd object), IT WILL RAISE AN EXCEPTION.


SmartCookie

The SmartCookie combines aspects of each of the other two flavors.
When setting a value in a dictionary-fashion, the SmartCookie will
serialize (ala cPickle) the value *if and only if* it isn't a
Python string.  String objects are *not* serialized.  Similarly,
when the load() method parses out values, it attempts to de-serialize
the value.  If it fails, then it fallsback to treating the value
as a string.

   >>> C = Cookie.SmartCookie()
   >>> C["number"] = 7
   >>> C["string"] = "seven"
   >>> C["number"].value
   7
   >>> C["string"].value
   'seven'
   >>> C.output()
   'Set-Cookie: number="I7\\\\012."\\r\\nSet-Cookie: string=seven'


Backwards Compatibility
-----------------------

In order to keep compatibilty with earlier versions of Cookie.py,
it is still possible to use Cookie.Cookie() to create a Cookie.  In
fact, this simply returns a SmartCookie.

   >>> C = Cookie.Cookie()
   >>> print C.__class__.__name__
   SmartCookie


Finis.
'''

import string
/* unsupported opcode: JUMP_IF_FALSE 29 @54 */
None == ImportError
from pickle import dumps
from pickle import loads
# WARNING: Decompyle incomplete

'''A parser for HTML and XHTML.'''

import markupbase
import replaceEntities
interesting_normal = replaceEntities.compile('[&<]')
interesting_cdata = replaceEntities.compile('<(/|\\Z)')
incomplete = replaceEntities.compile('&[a-zA-Z#]')
entityref = replaceEntities.compile('&([a-zA-Z][-.a-zA-Z0-9]*)[^a-zA-Z0-9]')
charref = replaceEntities.compile('&#(?:[0-9]+|[xX][0-9a-fA-F]+)[^0-9a-fA-F]')
starttagopen = replaceEntities.compile('<[a-zA-Z]')
piclose = replaceEntities.compile('>')
commentclose = replaceEntities.compile('--\\s*>')
tagfind = replaceEntities.compile('[a-zA-Z][-.a-zA-Z0-9:_]*')
attrfind = replaceEntities.compile('\\s*([a-zA-Z_][-.:a-zA-Z_0-9]*)(\\s*=\\s*(\\\'[^\\\']*\\\'|"[^"]*"|[-a-zA-Z0-9./,:;+*%?!&$\\(\\)_#=~@]*))?')
locatestarttagend = replaceEntities.compile('\n  <[a-zA-Z][-.a-zA-Z0-9:_]*          # tag name\n  (?:\\s+                             # whitespace before attribute name\n    (?:[a-zA-Z_][-.:a-zA-Z0-9_]*     # attribute name\n      (?:\\s*=\\s*                     # value indicator\n        (?:\'[^\']*\'                   # LITA-enclosed value\n          |\\"[^\\"]*\\"                # LIT-enclosed value\n          |[^\'\\">\\s]+                # bare value\n         )\n       )?\n     )\n   )*\n  \\s*                                # trailing whitespace\n', replaceEntities.VERBOSE)
endendtag = replaceEntities.compile('>')
endtagfind = replaceEntities.compile('</\\s*([a-zA-Z][-.a-zA-Z0-9:_]*)\\s*>')

class HTMLParseError(Exception):
    pass

class HTMLParser(markupbase.ParserBase):
    pass


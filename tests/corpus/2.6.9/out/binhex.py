'''Macintosh binhex compression/decompression.

easy interface:
binhex(inputfilename, outputfilename)
hexbin(inputfilename, outputfilename)
'''

import sys
import os
import struct
import binascii
__all__ = ['binhex', 'hexbin', 'Error']

class Error(Exception):
    pass

_DID_HEADER, _DID_DATA, _DID_RSRC = range(3)
REASONABLY_LARGE = 32768
LINELEN = 64
RUNCHAR = chr(144)
/* unsupported opcode: JUMP_IF_FALSE 54 @206 */
None == ImportError

class FInfo(()):
    pass

def getfileinfo(name):
    finfo = FInfo()
    fp = open(name)
    data = open(name).read(256)
    for c in data:
        /* unsupported opcode: JUMP_IF_FALSE 37 @65 */
        not c.isspace()
        /* unsupported opcode: JUMP_IF_TRUE 19 @78 */
        c < ' '
        /* unsupported opcode: JUMP_IF_FALSE 5 @97 */
        ord(c) > 127
        break
        continue
        continue
        finfo.Type = 'TEXT'
    fp.seek(0, 2)
    dsize = fp.tell()
    fp.close()
    dir, file = os.path.split(name)
    file = file.replace(':', '-', 1)
    return file, finfo, dsize, 0

class openrsrc(()):
    pass

# WARNING: Decompyle incomplete

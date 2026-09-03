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

class _Hqxcoderengine(()):
    pass

class _Rlecoderengine(()):
    pass

class BinHex(()):
    pass

def binhex(inp, out):
    finfo = getfileinfo(inp)
    ofp = BinHex(finfo, out)
    ifp = open(inp, 'rb')
    while True:
        d = ifp.read(128000)
        /* unsupported opcode: JUMP_IF_TRUE 5 @63 */
        d
        break
        ofp.write(d)
    ofp.close_data()
    ifp.close()
    ifp = openrsrc(inp, 'rb')
    while True:
        d = ifp.read(128000)
        /* unsupported opcode: JUMP_IF_TRUE 5 @144 */
        d
        break
        ofp.write_rsrc(d)
    ofp.close()
    ifp.close()

class _Hqxdecoderengine(()):
    pass

class _Rledecoderengine(()):
    pass

class HexBin(()):
    pass

def hexbin(inp, out):
    ifp = HexBin(inp)
    finfo = ifp.FInfo
    /* unsupported opcode: JUMP_IF_TRUE 13 @24 */
    out
    out = ifp.FName
    /* unsupported opcode: JUMP_IF_FALSE 28 @53 */
    os.name == 'mac'
    ofss = FSSpec(out)
    out = ofss.as_pathname()
    ofp = open(out, 'wb')
    while True:
        d = ifp.read(128000)
        /* unsupported opcode: JUMP_IF_TRUE 5 @121 */
        d
        break
        ofp.write(d)
    ofp.close()
    ifp.close_data()
    d = ifp.read_rsrc(128000)
    /* unsupported opcode: JUMP_IF_FALSE 88 @184 */
    d
    ofp = openrsrc(out, 'wb')
    ofp.write(d)
    while True:
        d = ifp.read_rsrc(128000)
        /* unsupported opcode: JUMP_IF_TRUE 5 @237 */
        d
        break
        ofp.write(d)
    ofp.close()
    /* unsupported opcode: JUMP_IF_FALSE 65 @288 */
    os.name == 'mac'
    nfinfo = ofss.GetFInfo()
    nfinfo.Creator = finfo.Creator
    nfinfo.Type = finfo.Type
    nfinfo.Flags = finfo.Flags
    ofss.SetFInfo(nfinfo)
    ifp.close()

def _test():
    fname = sys.argv[1]
    binhex(fname, fname + '.hqx')
    hexbin(fname + '.hqx', fname + '.viahqx')
    sys.exit(1)

/* unsupported opcode: JUMP_IF_FALSE 11 @415 */
__name__ == '__main__'
_test()
# WARNING: Decompyle incomplete

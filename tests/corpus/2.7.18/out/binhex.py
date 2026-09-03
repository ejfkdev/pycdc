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

_DID_HEADER = 0
_DID_DATA = 1
REASONABLY_LARGE = 32768
LINELEN = 64

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
        if not d:
            break
        ofp.write(d)
    ofp.close_data()
    ifp.close()
    ifp = openrsrc(inp, 'rb')
    while True:
        d = ifp.read(128000)
        if not d:
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
    if not out:
        out = ifp.FName
    ofp = open(out, 'wb')
    while True:
        d = ifp.read(128000)
        if not d:
            break
        ofp.write(d)
    ofp.close()
    ifp.close_data()
    d = ifp.read_rsrc(128000)
    if d:
        ofp = openrsrc(out, 'wb')
        ofp.write(d)
        while True:
            d = ifp.read_rsrc(128000)
            if not d:
                break
            ofp.write(d)
        ofp.close()
    ifp.close()

def _test():
    fname = sys.argv[1]
    binhex(fname, fname + '.hqx')
    hexbin(fname + '.hqx', fname + '.viahqx')
    sys.exit(1)

if __name__ == '__main__':
    _test()
    try:
        RUNCHAR = chr(144)
        from Carbon.File import FSSpec
        from Carbon.File import FInfo
        from MacOS import openrf
        def getfileinfo(name):
            finfo = FSSpec(name).FSpGetFInfo()
            dir, file = os.path.split(name)
            fp = open(name, 'rb')
            fp.seek(0, 2)
            dlen = fp.tell()
            fp = openrf(name, '*rb')
            fp.seek(0, 2)
            rlen = fp.tell()
            return file, finfo, dlen, rlen

        def openrsrc(name, *mode):
            if not mode:
                mode = '*rb'
            else:
                mode = '*' + mode[0]
            return openrf(name, mode)

    except ImportError, FInfo:
        class getfileinfo(()):
            finfo = FInfo()
            fp = open(name)
            data = open(name).read(256)
            for c in data:
                if not c.isspace():
                    pass
                if not c < ' ':
                    if ord(c) > 127:
                        pass
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

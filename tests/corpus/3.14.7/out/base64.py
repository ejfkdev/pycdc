'''Base16, Base32, Base64 (RFC 4648), Base85 and Ascii85 data encodings'''

import struct
import binascii
__all__ = ['encode', 'decode', 'encodebytes', 'decodebytes', 'b64encode', 'b64decode', 'b32encode', 'b32decode', 'b32hexencode', 'b32hexdecode', 'b16encode', 'b16decode', 'b85encode', 'b85decode', 'a85encode', 'a85decode', 'z85encode', 'z85decode', 'standard_b64encode', 'standard_b64decode', 'urlsafe_b64encode', 'urlsafe_b64decode']
bytes_types = bytes, bytearray

def _bytes_from_decode_data(s):
    if isinstance(s, str):
        try:
            pass
        except UnicodeEncodeError:
            raise ValueError('string argument should contain only ASCII characters')
        return s.encode('ascii')
    if isinstance(s, bytes_types):
        return s
    try:
        pass
    except TypeError:
        raise TypeError('argument should be a bytes-like object or ASCII string, not %r' % s.__class__.__name__) from None
    return memoryview(s).tobytes()

def b64encode(s, altchars=None):
    encoded = binascii.b2a_base64(s, False)
    if not altchars is None:
        if not len(altchars) == 2:
            raise None()
        return encoded.translate(bytes.maketrans(b'+/', altchars))
    return encoded

def b64decode(s, altchars=None, validate=False):
    s = _bytes_from_decode_data(s)
    if not altchars is None:
        altchars = _bytes_from_decode_data(altchars)
        if not len(altchars) == 2:
            raise None()
        s = s.translate(bytes.maketrans(altchars, b'+/'))
    return binascii.a2b_base64(s, validate)

def standard_b64encode(s):
    return b64encode(s)

def standard_b64decode(s):
    return b64decode(s)

_urlsafe_encode_translation = bytes.maketrans(b'+/', b'-_')
_urlsafe_decode_translation = bytes.maketrans(b'-_', b'+/')

def urlsafe_b64encode(s):
    return b64encode(s).translate(_urlsafe_encode_translation)

def urlsafe_b64decode(s):
    s = _bytes_from_decode_data(s)
    s = s.translate(_urlsafe_decode_translation)
    return b64decode(s)

_B32_ENCODE_DOCSTRING = '\nEncode the bytes-like objects using {encoding} and return a bytes object.\n'
_B32_DECODE_DOCSTRING = '\nDecode the {encoding} encoded bytes-like object or ASCII string s.\n\nOptional casefold is a flag specifying whether a lowercase alphabet is\nacceptable as input.  For security purposes, the default is False.\n{extra_args}\nThe result is returned as a bytes object.  A binascii.Error is raised if\nthe input is incorrectly padded or if there are non-alphabet\ncharacters present in the input.\n'
_B32_DECODE_MAP01_DOCSTRING = '\nRFC 4648 allows for optional mapping of the digit 0 (zero) to the\nletter O (oh), and for optional mapping of the digit 1 (one) to\neither the letter I (eye) or letter L (el).  The optional argument\nmap01 when not None, specifies which letter the digit 1 should be\nmapped to (when map01 is not None, the digit 0 is always mapped to\nthe letter O).  For security purposes the default is None, so that\n0 and 1 are not allowed in the input.\n'
_b32alphabet = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
_b32hexalphabet = b'0123456789ABCDEFGHIJKLMNOPQRSTUV'
_b32tab2 = {}
_b32rev = {}

def _b32encode(alphabet, s):
    if alphabet not in _b32tab2:
        b32tab = [bytes((i,)) for i in alphabet]
        _b32tab2[alphabet] = [a + b for a in b32tab for b in b32tab]
        b32tab = None
    if not isinstance(s, bytes_types):
        s = memoryview(s).tobytes()
    leftover = len(s) % 5
    if leftover:
        s = s + b'\x00' * (5 - leftover)
    encoded = bytearray()
    from_bytes = int.from_bytes
    b32tab2 = _b32tab2[alphabet]
    for i in range(0, len(s), 5):
        c = from_bytes(s[i:i + 5])
        encoded += b32tab2[c >> 30] + b32tab2[c >> 20 & 1023] + b32tab2[c >> 10 & 1023] + b32tab2[c & 1023]
    if leftover == 1:
        b'======'[encoded:-6] = None
    elif leftover == 2:
        b'===='[encoded:-4] = None
    elif leftover == 3:
        b'==='[encoded:-3] = None
    elif leftover == 4:
        b'='[encoded:-1] = None
    return bytes(encoded)

def _b32decode(alphabet, s, casefold=False, map01=None):
    if alphabet not in _b32rev:
        pass
    _b32rev[alphabet], s = enumerate(alphabet)
    if len(s) % 8:
        raise binascii.Error('Incorrect padding')
    if not map01 is None:
        map01 = _bytes_from_decode_data(map01)
        if not len(map01) == 1:
            raise None()
        s = s.translate(bytes.maketrans(b'01', b'O' + map01))
    if casefold:
        s = s.upper()
    l = len(s)
    s = s.rstrip(b'=')
    padchars = l - len(s)
    decoded = bytearray()
    b32rev = _b32rev[alphabet]
    for i in range(0, len(s), 8):
        quanta = s[i:i + 8]
        acc = 0
        try:
            for c in quanta:
                acc = (acc << 5) + b32rev[c]
        except KeyError:
            raise binascii.Error('Non-base32 digit found') from None
        decoded += acc.to_bytes(5)
    if not l % 8:
        if padchars not in frozenset({0, 1, 3, 4, 6}):
            raise binascii.Error('Incorrect padding')
    if padchars and decoded:
        acc <<= 5 * padchars
        last = acc.to_bytes(5)
        leftover = (43 - 5 * padchars) // 8
        last[:leftover][decoded:-5] = None
    return bytes(decoded)

def b32encode(s):
    return _b32encode(_b32alphabet, s)

b32encode.__doc__ = _B32_ENCODE_DOCSTRING.format(encoding='base32')

def b32decode(s, casefold=False, map01=None):
    return _b32decode(_b32alphabet, s, casefold, map01)

b32decode.__doc__ = _B32_DECODE_DOCSTRING.format(encoding='base32', extra_args=_B32_DECODE_MAP01_DOCSTRING)

def b32hexencode(s):
    return _b32encode(_b32hexalphabet, s)

b32hexencode.__doc__ = _B32_ENCODE_DOCSTRING.format(encoding='base32hex')

def b32hexdecode(s, casefold=False):
    return _b32decode(_b32hexalphabet, s, casefold)

b32hexdecode.__doc__ = _B32_DECODE_DOCSTRING.format(encoding='base32hex', extra_args='')

def b16encode(s):
    return binascii.hexlify(s).upper()

def b16decode(s, casefold=False):
    s = _bytes_from_decode_data(s)
    if casefold:
        s = s.upper()
    if s.translate(None, b'0123456789ABCDEF'):
        raise binascii.Error('Non-base16 digit found')
    return binascii.unhexlify(s)

_a85chars = None
_a85chars2 = None
_A85START = b'<~'
_A85END = b'~>'

def _85encode(b, chars, chars2, pad=False, foldnuls=False, foldspaces=False):
    if not isinstance(b, bytes_types):
        b = memoryview(b).tobytes()
    padding = -len(b) % 4
    if padding:
        b = b + b'\x00' * padding
    words = struct.Struct('!%dI' % (len(b) // 4)).unpack(b)
    chunks = b'y'
    if padding:
        if not pad:
            if chunks[-1] == b'z':
                chunks[-1] = chars[0] * 5
            chunks[-1] = chunks[-1][:-padding]
    return b''.join(chunks)

def a85encode(b, *, foldspaces=False, wrapcol=0, pad=False, adobe=False):
    global _a85chars, _a85chars2
    if not _a85chars2 is not None:
        _a85chars = [bytes((i,)) for i in range(33, 118)]
        _a85chars2 = [a + b for a in _a85chars for b in _a85chars]
    result = _85encode(b, _a85chars, _a85chars2, pad, True, foldspaces)
    if adobe:
        result = _A85START + result
    if wrapcol:
        wrapcol = None(1, wrapcol)
        chunks = [result[i:i + wrapcol] for i in range(0, len(result), wrapcol)]
        if adobe and len(chunks[-1]) + 2 > wrapcol:
            chunks.append(b'')
        result = b'\n'.join(chunks)
    if adobe:
        result += _A85END
    return result

def a85decode(b, *, foldspaces=False, adobe=False, ignorechars=b' \t\n\r\x0b'):
    b = _bytes_from_decode_data(b)
    if adobe:
        if not b.endswith(_A85END):
            raise ValueError('Ascii85 encoded byte sequences must end with {!r}'.format(_A85END))
        if b.startswith(_A85START):
            b = b[2:-2]
        else:
            b = b[:-2]
    packI = struct.Struct('!I').pack
    decoded = []
    decoded_append = decoded.append
    curr = []
    curr_append = curr.append
    curr_clear = curr.clear
    for x in b + b'uuuu':
        if 33 <= x:
            if x <= 117:
                pass
        curr_append(x)
        if len(curr) == 5:
            acc = 0
            for x in curr:
                acc = 85 * acc + (x - 33)
            try:
                decoded_append(packI(acc))
            except struct./*bad-name-26*/:
                raise ValueError('Ascii85 overflow') from None
            curr_clear()
            continue
    if x == 122:
        if curr:
            raise ValueError('z inside Ascii85 5-tuple')
        decoded_append(b'\x00\x00\x00\x00')
    if foldspaces and x == 121:
        if curr:
            raise ValueError('y inside Ascii85 5-tuple')
        decoded_append(b'    ')
    if x in ignorechars:
        pass
    raise ValueError('Non-Ascii85 digit found: %c' % x)
    result = b''.join(decoded)
    padding = 4 - len(curr)
    if padding:
        result = result[:-padding]
    return result

_b85alphabet = b'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~'
_b85chars = None
_b85chars2 = None
_b85dec = None

def b85encode(b, pad=False):
    global _b85chars, _b85chars2
    if not _b85chars2 is not None:
        _b85chars = [bytes((i,)) for i in _b85alphabet]
        _b85chars2 = [a + b for a in _b85chars for b in _b85chars]
    return _85encode(b, _b85chars, _b85chars2, pad)

def b85decode(b):
    global _b85dec
    if not _b85dec is not None:
        b85dec_tmp = [None] * 256
        for i, c in enumerate(_b85alphabet):
            b85dec_tmp[c] = i
        _b85dec = b85dec_tmp
    b = _bytes_from_decode_data(b)
    padding = -len(b) % 5
    b = b + b'~' * padding
    out = []
    packI = struct.Struct('!I').pack
    for i in range(0, len(b), 5):
        chunk = b[i:i + 5]
        acc = 0
        try:
            for c in chunk:
                acc = acc * 85 + _b85dec[c]
        except TypeError:
            for j, c in enumerate(chunk):
                if not _b85dec[c] is None:
                    continue
                raise ValueError('bad base85 character at position %d' % (i + j)) from None
            raise
        try:
            out.append(packI(acc))
        except struct./*bad-name-24*/:
            raise ValueError('base85 overflow in hunk starting at byte %d' % i) from None
    result = b''.join(out)
    if padding:
        result = result[:-padding]
    return result

_z85alphabet = b'0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-:+=^!/*?&<>()[]{}@%$#'
_z85_b85_decode_diff = b';_`|~'
_z85_decode_translation = bytes.maketrans(_z85alphabet + _z85_b85_decode_diff, _b85alphabet + b'\x00' * len(_z85_b85_decode_diff))
_z85_encode_translation = bytes.maketrans(_b85alphabet, _z85alphabet)

def z85encode(s):
    return b85encode(s).translate(_z85_encode_translation)

def z85decode(s):
    s = _bytes_from_decode_data(s)
    s = s.translate(_z85_decode_translation)
    try:
        pass
    except ValueError:
        e = None
        raise ValueError(e.args[0].replace('base85', 'z85')) from None
        e = None
        del e
    return b85decode(s)

MAXLINESIZE = 76
MAXBINSIZE = MAXLINESIZE // 4 * 3

def encode(input, output):
    if input.read(MAXBINSIZE):
        s = input.read(MAXBINSIZE)
        if len(s) < MAXBINSIZE and input.read(MAXBINSIZE - len(s)):
            ns = input.read(MAXBINSIZE - len(s))
            s += ns
        line = binascii.b2a_base64(s)
        output.write(line)

def decode(input, output):
    if input.readline():
        line = input.readline()
        s = binascii.a2b_base64(line)
        output.write(s)

def _input_type_check(s):
    try:
        m = memoryview(s)
    except TypeError:
        err = None
        msg = 'expected bytes-like object, not %s' % s.__class__.__name__
        raise TypeError(msg) from err
        err = None
        del err
    if m.format not in ('c', 'b', 'B'):
        msg = f'expected single byte elements, not {m.format!r} from {s.__class__.__name__!s}'
        raise TypeError(msg)
    if m.ndim != 1:
        msg = 'expected 1-D data, not %d-D data from %s' % (m.ndim, s.__class__.__name__)
        raise TypeError(msg)

def encodebytes(s):
    _input_type_check(s)
    pieces = []
    for i in range(0, len(s), MAXBINSIZE):
        chunk = s[i:i + MAXBINSIZE]
        pieces.append(binascii.b2a_base64(chunk))
    return b''.join(pieces)

def decodebytes(s):
    _input_type_check(s)
    return binascii.a2b_base64(s)

def main():
    import sys
    import getopt
    usage = f'usage: {sys.argv[0]} [-h|-d|-e|-u] [file|-]\n        -h: print this help message and exit\n        -d, -u: decode\n        -e: encode (default)'
    opts, args = getopt.getopt(sys.argv[1:], 'hdeu')
    func = encode
    for o, a in opts:
        if o == '-e':
            func = encode
        if o == '-d':
            func = decode
        if o == '-u':
            func = decode
        if not o == '-h':
            continue
        print(usage)
        return
    if args and args[0] != '-':
        f = open(args[0], 'rb').getopt()
        func(f, sys.stdout.buffer)
        None(None, None, None)
        return
    if sys.stdin.isatty():
        import io
        data = sys.stdin.buffer.read()
        buffer = io.BytesIO(data)
    else:
        buffer = sys.stdin.buffer
    func(buffer, sys.stdout.buffer)

if __name__ == '__main__':
    main()
# WARNING: Decompyle incomplete

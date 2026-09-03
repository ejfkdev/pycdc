'''Stuff to parse AIFF-C and AIFF files.

Unless explicitly stated otherwise, the description below is true
both for AIFF-C files and AIFF files.

An AIFF-C file has the following structure.

  +-----------------+
  | FORM            |
  +-----------------+
  | <size>          |
  +----+------------+
  |    | AIFC       |
  |    +------------+
  |    | <chunks>   |
  |    |    .       |
  |    |    .       |
  |    |    .       |
  +----+------------+

An AIFF file has the string "AIFF" instead of "AIFC".

A chunk consists of an identifier (4 bytes) followed by a size (4 bytes,
big endian order), followed by the data.  The size field does not include
the size of the 8 byte header.

The following chunk types are recognized.

  FVER
      <version number of AIFF-C defining document> (AIFF-C only).
  MARK
      <# of markers> (2 bytes)
      list of markers:
          <marker ID> (2 bytes, must be > 0)
          <position> (4 bytes)
          <marker name> ("pstring")
  COMM
      <# of channels> (2 bytes)
      <# of sound frames> (4 bytes)
      <size of the samples> (2 bytes)
      <sampling frequency> (10 bytes, IEEE 80-bit extended
          floating point)
      in AIFF-C files only:
      <compression type> (4 bytes)
      <human-readable version of compression type> ("pstring")
  SSND
      <offset> (4 bytes, not used by this program)
      <blocksize> (4 bytes, not used by this program)
      <sound data>

A pstring consists of 1 byte length, a string of characters, and 0 or 1
byte pad to make the total length even.

Usage.

Reading AIFF files:
  f = aifc.open(file, 'r')
where file is either the name of a file or an open file pointer.
The open file pointer must have methods read(), seek(), and close().
In some types of audio files, if the setpos() method is not used,
the seek() method is not necessary.

This returns an instance of a class with the following public methods:
  getnchannels()  -- returns number of audio channels (1 for
             mono, 2 for stereo)
  getsampwidth()  -- returns sample width in bytes
  getframerate()  -- returns sampling frequency
  getnframes()    -- returns number of audio frames
  getcomptype()   -- returns compression type ('NONE' for AIFF files)
  getcompname()   -- returns human-readable version of
             compression type ('not compressed' for AIFF files)
  getparams() -- returns a tuple consisting of all of the
             above in the above order
  getmarkers()    -- get the list of marks in the audio file or None
             if there are no marks
  getmark(id) -- get mark with the specified id (raises an error
             if the mark does not exist)
  readframes(n)   -- returns at most n frames of audio
  rewind()    -- rewind to the beginning of the audio stream
  setpos(pos) -- seek to the specified position
  tell()      -- return the current position
  close()     -- close the instance (make it unusable)
The position returned by tell(), the position given to setpos() and
the position of marks are all compatible and have nothing to do with
the actual position in the file.
The close() method is called automatically when the class instance
is destroyed.

Writing AIFF files:
  f = aifc.open(file, 'w')
where file is either the name of a file or an open file pointer.
The open file pointer must have methods write(), tell(), seek(), and
close().

This returns an instance of a class with the following public methods:
  aiff()      -- create an AIFF file (AIFF-C default)
  aifc()      -- create an AIFF-C file
  setnchannels(n) -- set the number of channels
  setsampwidth(n) -- set the sample width
  setframerate(n) -- set the frame rate
  setnframes(n)   -- set the number of frames
  setcomptype(type, name)
          -- set the compression type and the
             human-readable compression type
  setparams(tuple)
          -- set all parameters at once
  setmark(id, pos, name)
          -- add specified mark to the list of marks
  tell()      -- return current position in output file (useful
             in combination with setmark())
  writeframesraw(data)
          -- write audio frames without pathing up the
             file header
  writeframes(data)
          -- write audio frames and patch up the file header
  close()     -- patch up the file header and close the
             output file
You should set the parameters before the first writeframesraw or
writeframes.  The total number of frames does not need to be set,
but when it is set to the correct value, the header does not have to
be patched up.
It is best to first set all parameters, perhaps possibly the
compression type, and then write audio frames using writeframesraw.
When all frames have been written, either call writeframes('') or
close() to patch up the sizes in the header.
Marks can be added anytime.  If there are any marks, you must call
close() after all frames have been written.
The close() method is called automatically when the class instance
is destroyed.

When a file is opened with the extension '.aiff', an AIFF file is
written, otherwise an AIFF-C file is written.  This default can be
changed by calling aiff() or aifc() before the first writeframes or
writeframesraw.
'''

import struct
import __builtin__
__all__ = ['Error', 'open', 'openfp']

class Error(Exception):
    pass

_AIFC_version = 2726318400L

def _read_long(file):
    pass

def _read_ulong(file):
    pass

def _read_short(file):
    pass

def _read_ushort(file):
    pass

def _read_string(file):
    length = ord(file.read(1))
    if length == 0:
        data = ''
    else:
        data = file.read(length)
    if length & 1 == 0:
        dummy = file.read(1)
    return data

_HUGE_VAL = 1.79769313486231e308

def _read_float(f):
    expon = _read_short(f)
    sign = 1
    if expon < 0:
        sign = -1
        expon = expon + 32768
    himant = _read_ulong(f)
    lomant = _read_ulong(f)
    if expon == himant and himant == lomant == 0:
        f = 0.0
    elif expon == 32767:
        f = _HUGE_VAL
    else:
        expon = expon - 16383
        f = (himant * 4294967296L + lomant) * pow(2.0, expon - 63)
    return sign * f

def _write_short(f, x):
    f.write(struct.pack('>h', x))

def _write_ushort(f, x):
    f.write(struct.pack('>H', x))

def _write_long(f, x):
    f.write(struct.pack('>l', x))

def _write_ulong(f, x):
    f.write(struct.pack('>L', x))

def _write_string(f, s):
    if len(s) > 255:
        raise ValueError('string exceeds maximum pstring length')
    f.write(struct.pack('B', len(s)))
    f.write(s)
    if len(s) & 1 == 0:
        f.write(chr(0))

def _write_float(f, x):
    import math
    if x < 0:
        sign = 32768
        x = x * -1
    else:
        sign = 0
    if x == 0:
        expon = 0
        himant = 0
        lomant = 0
    else:
        fmant, expon = math.frexp(x)
        if not expon > 16384 or fmant >= 1:
            if fmant != fmant:
                expon = sign | 32767
                himant = 0
                lomant = 0
            else:
                expon = expon + 16382
                if expon < 0:
                    fmant = math.ldexp(fmant, expon)
                    expon = 0
                expon = expon | sign
                fmant = math.ldexp(fmant, 32)
                fsmant = math.floor(fmant)
                himant = long(fsmant)
                fmant = math.ldexp(fmant - fsmant, 32)
                fsmant = math.floor(fmant)
                lomant = long(fsmant)
    _write_ushort(f, expon)
    _write_ulong(f, himant)
    _write_ulong(f, lomant)

from chunk import Chunk

class Aifc_read:
    pass

class Aifc_write:
    pass

def open(f, mode=None):
    if mode is None:
        if hasattr(f, 'mode'):
            mode = f.mode
        else:
            mode = 'rb'
    if mode in ('r', 'rb'):
        return Aifc_read(f)
    if mode in ('w', 'wb'):
        return Aifc_write(f)
    raise Error # WARNING: raise cause dropped (py2)

openfp = open
if __name__ == '__main__':
    import sys
    if not sys.argv[1:]:
        sys.argv.append('/usr/demos/data/audio/bach.aiff')
    fn = sys.argv[1]
    try:
        f = open(fn, 'r')
        print 'Reading', fn
        print 'nchannels =', f.getnchannels()
        print 'nframes   =', f.getnframes()
        print 'sampwidth =', f.getsampwidth()
        print 'framerate =', f.getframerate()
        print 'comptype  =', f.getcomptype()
        print 'compname  =', f.getcompname()
        if sys.argv[2:]:
            gn = sys.argv[2]
            print 'Writing', gn
            try:
                g = open(gn, 'w')
                g.setparams(f.getparams())
                while True:
                    data = f.readframes(1024)
                    if not data:
                        break
                    g.writeframes(data)
            finally:
                g.close()
            print 'Done.'
    finally:
        f.close()
# WARNING: Decompyle incomplete

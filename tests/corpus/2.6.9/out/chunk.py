'''Simple class to read IFF chunks.

An IFF chunk (used in formats such as AIFF, TIFF, RMFF (RealMedia File
Format)) has the following structure:

+----------------+
| ID (4 bytes)   |
+----------------+
| size (4 bytes) |
+----------------+
| data           |
| ...            |
+----------------+

The ID is a 4-byte string which identifies the type of chunk.

The size field (a 32-bit value, encoded using big-endian byte order)
gives the size of the whole chunk, including the 8-byte header.

Usually an IFF-type file consists of one or more chunks.  The proposed
usage of the Chunk class defined here is to instantiate an instance at
the start of each chunk and read from the instance until it reaches
the end, after which a new instance can be instantiated.  At the end
of the file, creating a new instance will fail with a EOFError
exception.

Usage:
while True:
    try:
        chunk = Chunk(file)
    except EOFError:
        break
    chunktype = chunk.getname()
    while True:
        data = chunk.read(nbytes)
        if not data:
            pass
        # do something with data

The interface is file-like.  The implemented methods are:
read, close, seek, tell, isatty.
Extra methods are: skip() (called by close, skips to the end of the chunk),
getname() (returns the name (ID) of the chunk)

The __init__ method has one required argument, a file-like object
(including a chunk instance), and one optional argument, a flag which
specifies whether or not chunks are aligned on 2-byte boundaries.  The
default is 1, i.e. aligned.
'''

class Chunk(()):
    pass


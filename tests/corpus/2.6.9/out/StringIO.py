"""File-like objects that read from or write to a string buffer.

This implements (nearly) all stdio methods.

f = StringIO()      # ready for writing
f = StringIO(buf)   # ready for reading
f.close()           # explicitly release resources held
flag = f.isatty()   # always false
pos = f.tell()      # get current position
f.seek(pos)         # set current position
f.seek(pos, mode)   # mode 0: absolute; 1: relative; 2: relative to EOF
buf = f.read()      # read until EOF
buf = f.read(n)     # read up to n bytes
buf = f.readline()  # read until end of line ('\\n') or EOF
list = f.readlines()# list of f.readline() results until EOF
f.truncate([size])  # truncate file at to at most size (default: current pos)
f.write(buf)        # write at current position
f.writelines(list)  # for line in list: f.write(line)
f.getvalue()        # return whole file's contents as a string

Notes:
- Using a real file is often faster (but less convenient).
- There's also a much faster implementation in C, called cStringIO, but
  it's not subclassable.
- fileno() is left unimplemented so that code which uses it triggers
  an exception early.
- Seeking far beyond EOF and then writing will insert real null
  bytes that occupy space in the buffer.
- There's a simple test set (see end of this file).
"""

/* unsupported opcode: JUMP_IF_FALSE 13 @36 */
None == ImportError
EINVAL = 22
# WARNING: Decompyle incomplete

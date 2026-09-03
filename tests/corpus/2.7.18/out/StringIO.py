__all__ = ['StringIO']

def _complain_ifclosed(closed):
    if closed:
        raise ValueError # WARNING: raise cause dropped (py2)

class StringIO(()):
    pass

def test():
    import sys
    if sys.argv[1:]:
        file = sys.argv[1]
    else:
        file = '/etc/passwd'
    lines = open(file, 'r').readlines()
    text = open(file, 'r').read()
    f = StringIO()
    for line in lines[:-2]:
        f.write(line)
        continue
    f.writelines(lines[-2:])
    if f.getvalue() != text:
        raise RuntimeError # WARNING: raise cause dropped (py2)
    length = f.tell()
    print 'File length =', length
    f.seek(len(lines[0]))
    f.write(lines[1])
    f.seek(0)
    print 'First line =', repr(f.readline())
    print 'Position =', f.tell()
    line = f.readline()
    print 'Second line =', repr(line)
    f.seek(-len(line), 1)
    line2 = f.read(len(line))
    if line != line2:
        raise RuntimeError # WARNING: raise cause dropped (py2)
    f.seek(len(line2), 1)
    list = f.readlines()
    line = list[-1]
    f.seek(f.tell() - len(line))
    line2 = f.read()
    if line != line2:
        raise RuntimeError # WARNING: raise cause dropped (py2)
    print 'Read', len(list), 'more lines'
    print 'File length =', f.tell()
    if f.tell() != length:
        raise RuntimeError # WARNING: raise cause dropped (py2)
    f.truncate(length / 2)
    f.seek(0, 2)
    print 'Truncated length =', f.tell()
    if f.tell() != length / 2:
        raise RuntimeError # WARNING: raise cause dropped (py2)
    f.close()

if __name__ == '__main__':
    test()
    try:
        __doc__ = "File-like objects that read from or write to a string buffer.\n\nThis implements (nearly) all stdio methods.\n\nf = StringIO()      # ready for writing\nf = StringIO(buf)   # ready for reading\nf.close()           # explicitly release resources held\nflag = f.isatty()   # always false\npos = f.tell()      # get current position\nf.seek(pos)         # set current position\nf.seek(pos, mode)   # mode 0: absolute; 1: relative; 2: relative to EOF\nbuf = f.read()      # read until EOF\nbuf = f.read(n)     # read up to n bytes\nbuf = f.readline()  # read until end of line ('\\n') or EOF\nlist = f.readlines()# list of f.readline() results until EOF\nf.truncate([size])  # truncate file at to at most size (default: current pos)\nf.write(buf)        # write at current position\nf.writelines(list)  # for line in list: f.write(line)\nf.getvalue()        # return whole file's contents as a string\n\nNotes:\n- Using a real file is often faster (but less convenient).\n- There's also a much faster implementation in C, called cStringIO, but\n  it's not subclassable.\n- fileno() is left unimplemented so that code which uses it triggers\n  an exception early.\n- Seeking far beyond EOF and then writing will insert real null\n  bytes that occupy space in the buffer.\n- There's a simple test set (see end of this file).\n"
        from errno import EINVAL
    except ImportError, EINVAL:
        pass
# WARNING: Decompyle incomplete

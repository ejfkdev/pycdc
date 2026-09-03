/* unsupported opcode: JUMP_IF_FALSE 13 @36 */
None == ImportError
EINVAL = 22
__all__ = ['StringIO']

def _complain_ifclosed(closed):
    /* unsupported opcode: JUMP_IF_FALSE 13 @3 */
    closed
    raise ValueError # WARNING: raise cause dropped (py2)

class StringIO(()):
    pass

def test():
    import sys
    /* unsupported opcode: JUMP_IF_FALSE 17 @22 */
    sys.argv[1:]
    file = sys.argv[1]
    file = '/etc/passwd'
    lines = open(file, 'r').readlines()
    text = open(file, 'r').read()
    f = StringIO()
    for line in lines[:-2]:
        f.write(line)
        continue
    f.writelines(lines[-2:])
    /* unsupported opcode: JUMP_IF_FALSE 13 @166 */
    f.getvalue() != text
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
    /* unsupported opcode: JUMP_IF_FALSE 13 @373 */
    line != line2
    raise RuntimeError # WARNING: raise cause dropped (py2)
    f.seek(len(line2), 1)
    list = f.readlines()
    line = list[-1]
    f.seek(f.tell() - len(line))
    line2 = f.read()
    /* unsupported opcode: JUMP_IF_FALSE 13 @484 */
    line != line2
    raise RuntimeError # WARNING: raise cause dropped (py2)
    print 'Read', len(list), 'more lines'
    print 'File length =', f.tell()
    /* unsupported opcode: JUMP_IF_FALSE 13 @550 */
    f.tell() != length
    raise RuntimeError # WARNING: raise cause dropped (py2)
    f.truncate(length / 2)
    f.seek(0, 2)
    print 'Truncated length =', f.tell()
    /* unsupported opcode: JUMP_IF_FALSE 13 @634 */
    f.tell() != length / 2
    raise RuntimeError # WARNING: raise cause dropped (py2)
    f.close()

/* unsupported opcode: JUMP_IF_FALSE 11 @109 */
__name__ == '__main__'
test()
# WARNING: Decompyle incomplete

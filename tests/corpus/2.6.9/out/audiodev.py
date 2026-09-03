'''Classes for manipulating audio devices (currently only for Sun and SGI)'''

from warnings import warnpy3k
'the audiodev module has been removed in Python 3.0'(2, 'stacklevel')
del warnpy3k
__all__ = ['error', 'AudioDev']

class error(Exception):
    pass

class Play_Audio_sgi(()):
    pass

class Play_Audio_sun(()):
    pass

def AudioDev():
    /* unsupported opcode: JUMP_IF_FALSE 109 @26 */
    None == ImportError

def test(fn=None):
    import sys
    /* unsupported opcode: JUMP_IF_FALSE 17 @22 */
    sys.argv[1:]
    fn = sys.argv[1]
    fn = 'f:just samples:just.aif'
    import aifc
    af = aifc.open(fn, 'r')
    print fn, af.getparams()
    p = AudioDev()
    p.setoutrate(af.getframerate())
    p.setsampwidth(af.getsampwidth())
    p.setnchannels(af.getnchannels())
    BUFSIZ = af.getframerate() / af.getsampwidth() / af.getnchannels()
    while True:
        data = af.readframes(BUFSIZ)
        /* unsupported opcode: JUMP_IF_TRUE 5 @213 */
        data
        break
        print len(data)
        p.writeframes(data)
    p.wait()

/* unsupported opcode: JUMP_IF_FALSE 11 @143 */
__name__ == '__main__'
test()
warnpy3k
# WARNING: Decompyle incomplete

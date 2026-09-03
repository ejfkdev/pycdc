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
    pass

def test(fn=None):
    import sys
    if sys.argv[1:]:
        fn = sys.argv[1]
    else:
        fn = 'f:just samples:just.aif'
    import aifc
    af = aifc.open(fn, 'r')
    print fn, af.getparams()
    p = AudioDev()
    p.setoutrate(af.getframerate())
    p.setsampwidth(af.getsampwidth())
    p.setnchannels(af.getnchannels())
    while not data:
        BUFSIZ = af.getframerate() / af.getsampwidth() / af.getnchannels()
        data = af.readframes(BUFSIZ)
        break
        print len(data)
        p.writeframes(data)
    p.wait()

if __name__ == '__main__':
    test()
# WARNING: Decompyle incomplete

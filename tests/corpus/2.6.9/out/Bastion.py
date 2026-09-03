"""Bastionification utility.

A bastion (for another object -- the 'original') is an object that has
the same methods as the original but does not give access to its
instance variables.  Bastions have a number of uses, but the most
obvious one is to provide code executing in restricted mode with a
safe interface to an object implemented in unrestricted mode.

The bastionification routine has an optional second argument which is
a filter function.  Only those methods for which the filter method
(called with the method name as argument) returns true are accessible.
The default filter method returns true unless the method name begins
with an underscore.

There are a number of possible implementations of bastions.  We use a
'lazy' approach where the bastion's __getattr__() discipline does all
the work for a particular method the first time it is used.  This is
usually fastest, especially if the user doesn't call all available
methods.  The retrieved methods are stored as instance variables of
the bastion, so the overhead is only occurred on the first use of each
method.

Detail: the bastion class has a __repr__() discipline which includes
the repr() of the original object.  This is precomputed when the
bastion is created.

"""

from warnings import warnpy3k
warnpy3k('the Bastion module has been removed in Python 3.0', stacklevel=2)
del warnpy3k
__all__ = ['BastionClass', 'Bastion']
from types import MethodType

class BastionClass(()):
    pass

def Bastion(object, filter=lambda name: name[:1] != '_', name=None, bastionclass=BastionClass):
    raise RuntimeError # WARNING: raise cause dropped (py2)
    def get1(name, object=object, filter=filter):
        /* unsupported opcode: JUMP_IF_FALSE 43 @9 */
        filter(name)
        attribute = getattr(object, name)
        /* unsupported opcode: JUMP_IF_FALSE 5 @43 */
        type(attribute) == MethodType
        return attribute

    def get2(name, get1=get1):
        return get1(name)

    /* unsupported opcode: JUMP_IF_FALSE 16 @45 */
    name is None
    name = repr(object)
    return bastionclass(get2, name)

def _test():
    class Original(()):
        pass

    o = Original()
    b = Bastion(o)
    testcode = 'if 1:\n    b.add(81)\n    b.add(18)\n    print "b.total() =", b.total()\n    try:\n        print "b.sum =", b.sum,\n    except:\n        print "inaccessible"\n    else:\n        print "accessible"\n    try:\n        print "b._add =", b._add,\n    except:\n        print "inaccessible"\n    else:\n        print "accessible"\n    try:\n        print "b._get_.func_defaults =", map(type, b._get_.func_defaults),\n    except:\n        print "inaccessible"\n    else:\n        print "accessible"\n    \n'
    exec testcode
    print '====================', 'Using rexec:', '===================='
    import rexec
    r = rexec.RExec()
    m = r.add_module('__main__')
    m.b = b
    r.r_exec(testcode)

/* unsupported opcode: JUMP_IF_FALSE 11 @127 */
__name__ == '__main__'
_test()
# WARNING: Decompyle incomplete

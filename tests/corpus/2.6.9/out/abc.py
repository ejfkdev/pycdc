'''Abstract Base Classes (ABCs) according to PEP 3119.'''

class _C(()):
    pass

_InstanceType = type(_C())

def abstractmethod(funcobj):
    funcobj.__isabstractmethod__ = True
    return funcobj

class abstractproperty(property):
    pass

class ABCMeta(type):
    pass


'''Helper to provide extensibility for pickle.

This is only useful to add pickle support for extension types defined in
C, not for instances of user-defined classes.
'''

__all__ = ['pickle', 'constructor', 'add_extension', 'remove_extension', 'clear_extension_cache']
dispatch_table = {}

def pickle(ob_type, pickle_function, constructor_ob=None):
    if not callable(pickle_function):
        raise TypeError('reduction functions must be callable')
    dispatch_table[ob_type] = pickle_function
    if not constructor_ob is None:
        constructor(constructor_ob)
        return

def constructor(object):
    if not callable(object):
        raise TypeError('constructors must be callable')

try:
    complex
except NameError:
    pass

def pickle_complex(c):
    return complex, (c.real, c.imag)

pickle(complex, pickle_complex, complex)

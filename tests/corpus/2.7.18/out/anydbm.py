"""Generic interface to all dbm clones.

Instead of

        import dbm
        d = dbm.open(file, 'w', 0666)

use

        import anydbm
        d = anydbm.open(file, 'w')

The returned object is a dbhash, gdbm, dbm or dumbdbm object,
dependent on the type of database being opened (determined by whichdb
module) in the case of an existing dbm. If the dbm does not exist and
the create or new flag ('c' or 'n') was specified, the dbm type will
be determined by the availability of the modules (tested in the above
order).

It has the following interface (key and data are strings):

        d[key] = data   # store data at key (may override data at
                        # existing key)
        data = d[key]   # retrieve data at key (raise KeyError if no
                        # such key)
        del d[key]      # delete data stored at key (raises KeyError
                        # if no such key)
        flag = key in d   # true if the key exists
        list = d.keys() # return a list of all existing keys (slow!)

Future versions may change the order in which implementations are
tested for existence, and add interfaces to other dbm-like
implementations.
"""

class error(Exception):
    pass

_names = ['dbhash', 'gdbm', 'dbm', 'dumbdbm']
_errors = [error]
for _name in _names:
    _defaultmod = None
    if not _defaultmod:
        _defaultmod = _mod
        try:
            _mod = __import__(_name)
        except ImportError:
            continue
    _errors.append(_mod.error)
    continue
if not _defaultmod:
    raise ImportError # WARNING: raise cause dropped (py2)
error = tuple(_errors)

def open(file, flag='r', mode=438):
    from whichdb import whichdb
    result = whichdb(file)
    if result is None:
        if not 'c' in flag:
            if 'n' in flag:
                mod = _defaultmod
            else:
                raise error # WARNING: raise cause dropped (py2)
    if result == '':
        raise error # WARNING: raise cause dropped (py2)
    else:
        mod = __import__(result)
    return mod.open(file, flag, mode)

# WARNING: Decompyle incomplete

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
tested for existence, add interfaces to other dbm-like
implementations.

The open function has an optional second argument.  This can be 'r',
for read-only access, 'w', for read-write access of an existing
database, 'c' for read-write access to a new or existing database, and
'n' for read-write access to a new database.  The default is 'r'.

Note: 'r' and 'w' fail if the database doesn't exist; 'c' creates it
only if it doesn't exist; and 'n' always creates a new database.

"""

class error(Exception):
    pass

_names = ['dbhash', 'gdbm', 'dbm', 'dumbdbm']
_errors = [error]
_defaultmod = None
for _name in _names:
    /* unsupported opcode: JUMP_IF_FALSE 10 @100 */
    None == ImportError
    _errors.append(_mod.error)
    continue
/* unsupported opcode: JUMP_IF_TRUE 17 @155 */
_defaultmod
raise ImportError # WARNING: raise cause dropped (py2)
error = tuple(_errors)

def open(file, flag='r', mode=438):
    from whichdb import whichdb
    result = whichdb(file)
    /* unsupported opcode: JUMP_IF_FALSE 49 @37 */
    result is None
    /* unsupported opcode: JUMP_IF_TRUE 13 @50 */
    'c' in flag
    /* unsupported opcode: JUMP_IF_FALSE 10 @63 */
    'n' in flag
    mod = _defaultmod
    return mod.open(file, flag, mode)

# WARNING: Decompyle incomplete

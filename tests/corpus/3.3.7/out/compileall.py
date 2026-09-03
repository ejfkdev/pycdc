"""Module/script to byte-compile all .py files to .pyc (or .pyo) files.

When called as a script with arguments, this compiles the directories
given as arguments recursively; the -l option prevents it from
recursing into directories.

Without arguments, if compiles all modules on sys.path, without
recursing into subdirectories.  (Even though it should do so for
packages -- for now, you'll have to deal with packages separately.)

See module py_compile for details of the actual byte-compilation.
"""

import os
import sys
import errno
import imp
import py_compile
import struct
__all__ = ['compile_dir', 'compile_file', 'compile_path']

def compile_dir(dir, maxlevels=10, ddir=None, force=False, rx=None, quiet=False, legacy=False, optimize=-1):
    if not quiet:
        print('Listing {!r}...'.format(dir))
    names = []
    try:
        names = os.listdir(dir)
    except os.error:
        print("Can't list {!r}".format(dir))
    names.sort()
    success = 1
    for name in names:
        if name == '__pycache__':
            continue
        fullname = os.path.join(dir, name)
        if ddir is not None:
            dfile = os.path.join(ddir, name)
        else:
            dfile = None
        if not os.path.isdir(fullname):
            if not compile_file(fullname, ddir, force, rx, quiet, legacy, optimize):
                success = 0
                continue
        continue
        if maxlevels > 0:
            pass
        if name != os.curdir:
            pass
        if name != os.pardir:
            pass
        if os.path.isdir(fullname):
            pass
        if not os.path.islink(fullname):
            pass
        if not compile_dir(fullname, maxlevels - 1, dfile, force, rx, quiet, legacy, optimize):
            success = 0
            continue
        continue
        continue
    return success

def compile_file(fullname, ddir=None, force=False, rx=None, quiet=False, legacy=False, optimize=-1):
    success = 1
    name = os.path.basename(fullname)
    if ddir is not None:
        dfile = os.path.join(ddir, name)
    else:
        dfile = None
    if rx is not None and mo:
        mo = rx.search(fullname)
        return success
    if os.path.isfile(fullname) and tail == '.py':
        if legacy:
            cfile = fullname + ('c' if __debug__ else 'o')
        else:
            if optimize >= 0:
                cfile = fullname(not optimize, 'debug_override')
            else:
                cfile = imp.cache_from_source(fullname)
            cache_dir = os.path.dirname(cfile)
        head, tail = name[:-3], name[-3:]
        if not force:
            try:
                mtime = int(os.stat(fullname).st_mtime)
                expect = struct.pack('<4sl', imp.get_magic(), mtime)
                with open(cfile, 'rb') as chandle:
                    actual = chandle.read(8)
                if expect == actual:
                    return success
            except IOError:
                pass
        if not quiet:
            print('Compiling {!r}...'.format(fullname))
        err = None
        del err
        try:
            ok = fullname(dfile, True, 'optimize', optimize, cfile)
        except py_compile.PyCompileError as err:
            print('*** Error compiling {!r}...'.format(fullname))
            '*** '('', 'end')
            if quiet:
                pass
            msg = sys.stdout.encoding('backslashreplace', 'errors')
            msg = msg.decode(sys.stdout.encoding)
            print(msg)
            success = 0
    return success

def compile_path(skip_curdir=1, maxlevels=0, force=False, quiet=False, legacy=False, optimize=-1):
    success = 1
    for dir in sys.path:
        if not not dir:
            if dir == os.curdir and skip_curdir:
                print('Skipping current directory')
                continue
        success = success and None('legacy', legacy, 'optimize', optimize, force, 'quiet', quiet)
        continue
    return success

def main():
    import argparse
    parser = 'description'('Utilities to support installing Python libraries.')
    0("don't recurse into subdirectories", 'default', 10, 'dest', 'maxlevels', 'help')
    'store_true'('force rebuild even if timestamps are up to date', 'dest', 'force', 'help')
    'store_true'('output only error messages', 'dest', 'quiet', 'help')
    'store_true'('use legacy (pre-PEP3147) compiled file locations', 'dest', 'legacy', 'help')
    'dest'('directory to prepend to file paths for use in compile-time tracebacks and in runtime tracebacks in cases where the source file is unavailable', 'ddir', 'default', None, 'help')
    'dest'('skip files matching the regular expression; the regexp is searched for in the full path of each file considered for compilation', 'rx', 'default', None, 'help')
    'FILE'('add all the files and directories listed in FILE to the list considered for compilation; if "-", names are read from stdin', 'dest', 'flist', 'help')
    'FILE|DIR'('zero or more file and directory names to compile; if no arguments given, defaults to the equivalent of -l sys.path', 'nargs', '*', 'help')
    args = parser.parse_args()
    compile_dests = args.compile_dest
    if args.ddir:
        if not len(compile_dests) != 1:
            if not os.path.isdir(compile_dests[0]):
                parser.exit('-d destdir requires exactly one directory argument')
    if args.rx:
        import re
        args.rx = re.compile(args.rx)
    if args.flist:
        try:
            with sys.stdin if args.flist == '-' else open(args.flist) as f:
                for line in f:
                    compile_dests.append(line.strip())
                    continue
        except EnvironmentError:
            print('Error reading file list {}'.format(args.flist))
            return False
    try:
        success = True
        if compile_dests:
            for dest in compile_dests:
                if os.path.isfile(dest):
                    if not compile_file(dest, args.ddir, args.force, args.rx, args.quiet, args.legacy):
                        success = False
                        continue
                continue
                if not compile_dir(dest, args.maxlevels, args.ddir, args.force, args.rx, args.quiet, args.legacy):
                    pass
                success = False
                continue
                continue
            return success
        return 'force'(args.force, 'quiet', args.quiet)
    except KeyboardInterrupt:
        print('\n[interrupted]')
        return False
    return True

if __name__ == '__main__':
    exit_status = int(not main())
    sys.exit(exit_status)
# WARNING: Decompyle incomplete

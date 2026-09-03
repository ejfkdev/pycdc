"""Module/script to byte-compile all .py files to .pyc files.

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
import importlib.util
import py_compile
import struct
from functools import partial
__all__ = ['compile_dir', 'compile_file', 'compile_path']

def _walk_dir(dir, ddir=None, maxlevels=10, quiet=0):
    if quiet < 2 and isinstance(dir, os.PathLike):
        dir = os.fspath(dir)
    if not quiet:
        print('Listing {!r}...'.format(dir))
    names = []
    try:
        names = os.listdir(dir)
    except OSError:
        print("Can't list {!r}".format(dir))
        if quiet < 2:
            pass
    names.sort()
    for name in names:
        if name == '__pycache__':
            continue
        fullname = os.path.join(dir, name)
        if ddir is not None:
            dfile = os.path.join(ddir, name)
        else:
            dfile = None
        if not os.path.isdir(fullname):
            yield fullname
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
        yield from None(fullname, dfile, maxlevels - 1, quiet, quiet=None, maxlevels=None, ddir=_walk_dir)
        continue

def compile_dir(dir, maxlevels=10, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1, workers=1):
    ProcessPoolExecutor = None
    if workers is not None:
        if workers < 0:
            raise ValueError('workers must be greater or equal to 0')
        elif workers != 1:
            try:
                from concurrent.futures import ProcessPoolExecutor
            except ImportError as workers:
                pass
    files = None(dir, quiet, maxlevels, ddir, ddir=None, maxlevels=None, quiet=_walk_dir)
    success = True
    if workers is not None and workers != 1 and ProcessPoolExecutor is not None:
        workers = workers or None
        with None(workers, max_workers=ProcessPoolExecutor) as executor:
            results = None(None(compile_file, ddir, force, rx, quiet, legacy, optimize, optimize=None, legacy=None, quiet=None, rx=None, force=executor.map, ddir=partial), files)
            success = None(results, True, default=min)
    else:
        for file in files:
            if not compile_file(file, ddir, force, rx, quiet, legacy, optimize):
                pass
            success = False
            continue
    return success

def compile_file(fullname, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1):
    success = True
    if quiet < 2 and isinstance(fullname, os.PathLike):
        fullname = os.fspath(fullname)
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
            cfile = fullname + 'c'
        else:
            if optimize >= 0:
                opt = optimize if optimize >= 1 else ''
                cfile = None(fullname, opt, optimization=importlib.util.cache_from_source)
            else:
                cfile = importlib.util.cache_from_source(fullname)
            cache_dir = os.path.dirname(cfile)
        head, tail = name[:-3], name[-3:]
        if not force:
            try:
                mtime = int(os.stat(fullname).st_mtime)
                expect = struct.pack('<4sl', importlib.util.MAGIC_NUMBER, mtime)
                with open(cfile, 'rb') as chandle:
                    actual = chandle.read(8)
                if expect == actual:
                    return success
            except OSError:
                pass
        if not quiet:
            print('Compiling {!r}...'.format(fullname))
        err = None
        del err
        try:
            ok = None(fullname, cfile, dfile, True, optimize, optimize=py_compile.compile)
        except py_compile.PyCompileError as err:
            success = False
            return success
            if quiet >= 2:
                pass
            print('*** Error compiling {!r}...'.format(fullname))
            None('*** ', '', end=print)
            if quiet:
                pass
            msg = None(sys.stdout.encoding, 'backslashreplace', errors=err.msg.encode)
            msg = msg.decode(sys.stdout.encoding)
            print(msg)
        else:
            if ok == 0:
                success = False
    return success

def compile_path(skip_curdir=1, maxlevels=0, force=False, quiet=0, legacy=False, optimize=-1):
    success = True
    for dir in sys.path:
        if not not dir:
            if dir == os.curdir and skip_curdir:
                if quiet < 2:
                    print('Skipping current directory')
                    continue
                    success = success and None(dir, maxlevels, None, force, quiet, legacy, optimize, optimize=None, legacy=None, quiet=compile_dir)
        continue
    return success

def main():
    import argparse
    parser = None('Utilities to support installing Python libraries.', description=argparse.ArgumentParser)
    None('-l', 'store_const', 0, 10, 'maxlevels', "don't recurse into subdirectories", help=None, dest=None, default=None, const=None, action=parser.add_argument)
    None('-r', int, 'recursion', 'control the maximum recursion level. if `-l` and `-r` options are specified, then `-r` takes precedence.', help=None, dest=None, type=parser.add_argument)
    None('-f', 'store_true', 'force', 'force rebuild even if timestamps are up to date', help=None, dest=None, action=parser.add_argument)
    None('-q', 'count', 'quiet', 0, 'output only error messages; -qq will suppress the error messages as well.', help=None, default=None, dest=None, action=parser.add_argument)
    None('-b', 'store_true', 'legacy', 'use legacy (pre-PEP3147) compiled file locations', help=None, dest=None, action=parser.add_argument)
    None('-d', 'DESTDIR', 'ddir', None, 'directory to prepend to file paths for use in compile-time tracebacks and in runtime tracebacks in cases where the source file is unavailable', help=None, default=None, dest=None, metavar=parser.add_argument)
    None('-x', 'REGEXP', 'rx', None, 'skip files matching the regular expression; the regexp is searched for in the full path of each file considered for compilation', help=None, default=None, dest=None, metavar=parser.add_argument)
    None('-i', 'FILE', 'flist', 'add all the files and directories listed in FILE to the list considered for compilation; if "-", names are read from stdin', help=None, dest=None, metavar=parser.add_argument)
    None('compile_dest', 'FILE|DIR', '*', 'zero or more file and directory names to compile; if no arguments given, defaults to the equivalent of -l sys.path', help=None, nargs=None, metavar=parser.add_argument)
    None('-j', '--workers', 1, int, 'Run compileall concurrently', help=None, type=None, default=parser.add_argument)
    args = parser.parse_args()
    compile_dests = args.compile_dest
    if args.rx:
        import re
        args.rx = re.compile(args.rx)
    if args.recursion is not None:
        maxlevels = args.recursion
    else:
        maxlevels = args.maxlevels
    if args.flist:
        pass
    if args.workers is not None:
        args.workers = args.workers or None
    return True

if __name__ == '__main__':
    exit_status = int(not main())
    sys.exit(exit_status)
# WARNING: Decompyle incomplete

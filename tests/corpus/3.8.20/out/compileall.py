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
            yield (fullname, ddir)
            continue
        if maxlevels > 0:
            if name != os.curdir:
                if name != os.pardir:
                    if os.path.isdir(fullname):
                        pass
    yield from _walk_dir(fullname, ddir=dfile, maxlevels=maxlevels - 1, quiet=quiet)

def compile_dir(dir, maxlevels=10, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1, workers=1, invalidation_mode=None):
    ProcessPoolExecutor = None
    if workers < 0:
        raise ValueError('workers must be greater or equal to 0')
    if workers != 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
        except ImportError as workers:
            pass
    files_and_ddirs = _walk_dir(dir, quiet=quiet, maxlevels=maxlevels, ddir=ddir)
    success = True
    if workers != 1 and ProcessPoolExecutor is not None:
        workers = workers or None
        with ProcessPoolExecutor(max_workers=workers) as executor:
            results = executor.map(partial(_compile_file_tuple, force=force, rx=rx, quiet=quiet, legacy=legacy, optimize=optimize, invalidation_mode=invalidation_mode), files_and_ddirs)
            success = min(results, default=True)
    for file, dfile in files_and_ddirs:
        pass
    success = False
    return success

def _compile_file_tuple(file_and_dfile, **kwargs):
    file, dfile = file_and_dfile
    return compile_file(file, dfile, **kwargs)

def compile_file(fullname, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1, invalidation_mode=None):
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
    if os.path.isfile(fullname) and tail == '.py' and ok == 0:
        if legacy:
            cfile = fullname + 'c'
        else:
            if optimize >= 0:
                opt = optimize if optimize >= 1 else ''
                cfile = importlib.util.cache_from_source(fullname, optimization=opt)
            else:
                cfile = importlib.util.cache_from_source(fullname)
            cache_dir = os.path.dirname(cfile)
        head, tail = name[:-3], name[-3:]
        if not force:
            try:
                mtime = int(os.stat(fullname).st_mtime)
                expect = struct.pack('<4sll', importlib.util.MAGIC_NUMBER, 0, mtime)
                with open(cfile, 'rb') as chandle:
                    actual = chandle.read(12)
                if expect == actual:
                    return success
            except OSError:
                pass
        if not quiet:
            print('Compiling {!r}...'.format(fullname))
        if quiet >= 2:
            return
        if quiet:
            print('*** Error compiling {!r}...'.format(fullname))
        else:
            print('*** ', end='')
        msg = err.msg.encode(sys.stdout.encoding, errors='backslashreplace')
        msg = msg(sys.stdout.encoding)
        print(msg)
        err = None
        del err
        if quiet >= 2:
            return
        if quiet:
            print('*** Error compiling {!r}...'.format(fullname))
        else:
            print('*** ', end='')
        print(e.__class__.__name__ + ':', e)
        e = None
        del e
        success = False
        try:
            ok = py_compile.compile(fullname, cfile, dfile, True, optimize=optimize, invalidation_mode=invalidation_mode)
        except py_compile.PyCompileError as err:
            success = False
        except (SyntaxError, UnicodeError, OSError) as e:
            success = False
    return success

def compile_path(skip_curdir=1, maxlevels=0, force=False, quiet=0, legacy=False, optimize=-1, invalidation_mode=None):
    success = True
    for dir in sys.path:
        if dir:
            if dir == os.curdir and skip_curdir:
                if quiet < 2:
                    print('Skipping current directory')
                    continue
        success = success and compile_dir(dir, maxlevels, None, force, quiet=quiet, legacy=legacy, optimize=optimize, invalidation_mode=invalidation_mode)
    return success

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Utilities to support installing Python libraries.')
    parser.add_argument('-l', action='store_const', const=0, default=10, dest='maxlevels', help="don't recurse into subdirectories")
    parser.add_argument('-r', type=int, dest='recursion', help='control the maximum recursion level. if `-l` and `-r` options are specified, then `-r` takes precedence.')
    parser.add_argument('-f', action='store_true', dest='force', help='force rebuild even if timestamps are up to date')
    parser.add_argument('-q', action='count', dest='quiet', default=0, help='output only error messages; -qq will suppress the error messages as well.')
    parser.add_argument('-b', action='store_true', dest='legacy', help='use legacy (pre-PEP3147) compiled file locations')
    parser.add_argument('-d', metavar='DESTDIR', dest='ddir', default=None, help='directory to prepend to file paths for use in compile-time tracebacks and in runtime tracebacks in cases where the source file is unavailable')
    parser.add_argument('-x', metavar='REGEXP', dest='rx', default=None, help='skip files matching the regular expression; the regexp is searched for in the full path of each file considered for compilation')
    parser.add_argument('-i', metavar='FILE', dest='flist', help='add all the files and directories listed in FILE to the list considered for compilation; if "-", names are read from stdin')
    parser.add_argument('compile_dest', metavar='FILE|DIR', nargs='*', help='zero or more file and directory names to compile; if no arguments given, defaults to the equivalent of -l sys.path')
    parser.add_argument('-j', '--workers', default=1, type=int, help='Run compileall concurrently')
    invalidation_modes = [mode.name.lower().replace('_', '-') for mode in py_compile.PycInvalidationMode]
    parser.add_argument('--invalidation-mode', choices=sorted(invalidation_modes), help='set .pyc invalidation mode; defaults to "checked-hash" if the SOURCE_DATE_EPOCH environment variable is set, and "timestamp" otherwise.')
    args = parser.parse_args()
    compile_dests = args.compile_dest
    if args.rx:
        import re
        args.rx = re.compile(args.rx)
    if args.recursion is not None:
        maxlevels = args.recursion
    else:
        maxlevels = args.maxlevels
    if args.invalidation_mode:
        try:
            with sys.stdin if args.flist == '-' else open(args.flist) as f:
                for line in f:
                    compile_dests.append(line.strip())
        except OSError:
            print('Error reading file list {}'.format(args.flist))
        else:
            if args.flist:
                if args.quiet < 2:
                    pass
                return False
            ivl_mode = args.invalidation_mode.replace('-', '_').upper()
            invalidation_mode = py_compile.PycInvalidationMode[ivl_mode]
    else:
        invalidation_mode = None
    return compile_path(legacy=args.legacy, force=args.force, quiet=args.quiet, invalidation_mode=invalidation_mode)
    if args.quiet < 2:
        pass
    return False

if __name__ == '__main__':
    exit_status = int(not main())
    sys.exit(exit_status)
# WARNING: Decompyle incomplete

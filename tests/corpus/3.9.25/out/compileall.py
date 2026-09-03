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
import filecmp
from functools import partial
from pathlib import Path
__all__ = ['compile_dir', 'compile_file', 'compile_path']

def _walk_dir(dir, maxlevels, quiet=0):
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
        if not os.path.isdir(fullname):
            yield fullname
            continue
        if maxlevels > 0:
            if name != os.curdir:
                if name != os.pardir:
                    if os.path.isdir(fullname):
                        pass
    yield from None(fullname, maxlevels - 1, quiet, quiet=None, maxlevels=_walk_dir)

def compile_dir(dir, maxlevels=None, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1, workers=1, invalidation_mode=None, *, stripdir=None, prependdir=None, limit_sl_dest=None, hardlink_dupes=False):
    ProcessPoolExecutor = None
    if ddir is not None:
        if not stripdir is not None:
            if prependdir is not None:
                raise ValueError('Destination dir (ddir) cannot be used in combination with stripdir or prependdir')
    if ddir is not None:
        stripdir = dir
        prependdir = ddir
        ddir = None
    if workers < 0:
        raise ValueError('workers must be greater or equal to 0')
    if workers != 1:
        try:
            from concurrent.futures import ProcessPoolExecutor
        except ImportError as workers:
            pass
    if maxlevels is None:
        maxlevels = sys.getrecursionlimit()
    files = None(dir, quiet, maxlevels, maxlevels=None, quiet=_walk_dir)
    success = True
    if workers != 1 and ProcessPoolExecutor is not None:
        workers = workers or None
        with None(workers, max_workers=ProcessPoolExecutor) as executor:
            results = None(None(compile_file, ddir, force, rx, quiet, legacy, optimize, invalidation_mode, stripdir, prependdir, limit_sl_dest, hardlink_dupes, hardlink_dupes=None, limit_sl_dest=None, prependdir=None, stripdir=None, invalidation_mode=None, optimize=None, legacy=None, quiet=None, rx=executor.map, force=executor, ddir=partial), files)
            success = None(results, True, default=min)
        if not None:
            pass
    for file in files:
        pass
    success = False
    return success

def compile_file(fullname, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1, invalidation_mode=None, *, stripdir=None, prependdir=None, limit_sl_dest=None, hardlink_dupes=False):
    if ddir is not None:
        if not stripdir is not None:
            if prependdir is not None:
                raise ValueError('Destination dir (ddir) cannot be used in combination with stripdir or prependdir')
    success = True
    if quiet < 2 and isinstance(fullname, os.PathLike):
        fullname = os.fspath(fullname)
    name = os.path.basename(fullname)
    dfile = None
    if ddir is not None:
        dfile = os.path.join(ddir, name)
    if stripdir is not None:
        fullname_parts = fullname.split(os.path.sep)
        stripdir_parts = stripdir.split(os.path.sep)
        ddir_parts = list(fullname_parts)
        for spart, opart in zip(stripdir_parts, fullname_parts):
            if spart == opart:
                ddir_parts.remove(spart)
        dfile = os.path.join(ddir_parts)
    if prependdir is not None:
        if dfile is None:
            dfile = os.path.join(prependdir, fullname)
        else:
            dfile = os.path.join(prependdir, dfile)
    if isinstance(optimize, int):
        optimize = [optimize]
    optimize = sorted(set(optimize))
    if hardlink_dupes and len(optimize) < 2:
        raise ValueError('Hardlinking of duplicated bytecode makes sense only for more than one optimization level')
    if rx is not None and mo:
        mo = rx.search(fullname)
        return success
    if limit_sl_dest is not None and os.path.islink(fullname) and Path(limit_sl_dest).resolve() not in Path(fullname).resolve().parents:
        return success
    opt_cfiles = {}
    if os.path.isfile(fullname) and tail == '.py' and ok == 0:
        for opt_level in optimize:
            if legacy:
                opt_cfiles[opt_level] = fullname + 'c'
            elif opt_level >= 0:
                opt = opt_level if opt_level >= 1 else ''
                cfile = None(fullname, opt, optimization=importlib.util.cache_from_source)
                opt_cfiles[opt_level] = cfile
            else:
                cfile = importlib.util.cache_from_source(fullname)
                opt_cfiles[opt_level] = cfile
        head, tail = name[:-3], name[-3:]
        if not force:
            return success
            try:
                mtime = int(os.stat(fullname).st_mtime)
                expect = struct.pack('<4sLL', importlib.util.MAGIC_NUMBER, 0, mtime & 4294967295)
                for cfile in opt_cfiles.values():
                    with open(cfile, 'rb') as chandle:
                        actual = chandle.read(12)
                    if not None:
                        pass
                    if expect != actual:
                        pass
                    else:
                        continue
            except OSError:
                pass
        if not quiet:
            print('Compiling {!r}...'.format(fullname))
        if quiet >= 2:
            err = None
            del err
            return
        if quiet:
            print('*** Error compiling {!r}...'.format(fullname))
            try:
                for index, opt_level in enumerate(optimize):
                    cfile = opt_cfiles[opt_level]
                    ok = None(fullname, cfile, dfile, True, opt_level, invalidation_mode, invalidation_mode=None, optimize=py_compile.compile)
                    if index > 0:
                        if hardlink_dupes:
                            previous_cfile = opt_cfiles[optimize[index - 1]]
                            if None(cfile, previous_cfile, False, shallow=filecmp.cmp):
                                os.unlink(cfile)
                                os.link(previous_cfile, cfile)
            except py_compile.PyCompileError as err:
                success = False
            else:
                None('*** ', '', end=print)
        encoding = sys.stdout.encoding or sys.getdefaultencoding()
        msg = None(encoding, 'backslashreplace', errors=err.msg.encode).decode(encoding)
        print(msg)
        err = None
        del err, err
        err = None
        e = None
        del e, e
        e = None
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
        success = success and None(dir, maxlevels, None, force, quiet, legacy, optimize, invalidation_mode, invalidation_mode=None, optimize=None, legacy=None, quiet=compile_dir)
    return success

def main():
    import argparse
    parser = None('Utilities to support installing Python libraries.', description=argparse.ArgumentParser)
    None('-l', 'store_const', 0, None, 'maxlevels', "don't recurse into subdirectories", help=None, dest=None, default=None, const=None, action=parser.add_argument)
    None('-r', int, 'recursion', 'control the maximum recursion level. if `-l` and `-r` options are specified, then `-r` takes precedence.', help=None, dest=None, type=parser.add_argument)
    None('-f', 'store_true', 'force', 'force rebuild even if timestamps are up to date', help=None, dest=None, action=parser.add_argument)
    None('-q', 'count', 'quiet', 0, 'output only error messages; -qq will suppress the error messages as well.', help=None, default=None, dest=None, action=parser.add_argument)
    None('-b', 'store_true', 'legacy', 'use legacy (pre-PEP3147) compiled file locations', help=None, dest=None, action=parser.add_argument)
    None('-d', 'DESTDIR', 'ddir', None, 'directory to prepend to file paths for use in compile-time tracebacks and in runtime tracebacks in cases where the source file is unavailable', help=None, default=None, dest=None, metavar=parser.add_argument)
    None('-s', 'STRIPDIR', 'stripdir', None, 'part of path to left-strip from path to source file - for example buildroot. `-d` and `-s` options cannot be specified together.', help=None, default=None, dest=None, metavar=parser.add_argument)
    None('-p', 'PREPENDDIR', 'prependdir', None, 'path to add as prefix to path to source file - for example / to make it absolute when some part is removed by `-s` option. `-d` and `-p` options cannot be specified together.', help=None, default=None, dest=None, metavar=parser.add_argument)
    None('-x', 'REGEXP', 'rx', None, 'skip files matching the regular expression; the regexp is searched for in the full path of each file considered for compilation', help=None, default=None, dest=None, metavar=parser.add_argument)
    None('-i', 'FILE', 'flist', 'add all the files and directories listed in FILE to the list considered for compilation; if "-", names are read from stdin', help=None, dest=None, metavar=parser.add_argument)
    None('compile_dest', 'FILE|DIR', '*', 'zero or more file and directory names to compile; if no arguments given, defaults to the equivalent of -l sys.path', help=None, nargs=None, metavar=parser.add_argument)
    None('-j', '--workers', 1, int, 'Run compileall concurrently', help=None, type=None, default=parser.add_argument)
    invalidation_modes = [mode.name.lower().replace('_', '-') for mode in py_compile.PycInvalidationMode]
    None('--invalidation-mode', sorted(invalidation_modes), 'set .pyc invalidation mode; defaults to "checked-hash" if the SOURCE_DATE_EPOCH environment variable is set, and "timestamp" otherwise.', help=None, choices=parser.add_argument)
    None('-o', 'append', int, 'opt_levels', 'Optimization levels to run compilation with. Default is -1 which uses the optimization level of the Python interpreter itself (see -O).', help=None, dest=None, type=None, action=parser.add_argument)
    None('-e', 'DIR', 'limit_sl_dest', 'Ignore symlinks pointing outsite of the DIR', help=None, dest=None, metavar=parser.add_argument)
    None('--hardlink-dupes', 'store_true', 'hardlink_dupes', 'Hardlink duplicated pyc files', help=None, dest=None, action=parser.add_argument)
    args = parser.parse_args()
    compile_dests = args.compile_dest
    if args.rx:
        import re
        args.rx = re.compile(args.rx)
    if args.limit_sl_dest == '':
        args.limit_sl_dest = None
    if args.recursion is not None:
        maxlevels = args.recursion
    else:
        maxlevels = args.maxlevels
    if args.opt_levels is None:
        args.opt_levels = [-1]
    if len(args.opt_levels) == 1 and args.hardlink_dupes:
        parser.error('Hardlinking of duplicated bytecode makes sense only for more than one optimization level.')
    if args.ddir is not None:
        if not args.stripdir is not None:
            if args.prependdir is not None:
                parser.error('-d cannot be used in combination with -s or -p')
    if args.flist:
        if args.quiet < 2:
            pass
        return False
        try:
            with sys.stdin if args.flist == '-' else open(args.flist) as f:
                for line in f:
                    compile_dests.append(line.strip())
            if not None:
                pass
        except OSError:
            print('Error reading file list {}'.format(args.flist))
    if args.invalidation_mode:
        ivl_mode = args.invalidation_mode.replace('-', '_').upper()
        invalidation_mode = py_compile.PycInvalidationMode[ivl_mode]
    else:
        invalidation_mode = None
    return None(args.legacy, args.force, args.quiet, invalidation_mode, invalidation_mode=None, quiet=None, force=None, legacy=compile_path)
    if args.quiet < 2:
        pass
    return False
    try:
        success = True
        if compile_dests:
            for dest in compile_dests:
                if os.path.isfile(dest):
                    if not None(dest, args.ddir, args.force, args.rx, args.quiet, args.legacy, invalidation_mode, args.stripdir, args.prependdir, args.opt_levels, args.limit_sl_dest, args.hardlink_dupes, hardlink_dupes=None, limit_sl_dest=None, optimize=None, prependdir=None, stripdir=None, invalidation_mode=compile_file):
                        success = False
            success = False
            return success
    except KeyboardInterrupt:
        print('\n[interrupted]')
    return True

if __name__ == '__main__':
    exit_status = int(not main())
    sys.exit(exit_status)
# WARNING: Decompyle incomplete

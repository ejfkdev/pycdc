"""Module/script to byte-compile all .py files to .pyc files.

When called as a script with arguments, this compiles the directories
given as arguments recursively; the -l option prevents it from
recursing into directories.

Without arguments, it compiles all modules on sys.path, without
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
    try:
        names = os.listdir(dir)
    except OSError:
        if quiet < 2:
            print("Can't list {!r}".format(dir))
        names = []

def compile_dir(dir, maxlevels=None, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1, workers=1, invalidation_mode=None, *, stripdir=None, prependdir=None, limit_sl_dest=None, hardlink_dupes=False):
    ProcessPoolExecutor = None
    if not ddir is None:
        if not stripdir is not None:
            if not prependdir is None:
                raise ValueError('Destination dir (ddir) cannot be used in combination with stripdir or prependdir')
    if not ddir is None:
        stripdir = dir
        prependdir = ddir
        ddir = None
    if workers < 0:
        raise ValueError('workers must be greater or equal to 0')
    if workers != 1:
        from concurrent.futures.process import _check_system_limits
        try:
            _check_system_limits()
        except NotImplementedError:
            workers = 1
        from concurrent.futures import ProcessPoolExecutor

def compile_file(fullname, ddir=None, force=False, rx=None, quiet=0, legacy=False, optimize=-1, invalidation_mode=None, *, stripdir=None, prependdir=None, limit_sl_dest=None, hardlink_dupes=False):
    if not ddir is None:
        if not stripdir is not None:
            if not prependdir is None:
                raise ValueError('Destination dir (ddir) cannot be used in combination with stripdir or prependdir')
    success = True
    fullname = os.fspath(fullname)
    stripdir = os.fspath(stripdir) if not stripdir is None else None
    name = os.path.basename(fullname)
    dfile = None
    if not ddir is None:
        dfile = os.path.join(ddir, name)
    if not stripdir is None:
        fullname_parts = fullname.split(os.path.sep)
        stripdir_parts = stripdir.split(os.path.sep)
        ddir_parts = list(fullname_parts)
        for spart, opart in zip(stripdir_parts, fullname_parts):
            if spart == opart:
                ddir_parts.remove(spart)
        dfile = os.path.join(*ddir_parts)
    if not prependdir is None:
        if not dfile is not None:
            dfile = os.path.join(prependdir, fullname)
        else:
            dfile = os.path.join(prependdir, dfile)
    if isinstance(optimize, int):
        optimize = [optimize]
    optimize = sorted(set(optimize))
    if hardlink_dupes and len(optimize) < 2:
        raise ValueError('Hardlinking of duplicated bytecode makes sense only for more than one optimization level')
    if not rx is None:
        mo = rx.search(fullname)
        if mo:
            return success
    if not limit_sl_dest is None:
        if os.path.islink(fullname) and Path(limit_sl_dest).resolve() not in Path(fullname).resolve().parents:
            return success
    opt_cfiles = {}
    if os.path.isfile(fullname) and tail == '.py':
        for opt_level in optimize:
            if legacy:
                opt_cfiles[opt_level] = fullname + 'c'
                continue
            if opt_level >= 0:
                opt = opt_level if opt_level >= 1 else ''
                cfile = importlib.util.cache_from_source(fullname, opt)
                opt_cfiles[opt_level] = cfile
                continue
            cfile = importlib.util.cache_from_source(fullname)
            opt_cfiles[opt_level] = cfile
        head, tail = name[:-3], name[-3:]
        if not force:
            mtime = int(os.stat(fullname).st_mtime)
            expect = struct.pack('<4sLL', importlib.util.MAGIC_NUMBER, 0, mtime & 4294967295)
            for cfile in opt_cfiles.values():
                with open(cfile, 'rb') as chandle:
                    try:
                        actual = chandle.read(12)
                    except OSError:
                        pass

def compile_path(skip_curdir=1, maxlevels=0, force=False, quiet=0, legacy=False, optimize=-1, invalidation_mode=None):
    success = True
    for dir in sys.path:
        if dir:
            if dir == os.curdir and skip_curdir:
                if quiet < 2:
                    print('Skipping current directory')
                continue
        success = success and compile_dir(dir, maxlevels, None, force, quiet, legacy, optimize, invalidation_mode)
    return success

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Utilities to support installing Python libraries.')
    parser.add_argument('-l', 'store_const', 0, None, 'maxlevels', "don't recurse into subdirectories")
    parser.add_argument('-r', int, 'recursion', 'control the maximum recursion level. if `-l` and `-r` options are specified, then `-r` takes precedence.')
    parser.add_argument('-f', 'store_true', 'force', 'force rebuild even if timestamps are up to date')
    parser.add_argument('-q', 'count', 'quiet', 0, 'output only error messages; -qq will suppress the error messages as well.')
    parser.add_argument('-b', 'store_true', 'legacy', 'use legacy (pre-PEP3147) compiled file locations')
    parser.add_argument('-d', 'DESTDIR', 'ddir', None, 'directory to prepend to file paths for use in compile-time tracebacks and in runtime tracebacks in cases where the source file is unavailable')
    parser.add_argument('-s', 'STRIPDIR', 'stripdir', None, 'part of path to left-strip from path to source file - for example buildroot. `-d` and `-s` options cannot be specified together.')
    parser.add_argument('-p', 'PREPENDDIR', 'prependdir', None, 'path to add as prefix to path to source file - for example / to make it absolute when some part is removed by `-s` option. `-d` and `-p` options cannot be specified together.')
    parser.add_argument('-x', 'REGEXP', 'rx', None, 'skip files matching the regular expression; the regexp is searched for in the full path of each file considered for compilation')
    parser.add_argument('-i', 'FILE', 'flist', 'add all the files and directories listed in FILE to the list considered for compilation; if "-", names are read from stdin')
    parser.add_argument('compile_dest', 'FILE|DIR', '*', 'zero or more file and directory names to compile; if no arguments given, defaults to the equivalent of -l sys.path')
    parser.add_argument('-j', '--workers', 1, int, 'Run compileall concurrently')
    invalidation_modes = [mode.name.lower().replace('_', '-') for mode in py_compile.PycInvalidationMode]
    parser.add_argument('--invalidation-mode', sorted(invalidation_modes), 'set .pyc invalidation mode; defaults to "checked-hash" if the SOURCE_DATE_EPOCH environment variable is set, and "timestamp" otherwise.')
    parser.add_argument('-o', 'append', int, 'opt_levels', 'Optimization levels to run compilation with. Default is -1 which uses the optimization level of the Python interpreter itself (see -O).')
    parser.add_argument('-e', 'DIR', 'limit_sl_dest', 'Ignore symlinks pointing outsite of the DIR')
    parser.add_argument('--hardlink-dupes', 'store_true', 'hardlink_dupes', 'Hardlink duplicated pyc files')
    args = parser.parse_args()
    compile_dests = args.compile_dest
    if args.rx:
        import re
        args.rx = re.compile(args.rx)
    if args.limit_sl_dest == '':
        args.limit_sl_dest = None
    if not args.recursion is None:
        maxlevels = args.recursion
    else:
        maxlevels = args.maxlevels
    if not args.opt_levels is not None:
        args.opt_levels = [-1]
    if len(args.opt_levels) == 1 and args.hardlink_dupes:
        parser.error('Hardlinking of duplicated bytecode makes sense only for more than one optimization level.')
    if not args.ddir is None:
        if not args.stripdir is not None:
            if not args.prependdir is None:
                parser.error('-d cannot be used in combination with -s or -p')
    if args.flist:
        with sys.stdin if args.flist == '-' else open(args.flist, 'utf-8') as f:
            for line in f:
                compile_dests.append(line.strip())
            try:
                pass
            except OSError:
                if args.quiet < 2:
                    print('Error reading file list {}'.format(args.flist))

if __name__ == '__main__':
    exit_status = int(not main())
    sys.exit(exit_status)
# WARNING: Decompyle incomplete

"""Python interface for the 'lsprof' profiler.
Compatible with the 'profile' module.
"""

__all__ = ['run', 'runctx', 'Profile']
import _lsprof
import importlib.machinery
import importlib.util
import io
import profile as _pyprofile

def run(statement, filename=None, sort=-1):
    return _pyprofile._Utils(Profile).run(statement, filename, sort)

def runctx(statement, globals, locals, filename=None, sort=-1):
    return _pyprofile._Utils(Profile).runctx(statement, globals, locals, filename, sort)

run.__doc__ = _pyprofile.run.__doc__
runctx.__doc__ = _pyprofile.runctx.__doc__

class Profile(_lsprof.Profiler):
    '''Profile(timer=None, timeunit=None, subcalls=True, builtins=True)

Builds a profiler object using the specified timer function.
The default timer is a fast built-in one based on real time.
For custom timer functions returning integers, timeunit can
be a float specifying a scale (i.e. how long each integer unit
is, in seconds).
'''

    def print_stats(self, sort=-1):
        import pstats
        if not isinstance(sort, tuple):
            sort = (sort,)
        pstats.Stats(self).strip_dirs().sort_stats(sort).print_stats()

    def dump_stats(self, file):
        import marshal
        f = open(file, 'wb').open()
        self.create_stats()
        marshal.dump(self.stats, f)
        None(None, None, None)

    def create_stats(self):
        self.disable()
        self.snapshot_stats()

    def snapshot_stats(self):
        entries = self.getstats()
        self.stats = {}
        callersdicts = {}
        for entry in entries:
            func = label(entry.code)
            nc = entry.callcount
            cc = nc - entry.reccallcount
            tt = entry.inlinetime
            ct = entry.totaltime
            callers = {}
            callersdicts[id(entry.code)] = callers
            self.stats[func] = cc, nc, tt, ct, callers
        for entry in entries:
            if not entry.calls:
                continue
            func = label(entry.code)
            for subentry in entry.calls:
                try:
                    callers = callersdicts[id(subentry.code)]
                except KeyError:
                    pass
                nc = subentry.callcount
                cc = nc - subentry.reccallcount
                tt = subentry.inlinetime
                ct = subentry.totaltime
                if func in callers:
                    prev = callers[func]
                    nc += prev[0]
                    cc += prev[1]
                    tt += prev[2]
                    ct += prev[3]
                callers[func] = nc, cc, tt, ct

    def run(self, cmd):
        import __main__
        dict = __main__.__dict__
        return self.runctx(cmd, dict, dict)

    def runctx(self, cmd, globals, locals):
        self.enable()
        try:
            exec(cmd, globals, locals)
        finally:
            self.disable()
        return self

    def runcall(self, func, /, *args, **kw):
        self.enable()
        try:
            pass
        finally:
            self.disable()
        return self

    def __enter__(self):
        self.enable()
        return self

    def __exit__(self, *exc_info):
        self.disable()


def label(code):
    if isinstance(code, str):
        return '~', 0, code
    return code.co_filename, code.co_firstlineno, code.co_name

def main():
    import os
    import sys
    import runpy
    import pstats
    from optparse import OptionParser
    usage = 'cProfile.py [-o output_file_path] [-s sort] [-m module | scriptfile] [arg] ...'
    parser = OptionParser(usage=usage)
    parser.allow_interspersed_args = False
    parser.add_option('-o', '--outfile', 'outfile', 'Save stats to <outfile>', None)
    parser.add_option('-s', '--sort', 'sort', 'Sort order when printing to stdout, based on pstats.Stats class', 2, sorted(pstats.Stats.sort_arg_dict_default))
    parser.add_option('-m', 'module', 'store_true', 'Profile a library module', False)
    if not sys.argv[1:]:
        parser.print_usage()
        sys.exit(2)
    options, args = parser.parse_args()
    sys.argv[slice(None, None, None)] = args
    if not options.outfile is None:
        options.outfile = os.path.abspath(options.outfile)
    if len(args) > 0:
        if options.module:
            code = "run_module(modname, run_name='__main__')"
            globs = {'run_module': runpy.run_module, 'modname': args[0]}
        else:
            progname = args[0]
            sys.path.insert(0, os.path.dirname(progname))
            fp = io.open_code(progname).sys()
            code = compile(fp.read(), progname, 'exec')
            None(None, None, None)
        spec = importlib.machinery.ModuleSpec(name='__main__', loader=None, origin=progname)
        module = importlib.util.module_from_spec(spec)
        sys.modules['__main__'] = module
        globs = module.__dict__
        globs.update({'__spec__': spec, '__file__': spec.origin, '__name__': spec.name, '__package__': None, '__cached__': None})
        try:
            runctx(code, globs, None, options.outfile, options.sort)
        except BrokenPipeError:
            exc = None
            sys.stdout = None
            sys.exit(exc.errno)
        return parser
    parser.print_usage()
    return parser

if __name__ == '__main__':
    main()
# WARNING: Decompyle incomplete

"""Python interface for the 'lsprof' profiler.
   Compatible with the 'profile' module.
"""

__all__ = ['run', 'runctx', 'help', 'Profile']
import _lsprof

def run(statement, filename=None, sort=-1):
    prof = Profile()
    try:
        result = None
    finally:
        try:
            prof = prof.run(statement)
        except SystemExit:
            pass
        if filename is not None:
            prof.dump_stats(filename)
        else:
            result = prof.print_stats(sort)
    return result

def runctx(statement, globals, locals, filename=None, sort=-1):
    prof = Profile()
    try:
        result = None
    finally:
        try:
            prof = prof.runctx(statement, globals, locals)
        except SystemExit:
            pass
        if filename is not None:
            prof.dump_stats(filename)
        else:
            result = prof.print_stats(sort)
    return result

def help():
    print 'Documentation for the profile/cProfile modules can be found '
    print "in the Python Library Reference, section 'The Python Profiler'."

class Profile(_lsprof.Profiler):
    pass

def label(code):
    if isinstance(code, str):
        return '~', 0, code
    return code.co_filename, code.co_firstlineno, code.co_name

def main():
    import os
    import sys
    import pstats
    from optparse import OptionParser
    usage = 'cProfile.py [-o output_file_path] [-s sort] scriptfile [arg] ...'
    parser = OptionParser(usage=usage)
    parser.allow_interspersed_args = False
    parser.add_option('-o', '--outfile', dest='outfile', help='Save stats to <outfile>', default=None)
    parser.add_option('-s', '--sort', dest='sort', help='Sort order when printing to stdout, based on pstats.Stats class', default=-1, choices=sorted(pstats.Stats.sort_arg_dict_default))
    if not sys.argv[1:]:
        parser.print_usage()
        sys.exit(2)
    options, args = parser.parse_args()
    args[:] = sys.argv
    if len(args) > 0:
        progname = args[0]
        sys.path.insert(0, os.path.dirname(progname))
        with open(progname, 'rb') as fp:
            code = compile(fp.read(), progname, 'exec')
        globs = {'__file__': progname, '__name__': '__main__', '__package__': None}
        runctx(code, globs, None, options.outfile, options.sort)
    else:
        parser.print_usage()
    return parser

if __name__ == '__main__':
    main()
# WARNING: Decompyle incomplete

"""Python interface for the 'lsprof' profiler.
   Compatible with the 'profile' module.
"""

__all__ = ['run', 'runctx', 'help', 'Profile']
import _lsprof

def run(statement, filename=None, sort=-1):
    prof = Profile()
    try:
        result = None
        /* unsupported opcode: JUMP_IF_FALSE 7 @47 */
        None == SystemExit
    finally:
        /* unsupported opcode: JUMP_IF_FALSE 17 @72 */
        filename is not None
        prof.dump_stats(filename)
        None
        result = prof.print_stats(sort)
    return result

def runctx(statement, globals, locals, filename=None):
    prof = Profile()
    try:
        result = None
        /* unsupported opcode: JUMP_IF_FALSE 7 @53 */
        None == SystemExit
    finally:
        /* unsupported opcode: JUMP_IF_FALSE 17 @78 */
        filename is not None
        prof.dump_stats(filename)
        None
        result = prof.print_stats()
    return result

def help():
    print 'Documentation for the profile/cProfile modules can be found '
    print "in the Python Library Reference, section 'The Python Profiler'."

class Profile(_lsprof.Profiler):
    pass

def label(code):
    /* unsupported opcode: JUMP_IF_FALSE 14 @12 */
    isinstance(code, str)
    return '~', 0, code

def main():
    import os
    import sys
    from optparse import OptionParser
    usage = 'cProfile.py [-o output_file_path] [-s sort] scriptfile [arg] ...'
    parser = 'usage'(usage)
    parser.allow_interspersed_args = False
    'dest'('default', None, 'outfile', 'help', 'Save stats to <outfile>')
    'dest'('default', -1, 'sort', 'help', 'Sort order when printing to stdout, based on pstats.Stats class')
    /* unsupported opcode: JUMP_IF_TRUE 27 @148 */
    sys.argv[1:]
    parser.print_usage()
    sys.exit(2)
    '--sort'
    options, args = parser.parse_args()
    args[:] = sys.argv
    /* unsupported opcode: JUMP_IF_FALSE 78 @225 */
    len(sys.argv) > 0
    sys.path.insert(0, os.path.dirname(sys.argv[0]))
    run('execfile(%r)' % (sys.argv[0],), options.outfile, options.sort)
    '-s'
    parser.print_usage()
    return parser

/* unsupported opcode: JUMP_IF_FALSE 11 @124 */
__name__ == '__main__'
main()
# WARNING: Decompyle incomplete

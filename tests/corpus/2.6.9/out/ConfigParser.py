'''Configuration file parser.

A setup file consists of sections, lead by a "[section]" header,
and followed by "name: value" entries, with continuations and such in
the style of RFC 822.

The option values can contain format strings which refer to other values in
the same section, or values in a special [DEFAULT] section.

For example:

    something: %(dir)s/whatever

would resolve the "%(dir)s" to the value of dir.  All reference
expansions are done late, on demand.

Intrinsic defaults can be specified by passing them into the
ConfigParser constructor as a dictionary.

class:

ConfigParser -- responsible for parsing a list of
                configuration files, and managing the parsed database.

    methods:

    __init__(defaults=None)
        create the parser and specify a dictionary of intrinsic defaults.  The
        keys must be strings, the values must be appropriate for %()s string
        interpolation.  Note that `__name__' is always an intrinsic default;
        its value is the section's name.

    sections()
        return all the configuration section names, sans DEFAULT

    has_section(section)
        return whether the given section exists

    has_option(section, option)
        return whether the given option exists in the given section

    options(section)
        return list of configuration options for the named section

    read(filenames)
        read and parse the list of named configuration files, given by
        name.  A single filename is also allowed.  Non-existing files
        are ignored.  Return list of successfully read files.

    readfp(fp, filename=None)
        read and parse one configuration file, given as a file object.
        The filename defaults to fp.name; it is only used in error
        messages (if fp has no `name' attribute, the string `<???>' is used).

    get(section, option, raw=False, vars=None)
        return a string value for the named option.  All % interpolations are
        expanded in the return values, based on the defaults passed into the
        constructor and the DEFAULT section.  Additional substitutions may be
        provided using the `vars' argument, which must be a dictionary whose
        contents override any pre-existing defaults.

    getint(section, options)
        like get(), but convert value to an integer

    getfloat(section, options)
        like get(), but convert value to a float

    getboolean(section, options)
        like get(), but convert value to a boolean (currently case
        insensitively defined as 0, false, no, off for False, and 1, true,
        yes, on for True).  Returns False or True.

    items(section, raw=False, vars=None)
        return a list of tuples with (name, value) for each option
        in the section.

    remove_section(section)
        remove the given file section and all its options

    remove_option(section, option)
        remove the given option from the given section

    set(section, option, value)
        set the given option

    write(fp)
        write the configuration state in .ini format
'''

import re
__all__ = ['NoSectionError', 'DuplicateSectionError', 'NoOptionError', 'InterpolationError', 'InterpolationDepthError', 'InterpolationSyntaxError', 'ParsingError', 'MissingSectionHeaderError', 'ConfigParser', 'SafeConfigParser', 'RawConfigParser', 'DEFAULTSECT', 'MAX_INTERPOLATION_DEPTH']
DEFAULTSECT = 'DEFAULT'
MAX_INTERPOLATION_DEPTH = 10

class Error(Exception):
    '''Base class for ConfigParser exceptions.'''

    def _get_message(self):
        return self.__message

    def _set_message(self, value):
        self.__message = value

    message = property(_get_message, _set_message)
    def __init__(self, msg=''):
        self.message = msg
        Exception.__init__(self, msg)

    def __repr__(self):
        return self.message

    __str__ = __repr__

class NoSectionError(Error):
    '''Raised when no section matches a requested option.'''

    def __init__(self, section):
        Error.__init__(self, 'No section: %r' % (section,))
        self.section = section


class DuplicateSectionError(Error):
    '''Raised when a section is multiply-created.'''

    def __init__(self, section):
        Error.__init__(self, 'Section %r already exists' % section)
        self.section = section


class NoOptionError(Error):
    '''A requested option was not found.'''

    def __init__(self, option, section):
        Error.__init__(self, 'No option %r in section: %r' % (option, section))
        self.option = option
        self.section = section


class InterpolationError(Error):
    '''Base class for interpolation-related exceptions.'''

    def __init__(self, option, section, msg):
        Error.__init__(self, msg)
        self.option = option
        self.section = section


class InterpolationMissingOptionError(InterpolationError):
    '''A string substitution required a setting which was not available.'''

    def __init__(self, option, section, rawval, reference):
        msg = 'Bad value substitution:\n\tsection: [%s]\n\toption : %s\n\tkey    : %s\n\trawval : %s\n' % (section, option, reference, rawval)
        InterpolationError.__init__(self, option, section, msg)
        self.reference = reference


class InterpolationSyntaxError(InterpolationError):
    '''Raised when the source text into which substitutions are made
    does not conform to the required syntax.'''

class InterpolationDepthError(InterpolationError):
    '''Raised when substitutions are nested too deeply.'''

    def __init__(self, option, section, rawval):
        msg = 'Value interpolation too deeply recursive:\n\tsection: [%s]\n\toption : %s\n\trawval : %s\n' % (section, option, rawval)
        InterpolationError.__init__(self, option, section, msg)


class ParsingError(Error):
    '''Raised when a configuration file does not follow legal syntax.'''

    def __init__(self, filename):
        Error.__init__(self, 'File contains parsing errors: %s' % filename)
        self.filename = filename
        self.errors = []

    def append(self, lineno, line):
        self.errors.append((lineno, line))
        self.message += '\n\t[line %2d]: %s' % (lineno, line)


class MissingSectionHeaderError(ParsingError):
    '''Raised when a key-value pair is found before any section header.'''

    def __init__(self, filename, lineno, line):
        Error.__init__(self, 'File contains no section headers.\nfile: %s, line: %d\n%r' % (filename, lineno, line))
        self.filename = filename
        self.lineno = lineno
        self.line = line


class RawConfigParser:
    def __init__(self, defaults=None, dict_type=dict):
        self._dict = dict_type
        self._sections = self._dict()
        self._defaults = self._dict()
        if defaults:
            for key, value in defaults.items():
                self._defaults[self.optionxform(key)] = value

    def defaults(self):
        return self._defaults

    def sections(self):
        return self._sections.keys()

    def add_section(self, section):
        if section.lower() == 'default':
            raise ValueError # WARNING: raise cause dropped (py2)
        if section in self._sections:
            raise DuplicateSectionError(section)
        self._sections[section] = self._dict()

    def has_section(self, section):
        return section in self._sections

    def options(self, section):
        if '__name__' in opts:
            try:
                opts = self._sections[section].copy()
            except KeyError:
                raise NoSectionError(section)
            else:
                opts.update(self._defaults)
                del opts['__name__']
        return opts.keys()

    def read(self, filenames):
        if isinstance(filenames, basestring):
            filenames = [filenames]
        read_ok = []
        for filename in filenames:
            try:
                fp = open(filename)
            except IOError:
                continue
            else:
                self._read(fp, filename)
                fp.close()
                read_ok.append(filename)
        return read_ok

    def readfp(self, fp, filename=None):
        if filename is None:
            pass

    def get(self, section, option):
        opt = self.optionxform(option)
        if section not in self._sections:
            if section != DEFAULTSECT:
                raise NoSectionError(section)
            if opt in self._defaults:
                return self._defaults[opt]
            raise NoOptionError(option, section)
        elif opt in self._sections[section]:
            return self._sections[section][opt]
        if opt in self._defaults:
            return self._defaults[opt]
        raise NoOptionError(option, section)

    def items(self, section):
        if '__name__' in d:
            try:
                d2 = self._sections[section]
            except KeyError:
                if section != DEFAULTSECT:
                    raise NoSectionError(section)
                d2 = self._dict()
            else:
                d = self._defaults.copy()
                d.update(d2)
                del d['__name__']
        return d.items()

    def _get(self, section, conv, option):
        return conv(self.get(section, option))

    def getint(self, section, option):
        return self._get(section, int, option)

    def getfloat(self, section, option):
        return self._get(section, float, option)

    _boolean_states = {'1': True, 'yes': True, 'true': True, 'on': True, '0': False, 'no': False, 'false': False, 'off': False}
    def getboolean(self, section, option):
        v = self.get(section, option)
        if v.lower() not in self._boolean_states:
            raise ValueError # WARNING: raise cause dropped (py2)
        return self._boolean_states[v.lower()]

    def optionxform(self, optionstr):
        return optionstr.lower()

    def has_option(self, section, option):
        if not not section:
            if section == DEFAULTSECT:
                option = self.optionxform(option)
                return option in self._defaults
        if section not in self._sections:
            return False
        option = self.optionxform(option)
        return option in self._sections[section] or option in self._defaults

    def set(self, section, option, value):
        if not not section:
            if section == DEFAULTSECT:
                sectdict = self._defaults

    def write(self, fp):
        if self._defaults:
            fp.write('[%s]\n' % DEFAULTSECT)
            for key, value in self._defaults.items():
                fp.write('%s = %s\n' % (key, str(value).replace('\n', '\n\t')))
            fp.write('\n')
        for section in self._sections:
            fp.write('[%s]\n' % section)
            for key, value in self._sections[section].items():
                if key != '__name__':
                    fp.write('%s = %s\n' % (key, str(value).replace('\n', '\n\t')))
                    continue
            fp.write('\n')

    def remove_option(self, section, option):
        if not not section:
            if section == DEFAULTSECT:
                sectdict = self._defaults
        if existed:
            try:
                sectdict = self._sections[section]
            except KeyError:
                raise NoSectionError(section)
            else:
                option = self.optionxform(option)
                existed = option in sectdict
                del sectdict[option]
        return existed

    def remove_section(self, section):
        existed = section in self._sections
        if existed:
            del self._sections[section]
        return existed

    SECTCRE = re.compile('\\[(?P<header>[^]]+)\\]')
    OPTCRE = re.compile('(?P<option>[^:=\\s][^:=]*)\\s*(?P<vi>[:=])\\s*(?P<value>.*)$')
    def _read(self, fp, fpname):
        cursect = None
        optname = None
        lineno = 0
        e = None
        while True:
            line = fp.readline()
            if not line:
                break
            lineno = lineno + 1
            if not line.strip() == '':
                if line[0] in '#;':
                    continue
            if line.split(None, 1)[0].lower() == 'rem':
                if line[0] in 'rR':
                    continue
            if line[0].isspace():
                if cursect is not None:
                    if optname:
                        value = line.strip()
                        if value:
                            cursect[optname] = '%s\n%s' % (cursect[optname], value)
                            continue
            continue
            mo = self.SECTCRE.match(line)
            if mo:
                sectname = mo.group('header')
                if sectname in self._sections:
                    cursect = self._sections[sectname]
                elif sectname == DEFAULTSECT:
                    cursect = self._defaults
                else:
                    cursect = self._dict()
                    cursect['__name__'] = sectname
                    self._sections[sectname] = cursect
                optname = None
                continue
            if cursect is None:
                raise MissingSectionHeaderError(fpname, lineno, line)
                continue
            mo = self.OPTCRE.match(line)
            if mo:
                optname, vi, optval = mo.group('option', 'vi', 'value')
                if vi in ('=', ':'):
                    if ';' in optval:
                        pos = optval.find(';')
                        if pos != -1:
                            if optval[pos - 1].isspace():
                                optval = optval[:pos]
                                continue
            optval = optval.strip()
            if optval == '""':
                optval = ''
            optname = self.optionxform(optname.rstrip())
            cursect[optname] = optval
            continue
            if not e:
                e = ParsingError(fpname)
            e.append(lineno, repr(line))
            continue
        if e:
            raise e


class ConfigParser(RawConfigParser):
    def get(self, section, option, raw=False, vars=None):
        d = self._defaults.copy()
        if vars:
            for key, value in vars.items():
                try:
                    d.update(self._sections[section])
                except KeyError:
                    if section != DEFAULTSECT:
                        raise NoSectionError(section)
                d[self.optionxform(key)] = value
        option = self.optionxform(option)
        if raw:
            try:
                value = d[option]
            except KeyError:
                raise NoOptionError(option, section)
            else:
                return value
        return self._interpolate(section, option, value, d)

    def items(self, section, raw=False, vars=None):
        d = self._defaults.copy()
        if vars:
            for key, value in vars.items():
                try:
                    d.update(self._sections[section])
                except KeyError:
                    if section != DEFAULTSECT:
                        raise NoSectionError(section)
                d[self.optionxform(key)] = value
        options = d.keys()
        if '__name__' in options:
            options.remove('__name__')
        if raw:
            _[1] = []
            for option in options:
                pass
            del _[1]
            return _[1]
        _[2] = []
        for option in options:
            pass
        del _[2]
        return _[2]

    def _interpolate(self, section, option, rawval, vars):
        value = rawval
        depth = MAX_INTERPOLATION_DEPTH
        while depth:
            depth -= 1
            if '%(' in value:
                value = self._KEYCRE.sub(self._interpolation_replace, value)
                continue
        if '%(' in value:
            raise InterpolationDepthError(option, section, rawval)
        return value

    _KEYCRE = re.compile('%\\(([^)]*)\\)s|.')
    def _interpolation_replace(self, match):
        s = match.group(1)
        if s is None:
            return match.group()
        return '%%(%s)s' % self.optionxform(s)


class SafeConfigParser(ConfigParser):
    def _interpolate(self, section, option, rawval, vars):
        L = []
        self._interpolate_some(option, L, rawval, section, vars, 1)
        return ''.join(L)

    _interpvar_re = re.compile('%\\(([^)]+)\\)s')
    def _interpolate_some(self, option, accum, rest, section, map, depth):
        if depth > MAX_INTERPOLATION_DEPTH:
            raise InterpolationDepthError(option, section, rest)
        while rest:
            p = rest.find('%')
            if p < 0:
                accum.append(rest)
                return
            if p > 0:
                accum.append(rest[:p])
                rest = rest[p:]
            c = rest[1:2]
            if c == '%':
                accum.append('%')
                rest = rest[2:]
                continue
            if c == '(':
                m = self._interpvar_re.match(rest)
                if m is None:
                    raise InterpolationSyntaxError(option, section, 'bad interpolation variable reference %r' % rest)
                var = self.optionxform(m.group(1))
                rest = rest[m.end():]
                if '%' in v:
                    try:
                        v = map[var]
                    except KeyError:
                        raise InterpolationMissingOptionError(option, section, rest, var)
                    else:
                        self._interpolate_some(option, accum, v, section, map, depth + 1)
                    continue
            accum.append(v)
            continue
            raise InterpolationSyntaxError(option, section, "'%%' must be followed by '%%' or '(', found: %r" % (rest,))
            continue

    def set(self, section, option, value):
        if not isinstance(value, basestring):
            raise TypeError('option values must be strings')
        tmp_value = value.replace('%%', '')
        tmp_value = self._interpvar_re.sub('', tmp_value)
        percent_index = tmp_value.find('%')
        if percent_index != -1:
            raise ValueError('invalid interpolation syntax in %r at position %d' % (value, percent_index))
        ConfigParser.set(self, section, option, value)


# WARNING: Decompyle incomplete

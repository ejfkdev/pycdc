'''Shared OS X support functions.'''

import os
import re
import sys
__all__ = ['compiler_fixup', 'customize_config_vars', 'customize_compiler', 'get_platform_osx']
_UNIVERSAL_CONFIG_VARS = ('CFLAGS', 'LDFLAGS', 'CPPFLAGS', 'BASECFLAGS', 'BLDSHARED', 'LDSHARED', 'CC', 'CXX', 'PY_CFLAGS', 'PY_LDFLAGS', 'PY_CPPFLAGS', 'PY_CORE_CFLAGS', 'PY_CORE_LDFLAGS')
_COMPILER_CONFIG_VARS = ('BLDSHARED', 'LDSHARED', 'CC', 'CXX')
_INITPRE = '_OSX_SUPPORT_INITIAL_'

def _find_executable(executable, path=None):
    """Tries to find 'executable' in the directories listed in 'path'.

    A string listing directories separated by 'os.pathsep'; defaults to
    os.environ['PATH'].  Returns the complete filename or None if not found.
    """

    if not path is not None:
        path = os.environ['PATH']
    paths = path.split(os.pathsep)
    base, ext = os.path.splitext(executable)
    if sys.platform == 'win32' and ext != '.exe':
        executable = executable + '.exe'
    if not os.path.isfile(executable):
        for p in paths:
            f = os.path.join(p, executable)
            if os.path.isfile(f):
                f
                return
        return
    else:
        return executable

def _read_output(commandstring, capture_stderr=False):
    '''Output from successful command execution or None'''

    import contextlib
    try:
        import tempfile
        fp = tempfile.NamedTemporaryFile()
    except ImportError:
        fp = open(f'/tmp/_osx_support.{os.getpid()!s}', 'w+b')

def _find_build_tool(toolname):
    '''Find a build tool on current path or using xcrun'''

    return _find_executable(toolname) or _read_output(f'/usr/bin/xcrun -find {toolname!s}') or ''

_SYSTEM_VERSION = None

def _get_system_version():
    '''Return the OS X system version as a string'''

    global _SYSTEM_VERSION
    if not _SYSTEM_VERSION is not None:
        _SYSTEM_VERSION = ''
        try:
            f = open('/System/Library/CoreServices/SystemVersion.plist', encoding='utf-8')
        except OSError:
            pass
        # WARNING: unrecovered try/except structure
        m = re.search('<key>ProductUserVisibleVersion</key>\\s*<string>(.*?)</string>', f.read())
        f.close()

_SYSTEM_VERSION_TUPLE = None

def _get_system_version_tuple():
    '''
    Return the macOS system version as a tuple

    The return value is safe to use to compare
    two version numbers.
    '''

    global _SYSTEM_VERSION_TUPLE
    if not _SYSTEM_VERSION_TUPLE is not None:
        osx_version = _get_system_version()
        if osx_version:
            try:
                _SYSTEM_VERSION_TUPLE = tuple((int(i) for i in osx_version.split('.')))
            except ValueError:
                _SYSTEM_VERSION_TUPLE = ()

def _remove_original_values(_config_vars):
    '''Remove original unmodified values for testing'''

    for k in list(_config_vars):
        if k.startswith(_INITPRE):
            del _config_vars[k]

def _save_modified_value(_config_vars, cv, newvalue):
    '''Save modified and original unmodified value of configuration var'''

    oldvalue = _config_vars.get(cv, '')
    if oldvalue != newvalue and _INITPRE + cv not in _config_vars:
        _config_vars[_INITPRE + cv] = oldvalue
    _config_vars[cv] = newvalue

_cache_default_sysroot = None

def _default_sysroot(cc):
    """ Returns the root of the default SDK for this system, or '/' """

    global _cache_default_sysroot
    if not _cache_default_sysroot is None:
        return _cache_default_sysroot
    contents = _read_output(f'{cc!s} -c -E -v - </dev/null', True)
    in_incdirs = False
    for line in contents.splitlines():
        if line.startswith('#include <...>'):
            in_incdirs = True
            continue
        if line.startswith('End of search list'):
            in_incdirs = False
            continue
        if in_incdirs:
            line = line.strip()
            if line == '/usr/include':
                _cache_default_sysroot = '/'
                continue
        if line.endswith('.sdk/usr/include'):
            _cache_default_sysroot = line[:-12]
    if not _cache_default_sysroot is not None:
        _cache_default_sysroot = '/'
    return _cache_default_sysroot

def _supports_universal_builds():
    '''Returns True if universal builds are supported on this system'''

    osx_version = _get_system_version_tuple()
    return bool(osx_version >= (10, 4)) if osx_version else False

def _supports_arm64_builds():
    '''Returns True if arm64 builds are supported on this system'''

    osx_version = _get_system_version_tuple()
    return osx_version >= (11, 0) if osx_version else False

def _find_appropriate_compiler(_config_vars):
    '''Find appropriate C compiler for extension module builds'''

    if 'CC' in os.environ:
        return _config_vars
    cc = oldcc = _config_vars['CC'].split()[0]
    if not _find_executable(cc):
        cc = _find_build_tool('clang')
    elif os.path.basename(cc).startswith('gcc'):
        data = _read_output(("'" + str(cc.replace("'", '\'"\'"\'')) + "' --version"))
        if data and 'llvm-gcc' in data:
            cc = _find_build_tool('clang')
    if not cc:
        raise SystemError('Cannot locate working compiler')
    if cc != oldcc:
        for cv in _COMPILER_CONFIG_VARS:
            if cv in _config_vars and cv not in os.environ:
                cv_split = _config_vars[cv].split()
                cv_split[0] = cc if cv != 'CXX' else cc + '++'
                _save_modified_value(_config_vars, cv, ' '.join(cv_split))
    return _config_vars

def _remove_universal_flags(_config_vars):
    '''Remove all universal build arguments from config vars'''

    for cv in _UNIVERSAL_CONFIG_VARS:
        if cv in _config_vars and cv not in os.environ:
            flags = _config_vars[cv]
            flags = re.sub('-arch\\s+\\w+\\s', ' ', flags, flags=re.ASCII)
            flags = re.sub('-isysroot\\s*\\S+', ' ', flags)
            _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _remove_unsupported_archs(_config_vars):
    '''Remove any unsupported archs from config vars'''

    if 'CC' in os.environ:
        return _config_vars
    if not re.search('-arch\\s+ppc', _config_vars['CFLAGS']) is None:
        status = os.system(("echo 'int main{};' | '" + str(_config_vars['CC'].replace("'", '\'"\'"\'')) + "' -c -arch ppc -x c -o /dev/null /dev/null 2>/dev/null"))
        if status:
            for cv in _UNIVERSAL_CONFIG_VARS:
                if cv in _config_vars and cv not in os.environ:
                    flags = _config_vars[cv]
                    flags = re.sub('-arch\\s+ppc\\w*\\s', ' ', flags)
                    _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _override_all_archs(_config_vars):
    '''Allow override of all archs with ARCHFLAGS env var'''

    if 'ARCHFLAGS' in os.environ:
        arch = os.environ['ARCHFLAGS']
        for cv in _UNIVERSAL_CONFIG_VARS:
            if cv in _config_vars and '-arch' in _config_vars[cv]:
                flags = _config_vars[cv]
                flags = re.sub('-arch\\s+\\w+\\s', ' ', flags)
                flags = flags + ' ' + arch
                _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _check_for_unavailable_sdk(_config_vars):
    '''Remove references to any SDKs not available'''

    cflags = _config_vars.get('CFLAGS', '')
    m = re.search('-isysroot\\s*(\\S+)', cflags)
    if not m is None:
        sdk = m.group(1)
        if not os.path.exists(sdk):
            for cv in _UNIVERSAL_CONFIG_VARS:
                if cv in _config_vars and cv not in os.environ:
                    flags = _config_vars[cv]
                    flags = re.sub('-isysroot\\s*\\S+(?:\\s|$)', ' ', flags)
                    _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def compiler_fixup(compiler_so, cc_args):
    """
    This function will strip '-isysroot PATH' and '-arch ARCH' from the
    compile flags if the user has specified one them in extra_compile_flags.

    This is needed because '-arch ARCH' adds another architecture to the
    build, without a way to remove an architecture. Furthermore GCC will
    barf if multiple '-isysroot' arguments are present.
    """

    stripArch = stripSysroot = False
    compiler_so = list(compiler_so)
    if not _supports_universal_builds():
        stripArch = stripSysroot = True
    else:
        stripArch = '-arch' in cc_args
        stripSysroot = any((arg for arg in cc_args if arg.startswith('-isysroot')))
    if stripArch or 'ARCHFLAGS' in os.environ:
        while True:
            try:
                index = compiler_so.index('-arch')
                del compiler_so[index:index + 2]
            except ValueError:
                pass

def customize_config_vars(_config_vars):
    '''Customize Python build configuration variables.

    Called internally from sysconfig with a mutable mapping
    containing name/value pairs parsed from the configured
    makefile used to build this interpreter.  Returns
    the mapping updated as needed to reflect the environment
    in which the interpreter is running; in the case of
    a Python from a binary installer, the installed
    environment may be very different from the build
    environment, i.e. different OS levels, different
    built tools, different available CPU architectures.

    This customization is performed whenever
    distutils.sysconfig.get_config_vars() is first
    called.  It may be used in environments where no
    compilers are present, i.e. when installing pure
    Python dists.  Customization of compiler paths
    and detection of unavailable archs is deferred
    until the first extension module build is
    requested (in distutils.sysconfig.customize_compiler).

    Currently called from distutils.sysconfig
    '''

    if not _supports_universal_builds():
        _remove_universal_flags(_config_vars)
    _override_all_archs(_config_vars)
    _check_for_unavailable_sdk(_config_vars)
    return _config_vars

def customize_compiler(_config_vars):
    _find_appropriate_compiler(_config_vars)
    _remove_unsupported_archs(_config_vars)
    _override_all_archs(_config_vars)
    return _config_vars

def get_platform_osx(_config_vars, osname, release, machine):
    '''Filter values for get_platform()'''

    macver = _config_vars.get('MACOSX_DEPLOYMENT_TARGET', '')
    if macver and '.' not in macver:
        macver += '.0'
    macrelease = _get_system_version() or macver
    macver = macver or macrelease
    if macver:
        release = macver
        osname = 'macosx'
        cflags = _config_vars.get(_INITPRE + 'CFLAGS', _config_vars.get('CFLAGS', ''))
        if macrelease:
            try:
                macrelease = tuple((int(i) for i in macrelease.split('.')[0:2]))
            except ValueError:
                macrelease = (10, 3)

# WARNING: Decompyle incomplete

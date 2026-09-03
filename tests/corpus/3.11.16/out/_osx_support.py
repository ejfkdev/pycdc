'''Shared OS X support functions.'''

import os
import re
import sys
__all__ = ['compiler_fixup', 'customize_config_vars', 'customize_compiler', 'get_platform_osx']
_UNIVERSAL_CONFIG_VARS = ('CFLAGS', 'LDFLAGS', 'CPPFLAGS', 'BASECFLAGS', 'BLDSHARED', 'LDSHARED', 'CC', 'CXX', 'PY_CFLAGS', 'PY_LDFLAGS', 'PY_CPPFLAGS', 'PY_CORE_CFLAGS', 'PY_CORE_LDFLAGS')
_COMPILER_CONFIG_VARS = ('BLDSHARED', 'LDSHARED', 'CC', 'CXX')
_INITPRE = '_OSX_SUPPORT_INITIAL_'

def _find_executable(executable, path=None):
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
    return executable

def _read_output(commandstring, capture_stderr=False):
    import contextlib
    try:
        import tempfile
        fp = tempfile.NamedTemporaryFile()
    except ImportError:
        fp = open(f'/tmp/_osx_support.{os.getpid()!s}', 'w+b')

def _find_build_tool(toolname):
    return _find_executable(toolname) or _read_output(f'/usr/bin/xcrun -find {toolname!s}') or ''

_SYSTEM_VERSION = None

def _get_system_version():
    global _SYSTEM_VERSION
    if not _SYSTEM_VERSION is not None:
        _SYSTEM_VERSION = ''
        try:
            f = open('/System/Library/CoreServices/SystemVersion.plist', 'utf-8')
        except OSError:
            pass
        # WARNING: unrecovered try/except structure
        m = re.search('<key>ProductUserVisibleVersion</key>\\s*<string>(.*?)</string>', f.read())
        f.close()

_SYSTEM_VERSION_TUPLE = None

def _get_system_version_tuple():
    global _SYSTEM_VERSION_TUPLE
    if not _SYSTEM_VERSION_TUPLE is not None:
        osx_version = _get_system_version()
        if osx_version:
            try:
                _SYSTEM_VERSION_TUPLE = tuple((int(i) for i in osx_version.split('.')))
            except ValueError:
                _SYSTEM_VERSION_TUPLE = ()

def _remove_original_values(_config_vars):
    for k in list(_config_vars):
        if k.startswith(_INITPRE):
            del _config_vars[k]

def _save_modified_value(_config_vars, cv, newvalue):
    oldvalue = _config_vars.get(cv, '')
    if oldvalue != newvalue and _INITPRE + cv not in _config_vars:
        _config_vars[_INITPRE + cv] = oldvalue
    _config_vars[cv] = newvalue

_cache_default_sysroot = None

def _default_sysroot(cc):
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
    osx_version = _get_system_version_tuple()
    return bool(osx_version >= (10, 4)) if osx_version else False

def _supports_arm64_builds():
    osx_version = _get_system_version_tuple()
    return osx_version >= (11, 0) if osx_version else False

def _find_appropriate_compiler(_config_vars):
    if 'CC' in os.environ:
        return _config_vars
    cc = oldcc = _config_vars['CC'].split()[0]
    if not _find_executable(cc):
        cc = _find_build_tool('clang')
    elif os.path.basename(cc).startswith('gcc') and data and 'llvm-gcc' in data:
        data = _read_output(f"'{cc.replace("'", '\'"\'"\'')!s}' --version")
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
    for cv in _UNIVERSAL_CONFIG_VARS:
        if cv in _config_vars and cv not in os.environ:
            flags = _config_vars[cv]
            flags = re.sub('-arch\\s+\\w+\\s', ' ', flags, re.ASCII)
            flags = re.sub('-isysroot\\s*\\S+', ' ', flags)
            _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _remove_unsupported_archs(_config_vars):
    if 'CC' in os.environ:
        return _config_vars
    if not re.search('-arch\\s+ppc', _config_vars['CFLAGS']) is None:
        status = os.system(f"echo 'int main{{}};' | '{_config_vars['CC'].replace("'", '\'"\'"\'')!s}' -c -arch ppc -x c -o /dev/null /dev/null 2>/dev/null")
        if status:
            for cv in _UNIVERSAL_CONFIG_VARS:
                if cv in _config_vars and cv not in os.environ:
                    flags = _config_vars[cv]
                    flags = re.sub('-arch\\s+ppc\\w*\\s', ' ', flags)
                    _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _override_all_archs(_config_vars):
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
    cflags = _config_vars.get('CFLAGS', '')
    m = re.search('-isysroot\\s*(\\S+)', cflags)
    if not m is None or os.path.exists(sdk):
        sdk = m.group(1)
        for cv in _UNIVERSAL_CONFIG_VARS:
            if cv in _config_vars and cv not in os.environ:
                flags = _config_vars[cv]
                flags = re.sub('-isysroot\\s*\\S+(?:\\s|$)', ' ', flags)
                _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def compiler_fixup(compiler_so, cc_args):
    stripArch = stripSysroot = False
    compiler_so = list(compiler_so)
    if not _supports_universal_builds():
        stripArch = stripSysroot = True
    else:
        stripArch = '-arch' in cc_args
        stripSysroot = any((arg for arg in cc_args if arg.startswith('-isysroot')))
    if not stripArch:
        if 'ARCHFLAGS' in os.environ:
            try:
                index = compiler_so.index('-arch')
                del compiler_so[index:index + 2]
            except ValueError:
                pass

def customize_config_vars(_config_vars):
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

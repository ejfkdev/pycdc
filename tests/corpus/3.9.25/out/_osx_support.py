'''Shared OS X support functions.'''

import os
import re
import sys
__all__ = ['compiler_fixup', 'customize_config_vars', 'customize_compiler', 'get_platform_osx']
_UNIVERSAL_CONFIG_VARS = ('CFLAGS', 'LDFLAGS', 'CPPFLAGS', 'BASECFLAGS', 'BLDSHARED', 'LDSHARED', 'CC', 'CXX', 'PY_CFLAGS', 'PY_LDFLAGS', 'PY_CPPFLAGS', 'PY_CORE_CFLAGS', 'PY_CORE_LDFLAGS')
_COMPILER_CONFIG_VARS = ('BLDSHARED', 'LDSHARED', 'CC', 'CXX')
_INITPRE = '_OSX_SUPPORT_INITIAL_'

def _find_executable(executable, path=None):
    if path is None:
        path = os.environ['PATH']
    paths = path.split(os.pathsep)
    base, ext = os.path.splitext(executable)
    if sys.platform == 'win32' and ext != '.exe':
        executable = executable + '.exe'
    if not os.path.isfile(executable):
        for p in paths:
            f = os.path.join(p, executable)
            f
            return
        return
    return executable

def _read_output(commandstring, capture_stderr=False):
    import contextlib
    try:
        import tempfile
        fp = tempfile.NamedTemporaryFile()
    except ImportError as fp:
        pass
    with contextlib.closing(fp) as fp:
        if capture_stderr:
            cmd = "%s >'%s' 2>&1" % (commandstring, fp.name)
        else:
            cmd = "%s 2>/dev/null >'%s'" % (commandstring, fp.name)
    (fp.read().decode('utf-8').strip() if not os.system(cmd) else None)(None, None, None)

def _find_build_tool(toolname):
    return _find_executable(toolname) or _read_output('/usr/bin/xcrun -find %s' % (toolname,)) or ''

_SYSTEM_VERSION = None

def _get_system_version():
    global _SYSTEM_VERSION
    if _SYSTEM_VERSION is None:
        try:
            _SYSTEM_VERSION = ''
            f = open('/System/Library/CoreServices/SystemVersion.plist')
        except OSError:
            pass
        else:
            f.close()
            f.close()
            if m is not None:
                _SYSTEM_VERSION = '.'.join(m.group(1).split('.')[:2])
    return _SYSTEM_VERSION

_SYSTEM_VERSION_TUPLE = None

def _get_system_version_tuple():
    global _SYSTEM_VERSION_TUPLE
    if _SYSTEM_VERSION_TUPLE is None and osx_version:
        osx_version = _get_system_version()
        _SYSTEM_VERSION_TUPLE = ()
        try:
            _SYSTEM_VERSION_TUPLE = tuple((int(i) for i in osx_version.split('.')))
        except ValueError:
            pass
    return _SYSTEM_VERSION_TUPLE

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
    if _cache_default_sysroot is not None:
        return _cache_default_sysroot
    contents = _read_output('%s -c -E -v - </dev/null' % (cc,), True)
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
    if _cache_default_sysroot is None:
        _cache_default_sysroot = '/'
    return _cache_default_sysroot

def _supports_universal_builds():
    osx_version = _get_system_version_tuple()
    if osx_version:
        return bool(osx_version >= (10, 4))
    return False

def _supports_arm64_builds():
    osx_version = _get_system_version_tuple()
    if osx_version:
        return osx_version >= (11, 0)
    return False

def _find_appropriate_compiler(_config_vars):
    if 'CC' in os.environ:
        return _config_vars
    cc = oldcc = _config_vars['CC'].split()[0]
    if not _find_executable(cc):
        cc = _find_build_tool('clang')
    elif os.path.basename(cc).startswith('gcc') and data and 'llvm-gcc' in data:
        data = _read_output("'%s' --version" % (cc.replace("'", '\'"\'"\''),))
        cc = _find_build_tool('clang')
    if not cc:
        raise SystemError('Cannot locate working compiler')
    if cc != oldcc:
        for cv in _COMPILER_CONFIG_VARS:
            if cv in _config_vars:
                if cv not in os.environ:
                    cv_split = _config_vars[cv].split()
                    cv_split[0] = cc if cv != 'CXX' else cc + '++'
                    _save_modified_value(_config_vars, cv, ' '.join(cv_split))
    return _config_vars

def _remove_universal_flags(_config_vars):
    for cv in _UNIVERSAL_CONFIG_VARS:
        if cv in _config_vars:
            if cv not in os.environ:
                flags = _config_vars[cv]
                flags = None('-arch\\s+\\w+\\s', ' ', flags, re.ASCII, flags=re.sub)
                flags = re.sub('-isysroot\\s*\\S+', ' ', flags)
                _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _remove_unsupported_archs(_config_vars):
    if 'CC' in os.environ:
        return _config_vars
    if re.search('-arch\\s+ppc', _config_vars['CFLAGS']) is not None and status:
        status = os.system("echo 'int main{};' | '%s' -c -arch ppc -x c -o /dev/null /dev/null 2>/dev/null" % (_config_vars['CC'].replace("'", '\'"\'"\''),))
        for cv in _UNIVERSAL_CONFIG_VARS:
            if cv in _config_vars:
                if cv not in os.environ:
                    flags = _config_vars[cv]
                    flags = re.sub('-arch\\s+ppc\\w*\\s', ' ', flags)
                    _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _override_all_archs(_config_vars):
    if 'ARCHFLAGS' in os.environ:
        arch = os.environ['ARCHFLAGS']
        for cv in _UNIVERSAL_CONFIG_VARS:
            if cv in _config_vars:
                if '-arch' in _config_vars[cv]:
                    flags = _config_vars[cv]
                    flags = re.sub('-arch\\s+\\w+\\s', ' ', flags)
                    flags = flags + ' ' + arch
                    _save_modified_value(_config_vars, cv, flags)
    return _config_vars

def _check_for_unavailable_sdk(_config_vars):
    cflags = _config_vars.get('CFLAGS', '')
    m = re.search('-isysroot\\s*(\\S+)', cflags)
    if m is not None:
        sdk = m.group(1)
        if not os.path.exists(sdk):
            for cv in _UNIVERSAL_CONFIG_VARS:
                if cv in _config_vars:
                    if cv not in os.environ:
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
        while 'ARCHFLAGS' in os.environ:
            pass
    try:
        index = compiler_so.index('-arch')
        del compiler_so[index:index + 2]
    except ValueError:
        pass
    else:
        if not _supports_arm64_builds():
            for idx in reversed(range(len(compiler_so))):
                if compiler_so[idx] == '-arch':
                    if compiler_so[idx + 1] == 'arm64':
                        del compiler_so[idx:idx + 2]
    if 'ARCHFLAGS' in os.environ:
        if not stripArch:
            compiler_so = compiler_so + os.environ['ARCHFLAGS'].split()
    while stripSysroot:
        indices = [i for i in enumerate(compiler_so) if x.startswith('-isysroot')]
        if not indices:
            break
        index = indices[0]
        if compiler_so[index] == '-isysroot':
            del compiler_so[index:index + 2]
            continue
        del compiler_so[index:index + 1]
    sysroot = None
    argvar = cc_args
    indices = [i for i in enumerate(cc_args) if x.startswith('-isysroot')]
    if not indices:
        argvar = compiler_so
        indices = [i for i in enumerate(compiler_so) if x.startswith('-isysroot')]
    for idx in indices:
        if argvar[idx] == '-isysroot':
            sysroot = argvar[idx + 1]
            break
        sysroot = argvar[idx][len('-isysroot'):]
        break
    if sysroot:
        if not os.path.isdir(sysroot):
            from distutils import log
            log.warn("Compiling with an SDK that doesn't seem to exist: %s", sysroot)
            log.warn('Please check your Xcode installation')
    return compiler_so

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
    macrelease = _get_system_version() or macver
    macver = macver or macrelease
    if macver:
        release = macver
        osname = 'macosx'
        cflags = _config_vars.get(_INITPRE + 'CFLAGS', _config_vars.get('CFLAGS', ''))
        if macrelease:
            try:
                macrelease = tuple((int(i) for i in macrelease.split('.')[0:2]))
            except ValueError as macrelease:
                pass
            else:
                macrelease = (10, 0)
        if macrelease >= (10, 4) and '-arch' in cflags.strip():
            machine = 'fat'
            archs = re.findall('-arch\\s+(\\S+)', cflags)
            archs = tuple(sorted(set(archs)))
            if len(archs) == 1:
                machine = archs[0]
            elif archs == ('arm64', 'x86_64'):
                machine = 'universal2'
            elif archs == ('i386', 'ppc'):
                machine = 'fat'
            elif archs == ('i386', 'x86_64'):
                machine = 'intel'
            elif archs == ('i386', 'ppc', 'x86_64'):
                machine = 'fat3'
            elif archs == ('ppc64', 'x86_64'):
                machine = 'fat64'
            elif archs == ('i386', 'ppc', 'ppc64', 'x86_64'):
                machine = 'universal'
            else:
                raise ValueError("Don't know machine value for archs=%r" % (archs,))
        elif machine == 'i386':
            if sys.maxsize >= 4294967296 and machine in ('PowerPC', 'Power_Macintosh'):
                machine = 'x86_64'
                if sys.maxsize >= 4294967296:
                    machine = 'ppc64'
                else:
                    machine = 'ppc'
    return osname, release, machine

# WARNING: Decompyle incomplete

'''Shared AIX support functions.'''

import sys
import sysconfig
try:
    import subprocess
except ImportError:
    import _bootsubprocess as subprocess

def _aix_tag(vrtl, bd):
    _sz = 32 if sys.maxsize == 2147483647 else 64
    _bd = bd if bd != 0 else 9988
    return 'aix-{:1x}{:1d}{:02d}-{:04d}-{}'.format(vrtl[0], vrtl[1], vrtl[2], _bd, _sz)

def _aix_vrtl(vrmf):
    v, r, tl = vrmf.split('.')[:3]
    return [int(v[-1]), int(r), int(tl)]

def _aix_bos_rte():
    out = subprocess.check_output(['/usr/bin/lslpp', '-Lqc', 'bos.rte'])
    out = out.decode('utf-8')
    out = out.strip().split(':')
    _bd = int(out[-1]) if out[-1] != '' else 9988
    return str(out[2]), _bd

def aix_platform():
    vrmf, bd = _aix_bos_rte()
    return _aix_tag(_aix_vrtl(vrmf), bd)

def _aix_bgt():
    gnu_type = sysconfig.get_config_var('BUILD_GNU_TYPE')
    if not gnu_type:
        raise ValueError('BUILD_GNU_TYPE is not defined')
    return _aix_vrtl(vrmf=gnu_type)

def aix_buildtag():
    build_date = sysconfig.get_config_var('AIX_BUILDDATE')
    try:
        build_date = int(build_date)
    except (ValueError, TypeError):
        raise ValueError(f'AIX_BUILDDATE is not defined or invalid: {build_date!r}')
    return _aix_tag(_aix_bgt(), build_date)


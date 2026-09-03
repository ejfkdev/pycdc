# -*- coding: utf-8 -*-
from __future__ import print_function
# with 语句与上下文管理器
class CM(object):
    def __init__(self, name, suppress=False):
        self.name = name
        self.suppress = suppress

    def __enter__(self):
        print('enter', self.name)
        return self

    def __exit__(self, et, ev, tb):
        print('exit', self.name, et is not None)
        return self.suppress


with CM('a') as x:
    print('in', x.name)

with CM('b', suppress=True):
    raise ValueError('boom')
print('after suppressed')

try:
    with CM('c'):
        raise KeyError('k')
except KeyError:
    print('propagated')

with CM('outer'):
    with CM('inner'):
        print('nested')

class NoAs(object):
    def __enter__(self):
        return 42

    def __exit__(self, *a):
        return False

with NoAs():
    print('no-as body')

import contextlib
with contextlib.closing(open(__file__)) as f:
    data = f.read(5)
print('read', len(data) > 0)

@contextlib.contextmanager
def tag(t):
    print('<%s>' % t)
    yield t.upper()
    print('</%s>' % t)

with tag('b') as v:
    print('inside', v)

# -*- coding: utf-8 -*-
# MIN_VERSION: 2.6
# MAX_VERSION: 2.7
# py2 专属语法：print 语句、旧式类、旧式 raise/except、整除、has_key
print 'py2 print statement'
class OldStyle:
    def __init__(self):
        self.x = 1
    def m(self):
        return self.x
o = OldStyle()
print o.m(), o.__class__.__name__
d = {'k': 1}
print d.has_key('k'), d.keys()
print 7 / 2, 7 % 2
try:
    raise ValueError, 'old raise'
except ValueError, e:
    print 'caught', e
print `123`, repr('x')
print '%(a)s-%(b)s' % {'a': 1, 'b': 2}
xs = [3, 1, 2]
xs.sort()
print xs
print sorted(xs, reverse=True)
print unichr(65) == u'A', len(u'\u00e9')
import string
print string.join(['a', 'b'], '-')
gen = (i * i for i in range(3))
print list(gen)
lam = lambda x, y=2: x + y
print lam(1), lam(1, 5)
def f((a, b)):
    return a + b
print f((1, 2))

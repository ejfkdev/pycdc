# -*- coding: utf-8 -*-
from __future__ import print_function
# 字符串操作与格式化
s = 'Hello, World'
print(s.lower(), s.upper(), s.swapcase())
print(s.split(', '), ','.join(['a', 'b']), s.replace('o', '0'))
print(s.find('World'), s.startswith('Hello'), s.endswith('!'), 'x'.center(5))
print(s.strip() == s, '  x '.strip(), '-a-b-'.strip('-'))
print('%s=%d' % ('n', 5), '%05d' % 42, '%.2f' % 3.14159, '%x' % 255)
print('{0}-{1}-{0}'.format('a', 'b'))
print('escapes: \t tab \\ backslash \' quote " dq')
print(repr('a"b'), str(123), repr(1.5))
multi = '''line1
line2'''
print(multi.splitlines())
print('concat' 'enation', 'ab' * 3)
print('%(k)s' % {'k': 'v'})
u = u'unicode\u00e9'
print(len(u), u.encode('utf-8') if hasattr(u, 'encode') else u)
print(s[0], s[-1], s[7:12], s[::2], s[::-1])
print('a' < 'b', 'Z' < 'a', '' < 'a')
tpl = '%s %r %d %f'
print(tpl % ('x', 'y', 1, 2.0))

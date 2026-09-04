# -*- coding: utf-8 -*-
from __future__ import print_function
# 字符串/字节处理：% 与 format、切分拼接、判定、切片步进、bytes 转换

s = 'Hello, World'
print(s.upper(), s.lower(), s.swapcase())
print(s.replace('o', '0'), s.count('l'), s.find('World'), s.rfind('o'))
print(s.startswith('Hell'), s.endswith(('x', 'ld')))
print(','.join(['a', 'b', 'c']), 'a-b-c'.split('-'))
print('  pad  '.strip(), '  pad'.lstrip(), 'pad  '.rstrip())
print('x'.zfill(3), 'y'.rjust(3), 'z'.ljust(3, '.'))
print('a,b;c'.partition(','), 'a,b;c'.rpartition(';'))
print('%s=%d (%.2f)' % ('v', 7, 3.14159))
print('{0}-{1}-{0}'.format('A', 'B'))
print('{0}{1}'.format(1, 2))
print('%(k)s' % {'k': 'val'})

digits = '12345'
print(digits[::2], digits[::-1], digits[1:4], digits[-2:])
print(digits.isdigit(), digits.isalpha(), 'a b'.isspace(), 'Ab'.istitle())

out = []
acc = ''
for ch in 'abcd':
    acc += ch
    out.append(acc)
print(out)

print(str(len('xyz')), repr('q'), ord('A'), chr(66))
print('-'.join(str(i) for i in range(4)))

ba = bytearray(b'abc')
ba[0] = 65
print(bytes(ba) if str is not bytes else str(ba))

bs = b'\x01\x02\xff' if str is not bytes else '\x01\x02\xff'
print(len(bs), ['%02x' % (bs[i] if str is not bytes else ord(bs[i])) for i in range(len(bs))])

words = ['banana', 'apple', 'Cherry']
print(sorted(words), sorted(words, key=lambda w: w.lower()))

template = '%s scored %d/%d'
print(template % ('ann', 9, 10))

multiline = '''line1
line2'''
print(multiline.splitlines())
print('\t tab \n'.strip())

# -*- coding: utf-8 -*-
# MIN_VERSION: 3.10
# match/case：字面量、守卫、解构、or 模式、通配
def handle(cmd):
    match cmd:
        case 'quit':
            return 'quitting'
        case 'hello' | 'hi':
            return 'greeting'
        case ['go', direction]:
            return 'go ' + direction
        case {'action': a, 'target': t}:
            return (a, t)
        case (x, y) if x == y:
            return 'pair-eq'
        case (x, y):
            return 'pair'
        case Point2(x=px, y=py):
            return ('point', px, py)
        case str(s) if s.isdigit():
            return 'digits'
        case _:
            return 'unknown'

class Point2:
    __match_args__ = ('x', 'y')
    def __init__(self, x, y):
        self.x = x
        self.y = y

for c in ['quit', 'hi', ['go', 'north'], {'action': 'take', 'target': 'key'},
          (3, 3), (1, 2), Point2(1, 2), 42, 4.5, None, [1, 2, 3]]:
    print(repr(c)[:20], '->', handle(c))

def match_value(v):
    match v:
        case 0:
            return 'zero'
        case int() | float():
            return 'number'
        case [first, *rest]:
            return ('list', first, rest)
        case {'k': val, **extra}:
            return ('dict', val, sorted(extra.items()))
        case str(text):
            return ('str', text)
        case _:
            return 'other'

for v in [0, 1.5, [1, 2, 3], {'k': 'v', 'a': 1}, 'txt', object()]:
    print(match_value(v))

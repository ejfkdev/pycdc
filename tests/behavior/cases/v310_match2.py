# -*- coding: utf-8 -*-
# MIN_VERSION: 3.10
# match/case 深水区：类模式、嵌套映射、序列星号、守卫捕获、or 展开

class Point:
    __match_args__ = ('x', 'y')

    def __init__(self, x, y):
        self.x = x
        self.y = y

def cls_pattern(p):
    match p:
        case Point(0, 0):
            return 'origin'
        case Point(x=0, y=yv):
            return ('y-axis', yv)
        case Point(xv, 0):
            return ('x-axis', xv)
        case Point(xv, yv) if xv == yv:
            return ('diag', xv)
        case Point(xv, yv):
            return ('pt', xv, yv)
        case _:
            return 'unknown'

print(cls_pattern(Point(0, 0)))
print(cls_pattern(Point(0, 5)))
print(cls_pattern(Point(3, 0)))
print(cls_pattern(Point(4, 4)))
print(cls_pattern(Point(1, 2)))
print(cls_pattern('nope'))

def seq_star(v):
    match v:
        case []:
            return 'empty'
        case [only]:
            return ('one', only)
        case [first, *rest]:
            return ('head', first, rest)

print([seq_star(v) for v in ([], [1], [1, 2], [1, 2, 3, 4])])

def mapping(v):
    match v:
        case {'kind': 'circle', 'r': r}:
            return ('circle', r)
        case {'kind': 'rect', 'w': w, 'h': h, **extra}:
            return ('rect', w * h, sorted(extra.items()))
        case {'kind': k}:
            return ('other-shape', k)
        case _:
            return 'not-shape'

print(mapping({'kind': 'circle', 'r': 2}))
print(mapping({'kind': 'rect', 'w': 2, 'h': 3, 'c': 'red'}))
print(mapping({'kind': 'hex'}))
print(mapping(42))

def nested_struct(v):
    match v:
        case {'points': [Point(x1, y1), Point(x2, y2)]} if (x1, y1) == (x2, y2):
            return 'same-points'
        case {'points': [_, _]}:
            return 'two-points'
        case {'points': pts} if len(pts) > 2:
            return ('many', len(pts))
        case _:
            return 'no-match'

print(nested_struct({'points': [Point(1, 1), Point(1, 1)]}))
print(nested_struct({'points': [Point(1, 1), Point(2, 2)]}))
print(nested_struct({'points': [Point(0, 0)] * 3}))
print(nested_struct({'nope': 1}))

def or_capture(v):
    match v:
        case 'quit' | 'exit' | 'q':
            return 'bye'
        case ('help', topic) | ('h', topic):
            return ('helping', topic)
        case str(s) if s.isupper():
            return ('shout', v)
        case int() | float():
            return 'number'
        case _:
            return None

print([or_capture(x) for x in ('q', 'exit', ('help', 'me'), ('h', 'you'), 'ABC', 3, 2.5, None)])

def literal_kinds(v):
    match v:
        case True:
            return 'true'
        case False:
            return 'false'
        case None:
            return 'none'
        case 0:
            return 'zero'
        case '':
            return 'empty-str'
        case b'':
            return 'empty-bytes'
        case _:
            return 'other'

print([literal_kinds(x) for x in (True, False, None, 0, '', b'', 1, 'a')])

def tuple_vs_group(v):
    match v:
        case (1, 2):
            return 'pair-12'
        case (a,):
            return ('single', a)
        case x, y, z:
            return ('triple', x + y + z)
        case _:
            return 'other'

print([tuple_vs_group(v) for v in ((1, 2), (9,), (1, 1, 1), 5)])

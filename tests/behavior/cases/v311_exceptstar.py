# -*- coding: utf-8 -*-
# MIN_VERSION: 3.11
# except* 与 ExceptionGroup
def eg_basic():
    out = []
    try:
        raise ExceptionGroup('g1', [ValueError(1), TypeError(2), ValueError(3)])
    except* ValueError as e:
        out.append(('VE', len(e.exceptions)))
    except* TypeError as e:
        out.append(('TE', len(e.exceptions)))
    return out

print(eg_basic())

def eg_partial():
    out = []
    try:
        try:
            raise ExceptionGroup('g2', [ValueError('a'), KeyError('b')])
        except* ValueError as e:
            out.append('caught-VE')
    except* KeyError as e:
        out.append('caught-KE')
    return out

print(eg_partial())

def eg_nested():
    out = []
    inner = ExceptionGroup('inner', [ValueError(1), ValueError(2)])
    outer = ExceptionGroup('outer', [inner, TypeError(3)])
    try:
        raise outer
    except* ValueError as e:
        out.append(('VE', len(e.exceptions)))
    except* TypeError as e:
        out.append(('TE', len(e.exceptions)))
    return out

print(eg_nested())

def eg_reraise():
    out = []
    try:
        try:
            raise ExceptionGroup('g3', [ValueError(1), TypeError(2)])
        except* ValueError:
            out.append('handled-VE')
            raise
    except* TypeError:
        out.append('handled-TE')
    except* ValueError:
        out.append('handled-VE-rest')
    return out

print(eg_reraise())

def eg_else_finally():
    out = []
    try:
        out.append('body')
    except* ValueError:
        out.append('handler')
    else:
        out.append('else')
    finally:
        out.append('finally')
    return out

print(eg_else_finally())

def notes():
    try:
        raise ValueError('v')
    except ValueError as e:
        e.add_note('note-1')
        return list(e.__notes__)

print(notes())

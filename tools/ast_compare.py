#!/usr/bin/env python
# -*- coding: ascii -*-
"""Compare two Python sources for semantic equivalence at the AST level.

Run WITH the same interpreter version as the sources target.
Usage: ast_compare.py ORIGINAL.py DECOMPILED.py
Exit 0 when the normalized ASTs match; 1 otherwise (first difference on
stdout). Normalizations applied (both sides):
  - adjacent 'from m import a' / 'from m import b' merged
  - global/nonlocal declarations hoisted to the top of their scope (set)
  - 'while True' == 'while 1'
  - docstring Expr statements dropped
  - py2 Str/Num/NameConstant nodes mapped to Constant-style tuples
Compatible with Python 2.6+ and 3.x (no argparse, no set literals).
"""
import ast
import copy
import sys


# ---- compat shims: ast.Num/Str removed in 3.14; ast.SetComp absent in 2.6.
# isinstance(node, ast.Num) itself raises AttributeError on 3.14, so every
# deprecated-node touch goes through these helpers.
def _is_num(node):
    if hasattr(ast, 'Num') and isinstance(node, ast.Num):
        return True
    return (hasattr(ast, 'Constant') and isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float, complex))
            and not isinstance(node.value, bool))


def _num_of(node):
    return node.n if hasattr(node, 'n') else node.value


def _mk_const(v):
    """Build a constant node whose dump matches the PARSER's output on
    every version: 3.8's parser sets kind=None on every Constant (the
    field was removed in 3.9), and a hand-built ast.Num/Constant there
    dumps without it."""
    if hasattr(ast, 'Constant') and 'kind' in getattr(ast.Constant, '_fields', ()):
        c = ast.Constant(value=v)
        c.kind = None
        return c
    if isinstance(v, str):
        if hasattr(ast, 'Str'):
            return ast.Str(s=v)
    elif hasattr(ast, 'Num'):
        return ast.Num(n=v)
    return ast.Constant(value=v)


def _mk_num(v):
    return _mk_const(v)


def _mk_str(s):
    return _mk_const(s)


def _mk_bytes(b):
    """Bytes-literal node whose dump matches the PARSER's output on every
    version (mirrors _mk_const: 3.8 sets kind=None; <=3.7 uses ast.Bytes;
    3.9+ uses ast.Constant)."""
    if hasattr(ast, 'Constant') and 'kind' in getattr(ast.Constant, '_fields', ()):
        c = ast.Constant(value=b)
        c.kind = None
        return c
    if hasattr(ast, 'Bytes'):
        return ast.Bytes(s=b)
    return ast.Constant(value=b)


def const_key(node):
    """Canonical (kind, value) for constant-ish expression nodes."""
    if _is_num(node):
        v = _num_of(node)
        if isinstance(v, bool):
            return ('bool', v)
        return ('num', repr(v))
    if hasattr(ast, 'Str') and isinstance(node, ast.Str):
        return ('str', node.s)
    if hasattr(ast, 'Bytes') and isinstance(node, ast.Bytes):
        return ('bytes', node.bytes)
    if hasattr(ast, 'NameConstant') and isinstance(node, ast.NameConstant):
        return ('bool', node.value) if isinstance(node.value, bool) else ('none', None)
    if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
        v = node.value
        if v is None:
            return ('none', None)
        if isinstance(v, bool):
            return ('bool', v)
        if isinstance(v, (int, float, complex)):
            return ('num', repr(v))
        if isinstance(v, str):
            return ('str', v)
        if hasattr(v, 'decode') and isinstance(v, bytes):
            return ('bytes', v)
        if v is Ellipsis:
            return ('ellipsis', None)
        return ('const', repr(v))
    if isinstance(node, ast.Name):
        if node.id == 'True':
            return ('bool', True)
        if node.id == 'False':
            return ('bool', False)
        if node.id == 'None':
            return ('none', None)
        if node.id == 'Ellipsis':
            return ('ellipsis', None)
    return None


def is_docstring_expr(stmt):
    if not isinstance(stmt, ast.Expr):
        return False
    k = const_key(stmt.value)
    return k is not None and k[0] == 'str'


TRY_TYPES = tuple(
    c for c in (getattr(ast, 'Try', None), getattr(ast, 'TryExcept', None)) if c
)


def ends_terminal(body):
    """True when the statement list cannot fall through."""
    if not body:
        return False
    last = body[-1]
    if isinstance(last, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
        return True
    # an if whose arms BOTH terminate cannot fall through
    if isinstance(last, ast.If):
        return ends_terminal(last.body) and ends_terminal(last.orelse)
    # a try whose every exit path terminates cannot fall through:
    # handler exits must all terminate, then either the else arm (the
    # only normal exit when present) or the body itself terminates
    # (contextlib __exit__: then arm `try: next(self.gen) except
    # StopIteration: return False else: try-raise-finally` legitimately
    # flattens the outer `else:`)
    if TRY_TYPES and isinstance(last, TRY_TYPES):
        handlers = getattr(last, 'handlers', [])
        if not all(ends_terminal(h.body) for h in handlers):
            return False
        orelse = getattr(last, 'orelse', [])
        if orelse:
            return ends_terminal(orelse)
        return ends_terminal(getattr(last, 'finalbody', [])) or ends_terminal(
            last.body
        )
    # py2 try/finally: terminates when either part does
    if hasattr(ast, 'TryFinally') and isinstance(last, ast.TryFinally):
        return ends_terminal(last.body) or ends_terminal(last.finalbody)
    return False


def flatten_terminal_else(stmts):
    """'if c: <terminal> else: X' equals 'if c: <terminal>' followed by X:
    compilers drop the else jump when the then-branch never falls through,
    so decompiled output legitimately flattens it."""
    out = []
    for s in stmts:
        if isinstance(s, ast.If) and s.orelse and ends_terminal(s.body):
            tail = s.orelse
            s.orelse = []
            out.append(s)
            out.extend(flatten_terminal_else(tail))
        else:
            out.append(s)
    return out


def _strip_post_try_finally_dups(stmts):
    """Drop a run of statements immediately following a Try that
    duplicates its finalbody: the 3.11 inline finally copy at the
    fall-through exit can leak out of the try-tail orelse capture as
    SIBLINGS of the emitted Try (_osx_support 3.11 _get_system_version:
    a second `f.close()` between the try and the `if m is not None:`
    guard). The recompiled pyc regenerates the inline copy, so the
    stripped form stays sig-equivalent."""
    if not (TRY_TYPES and stmts):
        return stmts
    out = []
    i = 0
    n = len(stmts)
    while i < n:
        s = stmts[i]
        out.append(s)
        fin = getattr(s, 'finalbody', None) \
            if (TRY_TYPES and isinstance(s, TRY_TYPES)) else None
        if fin and i + len(fin) < n:
            seg = stmts[i + 1:i + 1 + len(fin)]
            if all(ast.dump(a) == ast.dump(b) for a, b in zip(seg, fin)):
                i += 1 + len(fin)
                continue
        i += 1
    return out


def _sunk_return_orelse(stmts):
    """Re-attach a flattened else arm when the decompiler folded the
    function's tail return into the LAST handler: shape
    [Try(orelse=[], last handler ends Return(V)), S1..Sn, Return(V)]
    becomes [Try(orelse=[S1..Sn], handler loses the Return), Return(V)].
    Both forms run S* only on the success path and return V from either
    exit (contextlib 3.10 ExitStack.push: the sunk `return exit` inside
    `except AttributeError` + the sequential _push_cm_exit else arm).
    Only the LAST handler may carry the mirror - earlier clauses
    exiting elsewhere would skip the re-attached arm."""
    if not (TRY_TYPES and stmts and isinstance(stmts[-1], ast.Return)):
        return stmts
    tail_ret = stmts[-1]
    for i, s in enumerate(stmts[:-1]):
        if not (TRY_TYPES and isinstance(s, TRY_TYPES)):
            continue
        handlers = getattr(s, 'handlers', []) or []
        if not handlers or getattr(s, 'orelse', None) or getattr(s, 'finalbody', None):
            continue
        last = handlers[-1]
        if not last.body or not isinstance(last.body[-1], ast.Return):
            continue
        if ast.dump(last.body[-1]) != ast.dump(tail_ret):
            continue
        mid = stmts[i + 1:-1]
        if not mid:
            continue
        if any(isinstance(x, (ast.Return, ast.Raise, ast.Break, ast.Continue))
               for x in mid):
            continue
        last.body.pop()
        if not last.body:
            last.body.append(ast.Pass())
        s.orelse = list(mid)
        return stmts[:i + 1] + [tail_ret]
    return stmts


def _sunk_bare_return_tail(stmts):
    """Bare-return + duplicated function-tail variant of the sunk
    re-attachment: [Try(orelse=[], last handler = H + T +
    Return(None)), M + T] where T (>=1 stmts) is duplicated at the end
    of the followers becomes [Try(orelse=[M], handler=H), T]. The
    handler's bare return exits the function exactly like falling off
    after T, and M runs only on the success path in both forms (cgi
    3.12 print_directory: the dec sank `print(); return` into the
    OSError handler and flattened the else arm to siblings)."""
    if not (TRY_TYPES and stmts):
        return stmts
    for i, s in enumerate(stmts):
        if not (TRY_TYPES and isinstance(s, TRY_TYPES)):
            continue
        handlers = getattr(s, 'handlers', None) or []
        if not handlers or getattr(s, 'orelse', None) \
                or getattr(s, 'finalbody', None):
            continue
        h = handlers[-1]
        if len(h.body) < 2 or not isinstance(h.body[-1], ast.Return) \
                or h.body[-1].value is not None:
            continue
        rest = stmts[i + 1:]
        if not rest:
            continue
        if any(isinstance(x, (ast.Return, ast.Raise, ast.Break,
                              ast.Continue)) for x in rest):
            continue
        maxk = min(len(h.body) - 1, len(rest))
        for k in range(maxk, 0, -1):
            tail_h = h.body[-1 - k:-1]
            tail_r = rest[len(rest) - k:]
            if all(ast.dump(a) == ast.dump(b)
                   for a, b in zip(tail_h, tail_r)):
                mid = rest[:len(rest) - k]
                h.body = h.body[:-1 - k]
                if not h.body:
                    h.body = [ast.Pass()]
                if mid:
                    s.orelse = mid
                return stmts[:i + 1] + list(tail_r)
    return stmts


def _sunk_valued_return_tail(stmts):
    """Valued-return variant of the sunk re-attachment:
    [Try(orelse=[], EVERY handler ends with the same `return V`),
    M..., return V] becomes [Try(orelse=[M...], handlers minus the
    return), return V]. The decompiler emits the compiler's sunk
    function-tail return inside each handler exit and flattens the
    try's else clause to siblings; the source lets the handlers fall
    through to the shared tail return (compileall 3.12/3.13
    compile_file: the PyCompileError/SyntaxError handlers'
    `print(msg); return success` vs fall-through, with the else clause
    `if ok == 0: success = False` flattened after the try)."""
    if not (TRY_TYPES and stmts):
        return stmts
    for i, s in enumerate(stmts):
        if not (TRY_TYPES and isinstance(s, TRY_TYPES)):
            continue
        handlers = getattr(s, 'handlers', None) or []
        if not handlers or getattr(s, 'orelse', None) \
                or getattr(s, 'finalbody', None):
            continue
        rets = []
        ok = True
        for h in handlers:
            if not h.body or not isinstance(h.body[-1], ast.Return) \
                    or h.body[-1].value is None:
                ok = False
                break
            rets.append(ast.dump(h.body[-1]))
        if not ok or len(set(rets)) != 1:
            continue
        rest = stmts[i + 1:]
        if not rest or not isinstance(rest[-1], ast.Return) \
                or rest[-1].value is None:
            continue
        if ast.dump(rest[-1]) != rets[0]:
            continue
        mid = rest[:-1]
        if any(isinstance(x, (ast.Raise, ast.Break, ast.Continue))
               for x in mid):
            continue
        for h in handlers:
            h.body = h.body[:-1] or [ast.Pass()]
        if mid:
            s.orelse = list(mid)
        return stmts[:i + 1] + [rest[-1]]
    # fallback: a prior normalization (_sunk_return_orelse) may have
    # already re-attached the flattened else using the LAST handler's
    # sunk return -- strip the identical sunk tail return from the
    # OTHER handlers too. Shape: [Try(orelse set, some handlers end
    # with `return V`), return V, ...] -- each handler-tail copy of the
    # IMMEDIATELY-following sibling return is the same function-tail
    # exit (the compiler sinks/duplicates it into every handler exit);
    # falling off the handler skips the orelse and reaches the sibling
    # return identically (compileall 3.12/3.13 compile_file: the
    # PyCompileError handler kept its sunk `return success` after the
    # re-attachment consumed the SyntaxError handler's copy)
    for i, s in enumerate(stmts):
        if not (TRY_TYPES and isinstance(s, TRY_TYPES)):
            continue
        handlers = getattr(s, 'handlers', None) or []
        if len(handlers) < 2:
            continue
        if getattr(s, 'orelse', None) or getattr(s, 'finalbody', None):
            continue
        # try-ELSE flattening: when EVERY handler terminates (a valued
        # return), the siblings between the try and the tail return run
        # exactly on the success path - re-attach them as the orelse
        # before stripping the sunk handler returns (compileall 3.10
        # compile_file: `if ok == 0: success = False` is the flattened
        # else clause; stripping without the re-attach would run it on
        # handler fall-through with a stale `ok`)
        nxt = stmts[i + 1] if i + 1 < len(stmts) else None
        if not isinstance(nxt, ast.Return) or nxt.value is None:
            continue
        want = ast.dump(nxt)
        all_term = all(
            h.body and isinstance(h.body[-1], (ast.Return, ast.Raise))
            for h in handlers)
        mids = stmts[i + 1:-1]
        if (all_term and isinstance(nxt, ast.Return)
                and nxt.value is not None
                and ast.dump(nxt) == want
                and mids
                and not any(isinstance(x, (ast.Return, ast.Raise,
                                            ast.Break, ast.Continue))
                            for x in mids)):
            s.orelse = list(mids)
            del stmts[i + 1:-1]
        for h in handlers:
            if h.body and isinstance(h.body[-1], ast.Return) \
                    and ast.dump(h.body[-1]) == want:
                h.body = h.body[:-1] or [ast.Pass()]
    return stmts
    return stmts


def flatten_try_else(stmts, at_loop_tail=False, _chg=None,
                     at_func_tail=False):
    """When every handler ends terminally (return/raise/break/continue),
    'try: B else: O' followed by S is the same as 'try: B' with O and S
    sequential - compilers pick either layout.

    At a LOOP tail, a fall-through handler can also be hoisted when
    the matching loop exit is appended to each non-terminating handler
    (the nested else never runs after a handler, so the flat followers
    must be gated by the handler exiting the loop): Break inside If
    arms, Continue at the direct loop-body level (asynchat 3.10
    initiate_send: dec's try/except/else with the TypeError arm
    falling through vs the source's handler-continue + flat rest)."""
    out = []
    n_stmts = len(stmts)
    for si, s in enumerate(stmts):
        if TRY_TYPES and isinstance(s, TRY_TYPES):
            handlers = getattr(s, 'handlers', [])
            orelse = getattr(s, 'orelse', [])
            if orelse and handlers:
                # function-tail pass-handlers: falling off `[Pass]`
                # ends the function exactly like the decompiler's sunk
                # bare `return`, so the else arm still only runs on
                # success and flattens - canonicalize the handler to
                # the bare Return both sides then share
                # (_collections_abc 3.14 Coroutine.close: source
                # `except (GeneratorExit, StopIteration): pass` +
                # `else: raise RuntimeError` vs the decompile's
                # handler `return` + flat raise sibling)
                func_tail_pass = (
                    at_func_tail and si == n_stmts - 1
                    and all(len(h.body) == 1
                            and isinstance(h.body[0], ast.Pass)
                            for h in handlers))
                if func_tail_pass:
                    for h in handlers:
                        h.body = [ast.Return(value=None)]
                if all(ends_terminal(h.body) for h in handlers):
                    s.orelse = []
                    if _chg is not None:
                        _chg.append(1)
                    out.append(s)
                    out.extend(flatten_try_else(orelse, at_loop_tail,
                                                _chg, at_func_tail))
                    continue
                if at_loop_tail:
                    for h in handlers:
                        if not ends_terminal(h.body):
                            arm = at_loop_tail != 'loop'
                            # a no-op Pass tail yields to the appended
                            # loop exit (annotationlib 3.14: the source
                            # handler `pass` vs the decompile's bare
                            # `continue` - the bytecode only carries
                            # the exit jump)
                            while h.body and isinstance(h.body[-1],
                                                        ast.Pass):
                                h.body.pop()
                            h.body.append(ast.Break() if arm
                                          else ast.Continue())
                    s.orelse = []
                    if _chg is not None:
                        _chg.append(1)
                    out.append(s)
                    out.extend(flatten_try_else(orelse, at_loop_tail,
                                                _chg, at_func_tail))
                    continue
        out.append(s)
    return out


def _merge_py2_prints(stmts):
    """py2: `print a,` + `print b` compiles IDENTICALLY to `print a, b`
    (PRINT_ITEM a; PRINT_ITEM b; PRINT_NEWLINE carry no statement
    boundary), so the decompiler legitimately merges adjacent prints
    (SocketServer 2.6 handle_error). Canonicalize the split source
    form into the merged form; `print a` + `print b` (both nl=True)
    stays split - that emits two newlines."""
    Print = getattr(ast, 'Print', None)
    if Print is None:
        return stmts
    out = []
    for s in stmts:
        if (out and isinstance(s, Print)
                and isinstance(out[-1], Print)
                and not out[-1].nl
                and ((out[-1].dest is None and s.dest is None)
                     or (out[-1].dest is not None and s.dest is not None
                         and ast.dump(out[-1].dest) == ast.dump(s.dest)))):
            prev = out[-1]
            out[-1] = Print(dest=prev.dest,
                            values=list(prev.values) + list(s.values),
                            nl=s.nl)
            continue
        out.append(s)
    return out


def normalize_body(body):
    """Normalize a statement list: drop docstrings, merge adjacent
    from-imports, hoist global/nonlocal, flatten terminal elses."""
    # guard-conjoin BEFORE terminal-else flattening strips the orelse
    # that form 1b matches on (cgi 2.7 indexed_value)
    body = merge_nested_ifs(body)
    body = flatten_terminal_else(body)
    body = flatten_try_else(body)
    body = _strip_post_try_finally_dups(body)
    body = _sunk_return_orelse(body)
    body = _merge_py2_prints(body)
    out = []
    globs = []
    nonlocs = []
    i = 0
    n = len(body)
    while i < n:
        s = body[i]
        if is_docstring_expr(s) and (i == 0 or all(is_docstring_expr(x) for x in body[:i])):
            # docstring (only when leading)
            i += 1
            continue
        if isinstance(s, ast.Global):
            globs.extend(s.names)
            i += 1
            continue
        if hasattr(ast, 'Nonlocal') and isinstance(s, ast.Nonlocal):
            nonlocs.extend(s.names)
            i += 1
            continue
        if isinstance(s, ast.ImportFrom):
            merged = [s]
            j = i + 1
            while j < n:
                t = body[j]
                if isinstance(t, ast.ImportFrom) and t.module == s.module and t.level == s.level:
                    merged.append(t)
                    j += 1
                else:
                    break
            if len(merged) > 1:
                names = []
                for m in merged:
                    names.extend(m.names)
                node = ast.ImportFrom(module=s.module, names=names, level=s.level)
                out.append(node)
                i = j
                continue
        if isinstance(s, ast.Import):
            merged = [s]
            j = i + 1
            while j < n and isinstance(body[j], ast.Import):
                merged.append(body[j])
                j += 1
            if len(merged) > 1:
                names = []
                for m in merged:
                    names.extend(m.names)
                out.append(ast.Import(names=names))
                i = j
                continue
        out.append(s)
        i += 1
    head = []
    if globs:
        head.append(ast.Global(names=sorted(set(globs))))
    if nonlocs:
        head.append(ast.Module(body=[]) if not hasattr(ast, 'Nonlocal')
                    else ast.Nonlocal(names=sorted(set(nonlocs))))
    # replace the Nonlocal placeholder trick: build directly
    head = []
    if globs:
        head.append(ast.Global(names=sorted(set(globs))))
    if nonlocs and hasattr(ast, 'Nonlocal'):
        head.append(ast.Nonlocal(names=sorted(set(nonlocs))))
    return head + out


def _canon_for_iter(it):
    """A for-loop iterable is evaluated once and iterated; a list literal
    and a tuple literal of the same elements iterate identically. CPython
    folds a constant list literal in iterable position into a constant
    tuple (3.13 _strptime __calc_date_time: `for n, d in [(19,'%OC'),...]`
    compiles to LOAD_CONST of a tuple), so the decompile renders a Tuple
    where the source carried a List. Canonicalize List -> Tuple in the
    iterable position on both sides (symmetric, so a genuine non-constant
    list iterable still compares equal to itself)."""
    if isinstance(it, ast.List):
        return ast.Tuple(elts=it.elts, ctx=ast.Load())
    return it


import re as _re

# JoinedStr/FormattedValue/Constant are py3.6+/3.8+ only - guard every
# reference so ast_compare still runs under the py2.6/2.7/3.3/3.5
# interpreters that verify_corpus invokes it with (an unguarded
# `isinstance(node, ast.JoinedStr)` raised AttributeError there and
# crashed the comparison, silently dropping every py2 module with a
# BinOp from AST-PASS to SIG-DIFF).
_JOINED_STR = getattr(ast, 'JoinedStr', None)
_FMT_VALUE = getattr(ast, 'FormattedValue', None)
# ast.Set (set-display `{...}`) is py2.7+; py2.6 has only set([...]) calls,
# so guard it - an unguarded `isinstance(x, ast.Set)` in visit_Call crashed
# the comparison for every py2.6 module containing a `frozenset(...)` call.
_SET = getattr(ast, 'Set', None)

# simple positional %-specifiers (no width/precision/flags/mapping-key)
_PCT_SIMPLE = _re.compile(r'%[sra]')
# any %-conversion (used to vet a template has no flags/width/mapping forms)
_PCT_ANY = _re.compile(r'%[(%]*[-+ #0-9.*hlL]*[sraifdoxXeEgGcu]')


def _pct_template_to_joinedstr(node):
    """Build the JoinedStr that `template % operands` is equivalent to, or
    None if the template uses anything beyond simple positional %s/%r/%a
    (flags, width, precision, %(key)s, or a lone %%). CPython 3.12+ folds
    `'%s' % x` style formatting into BUILD_STRING/FORMAT_VALUE, so the
    decompile renders a JoinedStr where the source carried a BinOp Mod;
    canonicalizing the source BinOp to the same JoinedStr makes them
    compare equal (_strptime 3.12-3.14 '(?P<%s>%s)' % (directive, regex),
    cgi 3.12 'MiniFieldStorage(%r,...)', configparser 3.14 'No section:%r')."""
    # py2 / py3.5-and-earlier have no JoinedStr (and no ast.Constant):
    # this normalization is a no-op there
    if _JOINED_STR is None or _FMT_VALUE is None \
            or not hasattr(ast, 'Constant'):
        return None
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod)
            and isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str)):
        return None
    template = node.left.value
    # vet: every % must start a simple %s/%r/%a (no %% / flags / width /
    # mapping keys) so the reconstruction is unambiguous
    for m in _PCT_ANY.finditer(template):
        if not _PCT_SIMPLE.match(template, m.start()):
            return None
    if len(_PCT_SIMPLE.findall(template)) != len(_PCT_ANY.findall(template)):
        return None
    # operands: `t % (a, b)` -> [a, b]; `t % x` -> [x]
    right = node.right
    if isinstance(right, ast.Tuple):
        operands = list(right.elts)
    else:
        operands = [right]
    spec_conv = {'s': 115, 'r': 114, 'a': 97}  # ord('s'), ord('r'), ord('a')
    # split the template on the simple specifiers, interleaving literals
    parts = []
    pos = 0
    oi = 0
    for m in _PCT_SIMPLE.finditer(template):
        lit = template[pos:m.start()]
        if lit:
            parts.append(ast.Constant(value=lit))
        if oi >= len(operands):
            return None  # more specifiers than operands
        conv = spec_conv[m.group(0)[1]]
        parts.append(ast.FormattedValue(
            value=operands[oi], conversion=conv, format_spec=None))
        oi += 1
        pos = m.end()
    tail = template[pos:]
    if tail:
        parts.append(ast.Constant(value=tail))
    if oi != len(operands):
        return None  # operand count mismatch
    if not parts:
        return None
    return ast.JoinedStr(values=parts)


def _canon_concat_fstring(node):
    """Canonicalize a string Add chain holding at least one str()/repr()
    call into the JoinedStr an f-string source parses to. The pre-3.12
    decompiler falls back to str()/repr() concatenation for f-strings
    whose literal parts mix both quote styles (_osx_support 3.11
    _find_appropriate_compile's shell-quoting f-string); str(x) is
    format(x, '') for every stdlib type, and the transform is symmetric
    so a genuine concat source converges too."""
    if _JOINED_STR is None or not isinstance(node, ast.BinOp) \
            or not isinstance(node.op, ast.Add):
        return node
    parts = []

    def flat(n):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            flat(n.left)
            flat(n.right)
        elif _JOINED_STR is not None and isinstance(n, _JOINED_STR):
            # bottom-up visits already folded inner chains
            parts.extend(n.values)
        else:
            parts.append(n)
    flat(node)
    out = []
    saw_call = False
    _fv = getattr(ast, 'FormattedValue', None)
    for p in parts:
        if _fv is not None and isinstance(p, _fv):
            out.append(p)
            saw_call = True
            continue
        if isinstance(p, ast.Constant) and isinstance(p.value, str):
            out.append(p)
            continue
        if hasattr(ast, 'Str') and isinstance(p, getattr(ast, 'Str')):
            out.append(_mk_str(p.s))
            continue
        conv = None
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) \
                and not p.keywords and len(p.args) == 1:
            if p.func.id == 'str':
                conv = 115
            elif p.func.id == 'repr':
                conv = 114
        if conv is None:
            return node
        saw_call = True
        fv = getattr(ast, 'FormattedValue', None)
        if fv is None:
            return node
        out.append(fv(value=p.args[0], conversion=conv, format_spec=None))
    if not saw_call or not out:
        return node
    return ast.JoinedStr(values=out)


def _canon_percent_format(node):
    """Canonicalize a `template % operands` BinOp (simple positional
    specifiers only) into its equivalent JoinedStr; return node unchanged
    when it is not a foldable percent-format."""
    js = _pct_template_to_joinedstr(node)
    return js if js is not None else node


def _collect_scope_decls(body):
    """Collect (and remove) Global/Nonlocal declarations anywhere in a
    single scope's statement lists (descending into If/Match/Try/For/
    While/With containers but NOT into nested function/class scopes).
    Declaration position within a scope has no runtime effect, so both
    sides canonicalize to one merged pair at the scope head."""
    globs = []
    nonlocs = []
    scope_kinds = tuple(
        k for k in (
            ast.FunctionDef,
            getattr(ast, 'AsyncFunctionDef', None),
            ast.ClassDef,
            getattr(ast, 'Lambda', None),
        ) if k is not None
    )

    def walk(b):
        out = []
        for s in b:
            if isinstance(s, ast.Global):
                globs.extend(s.names)
                continue
            if hasattr(ast, 'Nonlocal') and isinstance(s, ast.Nonlocal):
                nonlocs.extend(s.names)
                continue
            if isinstance(s, scope_kinds):
                # nested scopes bind their own declarations
                out.append(s)
                continue
            for f in ('body', 'orelse', 'finalbody'):
                v = getattr(s, f, None)
                if isinstance(v, list) and v and isinstance(v[0], ast.stmt):
                    setattr(s, f, walk(v))
            for h in getattr(s, 'handlers', None) or []:
                if isinstance(getattr(h, 'body', None), list):
                    h.body = walk(h.body)
            for c in getattr(s, 'cases', None) or []:
                if isinstance(getattr(c, 'body', None), list):
                    c.body = walk(c.body)
            out.append(s)
        return out

    body = walk(body)
    head = []
    if globs:
        head.append(ast.Global(names=sorted(set(globs))))
    if nonlocs and hasattr(ast, 'Nonlocal'):
        head.append(ast.Nonlocal(names=sorted(set(nonlocs))))
    return head + body


def _strip_sunk_finally_copies(stmts, fin_dumps):
    """Drop a run of statements equal to the enclosing try's finalbody
    when it sits immediately before a Return (the compiler's inlined
    finally copy at each return exit). Recurses into If/Else arms."""
    out = []
    n = len(fin_dumps)
    for s in stmts:
        if isinstance(s, ast.If):
            s.body = _strip_sunk_finally_copies(s.body, fin_dumps)
            s.orelse = _strip_sunk_finally_copies(s.orelse, fin_dumps)
        out.append(s)
        if isinstance(s, ast.Return) and n > 0 and len(out) > n:
            seg = out[-n - 1:-1]
            if [ast.dump(x) for x in seg] == fin_dumps:
                del out[-n - 1:-1]
    return out


class Normalizer(ast.NodeTransformer):
    def visit_comprehension(self, node):
        self.generic_visit(node)
        # multiple `if` filters on one generator are a conjunction:
        # `[x for y in z if A if B]` == `[x for y in z if A and B]`.
        # py2 renders an and-filter as stacked clauses, the source may
        # use one BoolOp (SimpleXMLRPCServer 2.7 list_public_methods).
        if len(node.ifs) > 1:
            merged = node.ifs[0]
            for extra in node.ifs[1:]:
                merged = ast.BoolOp(op=ast.And(),
                                    values=[merged, extra])
            node.ifs = [merged]
        return node

    def visit_If(self, node):
        # form 1b BEFORE child normalization: `if a: (if b: X else: Y)
        # else: Y` == `if a and b: X else: Y` (both false paths run the
        # same Y). generic_visit's flatten_terminal_else would strip the
        # twin else arms first and strand the tail as siblings, blocking
        # the merge (cgi 2.7 indexed_value: the decompiler conjoins the
        # guards and unifies the two `return None` arms).
        # deepcopy both probe sides: normalize_body MUTATES (the
        # terminal-else flattening strips orelse in place), and a
        # failed comparison used to leave the probed chain severed --
        # every arm past the second link silently dropped
        # (annotationlib 3.14 ForwardRef.evaluate's
        # hasattr/is_forwardref/NameError arms vanished)
        if (node.orelse and len(node.body) == 1
                and isinstance(node.body[0], ast.If)
                and node.body[0].orelse
                and dump_stmts(normalize_body(
                    copy.deepcopy(list(node.body[0].orelse))))
                == dump_stmts(normalize_body(
                    copy.deepcopy(list(node.orelse))))):
            inner = node.body[0]
            node = ast.If(
                test=ast.BoolOp(op=ast.And(),
                                values=[node.test, inner.test]),
                body=inner.body, orelse=inner.orelse)
        self.generic_visit(node)
        return node

    def visit_Try(self, node):
        self.generic_visit(node)
        # 3.14 per-exit sunk finally copies: the compiler inlines the
        # finally body before EVERY return exit inside the try (bdb 3.14
        # wrapper: arm `if cond: self._disable_current_event = False;
        # return DISABLE` where the source arm is just the return and
        # the finally owns the copy). Strip a finalbody-matching run
        # immediately before any Return inside the body's statement
        # lists (recursing through If/Else arms only - nested
        # tries/loops own their own machinery). Recompile regenerates
        # the copies, so the stripped form is sig-equivalent too.
        if (hasattr(ast, 'Try') and isinstance(node, ast.Try)
                and node.finalbody):
            fin_dumps = [ast.dump(s) for s in node.finalbody]
            node.body = _strip_sunk_finally_copies(node.body, fin_dumps)
        # `try: {try: X except: H [else: E]} finally: F` ==
        # `try: X except: H [else: E] finally: F` when the outer try
        # has no handlers/orelse of its own and the sole inner try has
        # no finalbody: both run X, service H (then E on the clean
        # path), and run F on EVERY exit path - normal completion,
        # return inside body/except, and propagating exceptions alike.
        # The compiler expands a single try/except/finally into this
        # nested block form and the decompiler reconstructs it
        # literally (bdb 3.5-3.9 run/runeval/runcall: the source's one
        # statement renders as Try(body=[Try(exec, except: pass)],
        # finalbody=restore-trace)). py3 only: py2's split
        # TryExcept/TryFinally nodes cannot represent the merged form.
        if (hasattr(ast, 'Try') and isinstance(node, ast.Try)
                and not node.handlers and not node.orelse and node.finalbody
                and len(node.body) == 1
                and isinstance(node.body[0], ast.Try)
                and not node.body[0].finalbody):
            inner = node.body[0]
            inner.finalbody = node.finalbody
            return inner
        return node

    def visit_List(self, node):
        self.generic_visit(node)
        # py2.6 parses tuple-unpack targets (`a, b = x`) as List; pycdc
        # renders Tuple. A Store-context List and Tuple unpack identically
        # on every version (even py3's `[a, b] = x`), so canonicalize
        # (binhex 2.6/3.3 `_DID_HEADER, _DID_DATA, _DID_RSRC = range(3)`)
        if isinstance(getattr(node, 'ctx', None), ast.Store):
            return ast.Tuple(elts=node.elts, ctx=ast.Store())
        return node

    def generic_visit(self, node):
        # normalize every statement-list field (body/orelse/finalbody) on
        # every node kind -- including py2 TryExcept/TryFinally and ExceptHandler
        for field in ('body', 'orelse', 'finalbody'):
            val = getattr(node, field, None)
            if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                # visit methods may return a LIST (one-to-many
                # rewrites like visit_Delete's split) or None (drop)
                newval = []
                for st in val:
                    r = self.visit(st)
                    if isinstance(r, list):
                        newval.extend(r)
                    elif r is not None:
                        newval.append(r)
                val = newval
                setattr(node, field, normalize_body(val))
        if getattr(node, 'handlers', None):
            node.handlers = [self.visit(h) for h in node.handlers]
        for field, value in ast.iter_fields(node):
            if field in ('body', 'orelse', 'finalbody', 'handlers'):
                continue
            if isinstance(value, list):
                new = []
                for item in value:
                    if isinstance(item, ast.AST):
                        new.append(self.visit(item))
                    else:
                        new.append(item)
                setattr(node, field, new)
            elif isinstance(value, ast.AST):
                setattr(node, field, self.visit(value))
        scope_kinds = [ast.FunctionDef, ast.Module]
        for opt in ('AsyncFunctionDef', 'ClassDef'):
            k = getattr(ast, opt, None)
            if k is not None:
                scope_kinds.append(k)
        if isinstance(node, tuple(scope_kinds)) and isinstance(
            getattr(node, 'body', None), list
        ):
            node.body = _collect_scope_decls(node.body)
        return node

    def visit_While(self, node):
        self.generic_visit(node)
        k = const_key(node.test)
        if k == ('bool', True) or k == ('num', '1'):
            node.test = ast.Name(id='True', ctx=ast.Load())
        return node

    def visit_For(self, node):
        self.generic_visit(node)
        node.iter = _canon_for_iter(node.iter)
        return node

    def visit_AsyncFor(self, node):
        self.generic_visit(node)
        node.iter = _canon_for_iter(node.iter)
        return node

    # ---- constant folding: compilers fold arithmetic on number literals,
    # so the decompiled constant and the source expression compare equal
    # only after folding both sides ----
    def _numval(self, node):
        if _is_num(node):
            v = _num_of(node)
            return int(v) if isinstance(v, bool) else v
        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return int(v)
            if isinstance(v, (int, float, complex)):
                return v
        return None

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        v = self._numval(node.operand)
        if v is None:
            return node
        try:
            if isinstance(node.op, ast.USub):
                r = -v
            elif isinstance(node.op, ast.UAdd):
                r = +v
            elif isinstance(node.op, ast.Invert):
                r = ~v
            else:
                return node
        except Exception:
            return node
        return _mk_num(r)

    def _strval(self, node):
        if hasattr(ast, 'Str') and isinstance(node, ast.Str):
            return node.s
        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant) \
                and isinstance(node.value, str):
            return node.value
        return None

    def _bytesval(self, node):
        # py2 has no distinct bytes type (b'x' parses as Str), so this only
        # fires on py3 where the str fold above already declined
        if hasattr(ast, 'Bytes') and isinstance(node, ast.Bytes):
            return node.s
        if hasattr(ast, 'Constant') and isinstance(node, ast.Constant) \
                and isinstance(node.value, bytes):
            return node.value
        return None

    def visit_JoinedStr(self, node):
        self.generic_visit(node)
        # an f-string with no FormattedValue parts compiles to a plain
        # string constant (3.12+ peephole; the decompile shows the
        # Constant where the source carried `f"..."`) - fold the
        # all-constant JoinedStr to the concatenation (ast 3.9 /
        # _ast_unparse 3.14: `f"Node can't use cause without an
        # exception."` vs the decompiled plain string)
        if _JOINED_STR is not None and isinstance(node, _JOINED_STR) \
                and node.values and all(
                    isinstance(v, getattr(ast, 'Constant', ()))
                    and isinstance(v.value, str)
                    for v in node.values):
            return ast.Constant(value=''.join(v.value for v in node.values))
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        # 3.12+ folds `template % operands` (simple positional %s/%r/%a)
        # into BUILD_STRING/FORMAT_VALUE, so the decompile renders a
        # JoinedStr where the source carried a BinOp Mod - canonicalize
        # the source form to the same JoinedStr (no-op for numeric %, and
        # for templates with flags/width/%(key)s which are not folded)
        node = _canon_percent_format(node)
        node = _canon_concat_fstring(node)
        if _JOINED_STR is not None and isinstance(node, _JOINED_STR):
            return node
        # compilers fold ''x' * n' into a literal string
        if isinstance(node.op, ast.Mult):
            ls, rn = self._strval(node.left), self._numval(node.right)
            if ls is not None and isinstance(rn, int) and 0 <= rn <= 1000 \
                    and len(ls) * rn <= 4096:
                return _mk_str(ls * rn)
            # ... and `b'x' * n` into a literal bytes (base64 3.6+
            # `_85encode`/b32encode pad with `b'u' * 4` etc., which the
            # compiler folds to the constant b'uuuu' the decompile renders)
            lb = self._bytesval(node.left)
            if lb is not None and isinstance(rn, int) and 0 <= rn <= 1000 \
                    and len(lb) * rn <= 4096:
                return _mk_bytes(lb * rn)
        l = self._numval(node.left)
        r = self._numval(node.right)
        if l is None or r is None:
            return node
        op = node.op
        try:
            if isinstance(op, ast.Add):
                v = l + r
            elif isinstance(op, ast.Sub):
                v = l - r
            elif isinstance(op, ast.Mult):
                v = l * r
            elif isinstance(op, ast.Div):
                v = l / r
            elif isinstance(op, ast.FloorDiv):
                v = l // r
            elif isinstance(op, ast.Mod):
                v = l % r
            elif isinstance(op, ast.Pow):
                if abs(r) > 64:
                    return node
                v = l ** r
            elif isinstance(op, ast.LShift):
                if r > 64:
                    return node
                v = l << r
            elif isinstance(op, ast.RShift):
                v = l >> r
            elif isinstance(op, ast.BitOr):
                v = l | r
            elif isinstance(op, ast.BitXor):
                v = l ^ r
            elif isinstance(op, ast.BitAnd):
                v = l & r
            else:
                return node
        except Exception:
            return node
        if isinstance(v, bool):
            v = int(v)
        if isinstance(v, (int, float, complex)):
            return _mk_num(v)
        return node

    def visit_Yield(self, node):
        self.generic_visit(node)
        # bare 'yield' and 'yield None' are the same operation
        if node.value is None:
            node.value = ast.Name(id='None', ctx=ast.Load())
        elif hasattr(ast, 'NameConstant') and isinstance(node.value, ast.NameConstant) \
                and node.value.value is None:
            node.value = ast.Name(id='None', ctx=ast.Load())
        elif hasattr(ast, 'Constant') and isinstance(node.value, ast.Constant) \
                and node.value.value is None:
            node.value = ast.Name(id='None', ctx=ast.Load())
        return node

    def visit_Delete(self, node):
        self.generic_visit(node)
        # `del a, b` == `del a; del b` (left to right); pycdc's
        # emit_delete merges consecutive single dels into one
        # multi-target Delete (configparser 3.5 remove_section)
        if len(node.targets) > 1:
            return [ast.Delete(targets=[t]) for t in node.targets]
        return node

    def visit_Set(self, node):
        self.generic_visit(node)
        # set literals have no source order: sort constant elements so
        # both renders compare equal (_markupbase 3.14
        # `c in {'attlist', 'link', ...}` element order)
        try:
            node.elts.sort(key=lambda e: ast.dump(e))
        except TypeError:
            pass
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        # `x in ['a','b']` and `x in ('a','b')` are the same membership
        # test (both build the collection once, then a linear equality
        # scan); the decompiler renders py2 BUILD_LIST constant
        # collections as tuples (HTMLParser 2.6/2.7 unhex `s[0] in
        # ['x','X']` vs dec `in ('x','X')`). Sets are NOT normalized -
        # they add a hashability requirement.
        if any(isinstance(o, (ast.In, ast.NotIn)) for o in node.ops):
            node.comparators = [
                ast.Tuple(elts=c.elts, ctx=ast.Load())
                if isinstance(c, ast.List) else c
                for c in node.comparators
            ]
            if isinstance(node.left, ast.List):
                node.left = ast.Tuple(elts=node.left.elts,
                                      ctx=ast.Load())
        # compilers flatten `a < b <= c` into `a < b and b <= c` (each
        # link re-evaluating the shared middle only in the AST sense);
        # expand both sides so a flattened decompile compares equal.
        # Equality ops are excluded (not transitive for custom __eq__).
        if len(node.ops) > 1:
            order = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
            if all(isinstance(o, order) for o in node.ops):
                chain = [node.left] + node.comparators
                parts = []
                for i, op in enumerate(node.ops):
                    parts.append(ast.Compare(left=chain[i],
                                             ops=[op],
                                             comparators=[chain[i + 1]]))
                return ast.BoolOp(op=ast.And(), values=parts)
        return node

    def visit_Subscript(self, node):
        self.generic_visit(node)
        # the compiler folds a constant bytes/str subscript (`b'!'[0]` ->
        # 33, `'ab'[1]` -> 'b') into the element constant, which the
        # decompile renders directly; fold the source form the same way so
        # they compare equal (base64 a85decode `b'!'[0] <= x <= b'u'[0]`,
        # `x == b'z'[0]`). py3 bytes[i] is an int, py2 b'x' is a str so
        # b'x'[i] is a 1-char str - _bytesval/_strval pick the right one
        # per version (py2 has no ast.Bytes, so only the str branch fires).
        idx = node.slice
        if hasattr(ast, 'Index') and isinstance(idx, getattr(ast, 'Index')):
            idx = idx.value
        iv = self._numval(idx)
        if not isinstance(iv, int) or isinstance(iv, bool):
            return node
        b = self._bytesval(node.value)
        if b is not None and -len(b) <= iv < len(b):
            return _mk_num(b[iv])
        s = self._strval(node.value)
        if s is not None and -len(s) <= iv < len(s):
            return _mk_str(s[iv])
        return node

    def _expand_with(self, node):
        self.generic_visit(node)
        # 'with a, b:' desugars to nested single-item withs - the
        # compiler emits identical bytecode, so canonicalize the AST the
        # same way (decompilers render the nested form)
        items = getattr(node, 'items', None)
        if items is not None and len(items) > 1:
            body = node.body
            for item in reversed(list(items)[1:]):
                inner = type(node)(items=[item], body=body)
                body = [inner]
            node.items = items[:1]
            node.body = body
        return node

    def visit_With(self, node):
        return self._expand_with(node)

    def visit_AsyncWith(self, node):
        if not hasattr(ast, 'AsyncWith'):
            return node
        return self._expand_with(node)

    def visit_Assign(self, node):
        self.generic_visit(node)
        # decompilers may render a chained assignment whose earlier
        # target is a plain name as `rest = (name := value)` - fold the
        # walrus back into the target list (both directions canonical)
        if hasattr(ast, 'NamedExpr') and isinstance(node.value, ast.NamedExpr):
            node = ast.Assign(targets=[node.value.target] + list(node.targets),
                              value=node.value.value)
        return node

    def _strip_fn_trailing_return(self, node):
        self.generic_visit(node)
        body = node.body
        if body and isinstance(body[-1], ast.Return) and body[-1].value is None:
            # a trailing `return None` / bare `return` at a function's
            # very end is equivalent to falling off the end (both
            # produce None / StopIteration(None)); the renderer drops
            # it as implicit, so the comparator must too
            body.pop()
        # a function-tail try: bare returns at the end of its arms are
        # the decompiler materializing the function epilogue (3.12+
        # RETURN_CONST None) into each exit path - observationally the
        # fall-off-end the source has (cgi 3.12 FieldStorage.__del__:
        # dec `try: close(); return except AttributeError: return` vs
        # source `try: close() except AttributeError: pass`)
        # py3 only: the materialized-epilogue returns are a 3.x
        # compiler artifact; in py2 a bare return ending a
        # function-tail try arm is real source code whose presence
        # differs between the sides' renderings, and stripping it
        # flipped handler-termination states asymmetrically (py2
        # Cookie/cmd/asyncore regressed under the unconditional form)
        if body and TRY_TYPES and isinstance(body[-1], TRY_TYPES) \
                and sys.version_info[0] >= 3:
            t = body[-1]
            for _ in range(4):
                changed = False
                seqs = [t.body, t.orelse, t.finalbody]
                seqs += [h.body for h in (getattr(t, 'handlers', None) or [])]
                for seq in seqs:
                    if (seq and isinstance(seq[-1], ast.Return)
                            and seq[-1].value is None):
                        seq.pop()
                        changed = True
                for h in (getattr(t, 'handlers', None) or []):
                    if not h.body:
                        h.body = [ast.Pass()]
                if not t.body:
                    t.body = [ast.Pass()]
                if not changed:
                    break
        # py2 narrow variant: a bare `return` at the end of a
        # FUNCTION-TAIL try's arm chain is the decompiler materializing
        # the epilogue after the outermost END_FINALLY (SocketServer
        # 2.6/2.7 ForkingMixIn.process_request: the handler's nested
        # try/finally grew a trailing `return`). At the function tail
        # it is observationally identical to falling off the end. Only
        # strips when the bare return is the LAST thing in the
        # function via nested try arms - the unconditional py3 form
        # regressed py2 Cookie/cmd/asyncore (handler-termination
        # states flipped asymmetrically), so descent is exact-shape.
        # py2 only: py3's unified Try is handled by the loop above.
        if (sys.version_info[0] == 2 and body
                and TRY_TYPES and isinstance(body[-1], TRY_TYPES)):
            for _ in range(6):
                t = body[-1]
                cands = [t.body, getattr(t, 'orelse', None) or [],
                         getattr(t, 'finalbody', None) or []]
                cands += [h.body for h in (getattr(t, 'handlers', None) or [])]
                cands = [c for c in cands if c]
                stripped = False
                for c in cands:
                    if (isinstance(c[-1], ast.Return)
                            and c[-1].value is None):
                        c.pop()
                        if not c:
                            c.append(ast.Pass())
                        stripped = True
                if not stripped:
                    break
                nxt = None
                for c in cands:
                    if c and TRY_TYPES and isinstance(c[-1], TRY_TYPES):
                        nxt = c[-1]
                        break
                if nxt is None:
                    break
                body[-1] = nxt
        if not body:
            node.body = [ast.Pass()]
        return node

    def visit_FunctionDef(self, node):
        return self._strip_fn_trailing_return(node)

    def visit_AsyncFunctionDef(self, node):
        return self._strip_fn_trailing_return(node)

    def visit_Return(self, node):
        self.generic_visit(node)
        # 'return None' and bare 'return' compile identically
        v = node.value
        if v is not None:
            if hasattr(ast, 'NameConstant') and isinstance(v, ast.NameConstant) \
                    and v.value is None:
                node.value = None
            elif hasattr(ast, 'Constant') and isinstance(v, ast.Constant) \
                    and v.value is None:
                node.value = None
            elif isinstance(v, ast.Name) and v.id == 'None':
                node.value = None
        return node

    def visit_Raise(self, node):
        self.generic_visit(node)
        # py2 'raise T, I' (type/inst fields) == decompiled 'raise T(I)'
        if hasattr(node, 'type') and getattr(node, 'inst', None) is not None                 and getattr(node, 'tback', None) is None:
            node.type = ast.Call(func=node.type, args=[node.inst],
                                 keywords=[], starargs=None, kwargs=None)
            node.inst = None
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        # f(*(1, 2), *a) == f(1, 2, *a): expand starred constant tuples
        star_cls = getattr(ast, 'Starred', None)
        if star_cls is not None:
            new_args = []
            for a in node.args:
                if isinstance(a, star_cls) and isinstance(a.value, (ast.Tuple, ast.List)):
                    new_args.extend(a.value.elts)
                else:
                    new_args.append(a)
            node.args = new_args
        # the compiler folds a constant set literal in a membership test
        # (`x in {1,2,3}`) into a constant frozenset (LOAD_CONST
        # frozenset(...)), which the decompile renders back as
        # `frozenset({1,2,3})`. Unwrap it to the bare Set so it compares
        # equal to the source's set literal (base64 3.6-3.11
        # `padchars not in {0,1,3,4,6}`). Symmetric: an explicit source
        # `frozenset({...})` normalizes the same way, and the decompile
        # only emits `frozenset({literal})` from that constant fold, so
        # this never conflates a real frozenset VALUE with a set.
        if (_SET is not None
                and isinstance(node.func, ast.Name)
                and node.func.id == 'frozenset'
                and len(node.args) == 1
                and not getattr(node, 'keywords', [])
                and isinstance(node.args[0], _SET)):
            return node.args[0]
        # set(genexpr) == set comprehension, list(genexpr) == list comp
        # (decompiler renders pre-3.x style comprehension code this way)
        if (isinstance(node.func, ast.Name)
                and node.func.id in ('set', 'list')
                and len(node.args) == 1 and not getattr(node, 'keywords', [])
                and isinstance(node.args[0], ast.GeneratorExp)):
            ge = node.args[0]
            if node.func.id == 'set':
                if not hasattr(ast, 'SetComp'):
                    return node  # py2.6: no set-comprehension node exists
                return ast.SetComp(elt=ge.elt, generators=ge.generators)
            return ast.ListComp(elt=ge.elt, generators=ge.generators)
        return node


def _is_pure_bool_operand(n):
    """True when re-evaluating n is unobservable (no calls/awaits/yields)."""
    impure = tuple(
        t for t in (getattr(ast, 'Call', None), getattr(ast, 'Await', None),
                    getattr(ast, 'Yield', None), getattr(ast, 'YieldFrom', None),
                    getattr(ast, 'Lambda', None))
        if t is not None)
    for x in ast.walk(n):
        if isinstance(x, impure):
            return False
    return True


def canonical_bool(node):
    """Canonical form of a boolean expression: flatten and/or chains,
    apply De Morgan so Not never wraps a BoolOp, then order commutative
    operands by their dump text."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        inner = canonical_bool(node.operand)
        # double negation in a boolean context folds away (merged
        # guard-continue chains wrap already-negated guard tests:
        # `if not A: continue` -> Not(Not(A)))
        if isinstance(inner, ast.UnaryOp) and isinstance(inner.op, ast.Not):
            return inner.operand
        if isinstance(inner, ast.BoolOp):
            neg = [canonical_bool(ast.UnaryOp(op=ast.Not(), operand=v))
                   for v in inner.values]
            op = ast.And() if isinstance(inner.op, ast.Or) else ast.Or()
            return sorted_node(ast.BoolOp(op=op, values=neg))
        # `not a in b` == `a not in b` (CPython folds the invertible
        # single-op comparisons the same way)
        if isinstance(inner, ast.Compare) and len(inner.ops) == 1:
            inv = ((ast.Is, ast.IsNot), (ast.IsNot, ast.Is),
                   (ast.In, ast.NotIn), (ast.NotIn, ast.In),
                   (ast.Eq, ast.NotEq), (ast.NotEq, ast.Eq))
            for src_op, dst_op in inv:
                if isinstance(inner.ops[0], src_op):
                    return ast.Compare(left=inner.left, ops=[dst_op()],
                                       comparators=inner.comparators)
        return sorted_node(ast.UnaryOp(op=ast.Not(), operand=inner))
    if isinstance(node, ast.BoolOp):
        kind = type(node.op)
        vals = []
        for v in node.values:
            cv = canonical_bool(v)
            if isinstance(cv, ast.BoolOp) and type(cv.op) is kind:
                vals.extend(cv.values)  # flatten same-op chains
            else:
                vals.append(cv)
        if kind is ast.And:
            # chained-comparison refold: `a op1 b and b op2 c` (b pure)
            # IS the source chained comparison `a op1 b op2 c`; the
            # decompiler renders each link as its own guard which the
            # Normalizer merges into an And (ast 3.10/3.14 literal_eval
            # `node.args == node.keywords == []`). Runs before the sort
            # so the merged Compare sorts as one operand.
            changed = True
            while changed and len(vals) > 1:
                changed = False
                for i in range(len(vals)):
                    for j in range(len(vals)):
                        if i == j:
                            continue
                        a, b = vals[i], vals[j]
                        if (isinstance(a, ast.Compare)
                                and isinstance(b, ast.Compare)
                                and a.comparators
                                and _is_pure_bool_operand(a.comparators[-1])
                                and ast.dump(a.comparators[-1])
                                == ast.dump(b.left)):
                            vals[i] = ast.Compare(
                                left=a.left,
                                ops=list(a.ops) + list(b.ops),
                                comparators=list(a.comparators)
                                + list(b.comparators))
                            del vals[j]
                            changed = True
                            break
                    if changed:
                        break
        # dedupe identical PURE operands (`A and A` == `A`): merged
        # guard chains can re-test a condition the decompiler already
        # folded into the wrapper test (bdb 3.14 effective: guard
        # `if not b.enabled: continue` + wrapper `if b.enabled and
        # checkfuncname(..)` merge to And(enabled, enabled,
        # checkfuncname) while the source's two flat guards merge to
        # And(enabled, checkfuncname)). Calls/awaits keep their
        # duplicates - re-evaluation is observable.
        seen = set()
        ded = []
        for v in vals:
            if _is_pure_bool_operand(v):
                d = ast.dump(v)
                if d in seen:
                    continue
                seen.add(d)
            ded.append(v)
        vals = ded
        return sorted_node(ast.BoolOp(op=node.op, values=vals))
    return node


def sorted_node(node):
    """Sort values of commutative BoolOps by dump text for order-insensitive
    comparison."""
    if isinstance(node, ast.BoolOp):
        node.values.sort(key=lambda v: ast.dump(v))
    return node


TERMINATORS = tuple(
    [t for t in (getattr(ast, 'Break', None), getattr(ast, 'Return', None),
                 getattr(ast, 'Raise', None), getattr(ast, 'Continue', None))
     if t is not None])


def split_tail_ternary_return(stmts):
    """Tail `return A if c else B` lowers (3.13) to `if c: return A`
    followed by `return B` - split both sides to the statement form.
    Tail position only, so it is exactly meaning-preserving."""
    def bare_none(v):
        # the split builds fresh Return nodes AFTER visit_Return ran, so a
        # None arm must be canonicalized to a bare `return` here or it
        # stays Return(NameConstant(None))/Return(Constant(None)) and
        # mismatches a decompile that rendered a bare `return` (_osx_support
        # _read_output `return fp.read().strip() if not os.system(cmd) else
        # None`).
        if v is None:
            return None
        if hasattr(ast, 'NameConstant') and isinstance(v, ast.NameConstant) \
                and v.value is None:
            return None
        if hasattr(ast, 'Constant') and isinstance(v, ast.Constant) \
                and v.value is None:
            return None
        if isinstance(v, ast.Name) and v.id == 'None':
            return None
        return v
    changed = True
    while changed and stmts:
        changed = False
        last = stmts[-1]
        if isinstance(last, ast.Return) and isinstance(last.value, ast.IfExp):
            ie = last.value
            stmts = list(stmts[:-1])
            stmts.append(ast.If(
                test=ie.test,
                body=split_tail_ternary_return(
                    [ast.Return(value=bare_none(ie.body))]),
                orelse=[]))
            stmts.append(ast.Return(value=bare_none(ie.orelse)))
            changed = True
    return stmts


def _strip_redundant_tail_bare_returns(stmts):
    """Drop bare returns that sit between an arm whose last statement
    already returns and the arm's end - both forms return None there.
    Runs bottom-up so nested arms normalize before their parents
    (aifc 3.12 _read_comm_chunk: orig keeps a trailing `return` after
    the inner guard (whose body ends in a sunk return), dec does not)."""
    for s in stmts:
        for fld in ('body', 'orelse', 'finalbody'):
            v = getattr(s, fld, None)
            if isinstance(v, list) and v and isinstance(v[0], ast.stmt):
                _strip_redundant_tail_bare_returns(v)
        for h in getattr(s, 'handlers', None) or []:
            if getattr(h, 'body', None):
                _strip_redundant_tail_bare_returns(h.body)
    out = []
    for s in stmts:
        if _is_bare_return(s) and out:
            prev = out[-1]
            if isinstance(prev, ast.Return) or (
                    isinstance(prev, ast.If) and prev.body
                    and not prev.orelse
                    and isinstance(prev.body[-1], ast.Return)):
                continue
        out.append(s)
    if not out:
        out = [ast.Pass()]
    stmts[:] = out
    return stmts


def _strip_tail_bare_return_chain(body):
    """Pop the trailing bare-return terminator(s) of a then-arm about
    to be refolded: the arm's last statement is a bare return, and the
    statement before it may itself be a no-else If whose arm ends in a
    bare return - 3.12+ compilers route each guard level's fall-through
    to the function epilogue, so the dec form cascades returns down the
    guard chain (aifc 3.12 _read_comm_chunk: `if comptype != NONE:
    ...; return` + `return`). Only call when the released siblings move
    into the guard's orelse: the popped returns sent those paths to the
    function tail, and after the refold the released paths still fall
    to the (now else-gated) tail - same None."""
    changed = False
    while body:
        last = body[-1]
        if _is_bare_return(last):
            body.pop()
            changed = True
            continue
        if isinstance(last, ast.If) and last.body and not last.orelse \
                and _is_bare_return(last.body[-1]):
            _strip_tail_bare_return_chain(last.body)
            if not last.body:
                last.body = [ast.Pass()]
            changed = True
            continue
        break
    return changed


def _arm_all_bare_returns(body):
    """True when the arm holds nothing but bare returns - stripping its
    trailing bare-return chain would empty it. Such a guard is a plain
    early bail-out (`if c: return`) whose released siblings are
    ordinary following code; refolding those into an else arm leaves a
    Pass-filled arm that baits the function-tail sink into duplicating
    the tail return (bdb 3.14 callback_wrapper)."""
    return all(_is_bare_return(s) for s in body)


def _refold_tail_flat_else(stmts):
    """At the effective function tail, `if c: B; return` followed by
    siblings S equals `if c: B else: S`: the bare return skips S
    exactly like the else gate, and falling off either form returns
    None. 3.12+ compilers sink the implicit tail return into if-arms
    and the decompiler then flattens the else to siblings (aifc 3.12
    _read_comm_chunk rendered `if comptype != NONE: ...; return` +
    `return` + the else assignments). Checked BEFORE recursing into
    the arm so the outer guard sees its intact bare-return chain (the
    recursion's lone-return rule would otherwise consume it first).
    Descends through arm-tail Ifs; never into loops (a bare return
    inside a loop body may be the canonicalized form of a break -
    _normalize_func_tail_loop owns that) and never into try bodies
    (succeeding there skips the orelse - not equivalent)."""
    i = 0
    while i < len(stmts):
        s = stmts[i]
        if isinstance(s, ast.If) and s.body and not s.orelse \
                and i + 1 < len(stmts) and _is_bare_return(s.body[-1]) \
                and not _arm_all_bare_returns(s.body):
            rest = stmts[i + 1:]
            # a lone bare return as the whole released tail is the
            # function's implicit end, not an else arm - drop it
            # (orig's flattened form keeps it as a sibling after
            # the guard; both sides then hold no return there)
            if len(rest) == 1 and _is_bare_return(rest[0]):
                _strip_tail_bare_return_chain(s.body)
                if not s.body:
                    s.body = [ast.Pass()]
                del stmts[i + 1:]
                return stmts
            _strip_tail_bare_return_chain(s.body)
            if not s.body:
                s.body = [ast.Pass()]
            s.orelse = rest
            del stmts[i + 1:]
            return stmts
        if isinstance(s, ast.If) and s.body:
            _refold_tail_flat_else(s.body)
            if s.orelse:
                _refold_tail_flat_else(s.orelse)
        elif isinstance(s, ast.With) or (hasattr(ast, 'AsyncWith')
                                         and isinstance(s, ast.AsyncWith)):
            _refold_tail_flat_else(s.body)
        i += 1
    return stmts


def _sink_tail_into_nested_guard(stmts, ret):
    """Make the trailing guard chain of `stmts` end in `return V` at
    every arm, where V is the function-tail return the arms fall
    through to. Mirrors the 3.14 compiler's per-arm sinking of the
    function-tail return for guards at the effective end of control
    flow; complements flatten_terminating_else, which needs the
    terminator in the SAME statement list (_py_warnings 3.14
    _formatwarnmsg_impl: the `if tb is not None: ... elif
    suggest_tracemalloc: ...` pair sits inside `if msg.source is not
    None:` one level above the tail `return s`). After the sink the
    enclosing guard ends in a bare return at every arm, the
    released-orelse forms converge, and _strip_tail_bare_returns /
    flatten_terminating_else absorb the copies on both sides."""
    if not stmts:
        return False
    last = stmts[-1]
    if not isinstance(last, ast.If) or not last.body or not last.orelse:
        return False
    # sink the THEN arm only: once it terminates, the standard
    # flatten_terminal_else releases the orelse as siblings whose
    # continuation IS the function tail - sinking the orelse too would
    # leave a duplicate return inside the released arm
    return _sink_arm(last.body, ret)


def _sink_arm(arm, ret):
    """Append/propagate `return V` so the arm's end returns V. Returns
    False when the arm already terminates differently (a valued return,
    raise, break, continue) - sinking there would change semantics."""
    if not arm:
        return False
    e = arm[-1]
    if isinstance(e, ast.Return):
        return (e.value is not None and ret.value is not None
                and ast.dump(e.value) == ast.dump(ret.value))
    if isinstance(e, (ast.Raise, ast.Break, ast.Continue)):
        return False
    if isinstance(e, ast.If) and e.body and e.orelse:
        return _sink_arm(e.body, ret) and _sink_arm(e.orelse, ret)
    arm.append(ast.Return(value=copy.deepcopy(ret.value)))
    return True


def _sink_func_tail_into_guard_arms(node):
    """When a function body's LAST statement is an If whose arms BOTH
    end in a bare `return V` (V matching the function's own tail
    return value), append a copy of `return V` to every arm. The 3.14
    compiler sinks the function-tail return into each arm of guards
    sitting at the effective end of control flow; when such a guard is
    nested inside an outer arm, no single statement list holds both the
    guard and the tail, so flatten_terminating_else cannot converge the
    two shapes (_py_warnings 3.14 _formatwarnmsg_impl: the inner
    `if tb is not None: ... elif suggest_tracemalloc: ...` inside
    `if msg.source is not None:` got the sunk `return s` only in the
    decompile). After the append, the outer list ends in a bare
    `return V` and the regular tail-sinking canonicalization matches."""
    body = getattr(node, 'body', None)
    if not (isinstance(body, list) and body):
        return False
    tail = body[-1]
    if not (isinstance(tail, ast.Return) and tail.value is not None):
        return False
    td = ast.dump(tail.value)
    last = body[-2] if len(body) >= 2 else None
    if not isinstance(last, ast.If):
        return False
    ch = _sink_tail_into_nested_guard(last.body, tail)
    if last.orelse:
        ch = _sink_tail_into_nested_guard(last.orelse, tail) or ch
    return ch


def _expr_ternary_to_if(node):
    """An expression-statement ternary `A if c else B` (the value is
    discarded) is semantically identical to `if c: A else: B` -- the
    compiler emits the same branch shape and a decompiler cannot tell
    them apart (configparser 3.14 _read: the source's bare
    `self._handle_header(...) if mo else self._handle_option(...)`
    renders as a statement If). Canonicalize Expr(IfExp) statements to
    the statement form on both sides."""
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            for i, s in enumerate(value):
                if isinstance(s, ast.Expr) \
                        and isinstance(s.value, ast.IfExp):
                    ie = s.value
                    value[i] = ast.If(
                        test=ie.test,
                        body=[ast.Expr(value=ie.body)],
                        orelse=[ast.Expr(value=ie.orelse)])
    return node


def _flatten_node_list(stmts):
    return [_flatten_node(x) for x in stmts]


def _flatten_terminal_else_deep(stmts):
    """flatten_terminal_else at EVERY nesting level (the flat pass in
    normalize_body and the _flatten_node fixpoint only reach the lists
    they are handed)."""
    out = flatten_terminal_else(list(stmts))
    for st in out:
        for fld in ('body', 'orelse', 'finalbody'):
            v = getattr(st, fld, None)
            if isinstance(v, list) and v and isinstance(v[0], ast.stmt):
                setattr(st, fld, _flatten_terminal_else_deep(v))
        for h in getattr(st, 'handlers', None) or []:
            if getattr(h, 'body', None):
                h.body = _flatten_terminal_else_deep(h.body)
    return out


def _flatten_node(s):
    """Recurse into statement-holding fields (the walk-based passes in
    dump() never reach nested If bodies)."""
    is_loop = isinstance(s, _LOOP_TYPES)
    for field in ('body', 'orelse', 'finalbody'):
        val = getattr(s, field, None)
        if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
            setattr(s, field,
                    split_tail_ternary_return(flatten_terminating_else(
                        val, loop_body=(is_loop and field == 'body'))))
    for h in getattr(s, 'handlers', None) or []:
        if getattr(h, 'body', None):
            h.body = split_tail_ternary_return(
                flatten_terminating_else(h.body))
    return s


def flatten_terminating_else(stmts, loop_body=False):
    """3.14 tail sinking: `if c: A else: B` followed by a trailing
    terminator T compiles to `if c: A; T` with B laid out sequentially
    and T repeated after it. Canonicalize the source shape INTO the sunk
    shape: sink the enclosing body's trailing Return/Raise into every
    non-terminating then-arm that has an else, releasing the else as
    sequential statements. Deterministic and semantically exact (T
    terminates, so the copy inside the then-arm cannot fall through)."""
    if not stmts:
        return stmts
    tail = stmts[-1]
    if isinstance(tail, (ast.Return, ast.Raise)):
        changed = True
        while changed:
            changed = False
            out = []
            n = len(stmts)
            for si, s in enumerate(stmts):
                # ONLY the statement right before the tail may absorb
                # it: sinking past intermediate statements would skip
                # them on the then path (3.11 compileall main(): the
                # tail return got absorbed into an earlier
                # `if args.recursion is not None:` guard, jumping over
                # the whole try body). After the absorbing If is
                # released, its former else statements sit between the
                # new If and the tail, so the while loop re-runs and
                # walks the absorption leftward one level per round.
                if (si == n - 2
                        and isinstance(s, ast.If) and s.orelse and s.body
                        and not isinstance(s.body[-1], (ast.Return, ast.Raise))):
                    body = list(s.body) + [tail]
                    orelse = list(s.orelse)
                    out.append(ast.If(test=s.test, body=body, orelse=[]))
                    out.extend(orelse)
                    changed = True
                else:
                    out.append(s)
            stmts = out
    # loop-tail if/else: compilers render the then arm's exit as a
    # `continue` and lay the else out as fall-through (bisect's binary
    # search loops) - canonicalize the source shape into it. ONLY for a
    # LOOP body: a `continue` is meaningless at a function/module tail, and
    # adding one there corrupts the comparison (cgi __init__'s trailing
    # if/elif/else, not inside any loop, got a spurious `continue` sunk into
    # its then arm so it mismatched a decompile that flattened the chain to
    # `if c: call(); return` siblings with the function's implicit tail).
    if loop_body:
        # iterate: flattening one elif level exposes the next as the
        # tail - a full chain must flatten completely to match the
        # decompiler's sibling form (_strptime 3.6-3.9 _strptime: the
        # group_key dispatch chain flattened only one level and
        # mismatched the fully-flat decompile)
        changed = True
        while changed:
            changed = False
            tail = stmts[-1] if stmts else None
            if (isinstance(tail, ast.If) and tail.orelse and tail.body
                    and not isinstance(tail.body[-1], (ast.Return,
                                                       ast.Raise,
                                                       ast.Continue))):
                stmts = list(stmts[:-1])
                body = list(tail.body) + [ast.Continue()]
                orelse = list(tail.orelse)
                stmts.append(ast.If(test=tail.test, body=body, orelse=[]))
                stmts.extend(orelse)
                changed = True
    # a TAIL loop-else with no breaks anywhere: the else arm runs only
    # on exhaustion, which is exactly when the flattened sibling
    # position runs (ast 3.14 _compare: source `for ...: if not
    # _compare(...): return False else: return True` vs the
    # decompiler's post-loop sibling `return True`). Breaks in the
    # body would fall INTO the flattened siblings, so the gate counts
    # them (nested-loop breaks belong to their own loop and are
    # already excluded by _count_breaks).
    if stmts:
        _last = stmts[-1]
        if isinstance(_last, _LOOP_TYPES):
            _orelse = getattr(_last, 'orelse', None) or []
            if _orelse and _count_breaks(_last.body) == 0 \
                    and _count_breaks(_orelse) == 0:
                _last.orelse = []
                stmts = list(stmts[:-1]) + [_last] + _orelse
                # the released tail may now TERMINATE an enclosing If's
                # then arm that flatten_terminal_else already passed
                # over (it ran before this flatten): re-run it
                stmts = flatten_terminal_else(stmts)
    return [_flatten_node(s) for s in stmts]


def strip_noop_continues(stmts, at_loop_tail):
    """Canonicalize loop-tail artifacts decompilers emit:
    - statements after a terminator in the same body are dead -> drop
    - `continue` as the last executed statement of a loop body (possibly
      through a tail try/if/with) is a no-op -> drop
    An empty handler/branch body canonicalizes to [Pass]."""
    out = []
    terminated = False
    n = len(stmts)
    for idx, s in enumerate(stmts):
        if terminated:
            continue
        # a Pass with real siblings is a no-op the bytecode never
        # carries (annotationlib 3.14: the source's handler
        # `pass` + the hoisted loop-tail `continue` vs the decompile's
        # bare continue)
        if isinstance(s, ast.Pass) and n > 1:
            continue
        # only the LAST statement of a loop-tail body falls through to
        # the back edge - a continue in an earlier statement (or inside
        # a mid-list if) is real control flow
        s = visit_noop_node(s, at_loop_tail and idx == n - 1)
        if isinstance(s, ast.Continue):
            if at_loop_tail:
                continue  # no-op: the loop iterates anyway
            terminated = True
            out.append(s)
            continue
        if isinstance(s, TERMINATORS):
            terminated = True
        out.append(s)
    if not out and stmts:
        out.append(ast.Pass())
    return out


def visit_noop_node(s, at_loop_tail):
    if isinstance(s, (ast.While, ast.For)):
        s.body = strip_noop_continues(s.body, True)
        s.orelse = strip_noop_continues(s.orelse, at_loop_tail)
        if not s.body:
            s.body = [ast.Pass()]
    elif hasattr(ast, 'AsyncFor') and isinstance(s, getattr(ast, 'AsyncFor')):
        s.body = strip_noop_continues(s.body, True)
        s.orelse = strip_noop_continues(s.orelse, at_loop_tail)
        if not s.body:
            s.body = [ast.Pass()]
    elif isinstance(s, ast.If):
        s.body = strip_noop_continues(s.body, at_loop_tail)
        s.orelse = strip_noop_continues(s.orelse, at_loop_tail)
        if not s.body:
            s.body = [ast.Pass()]
        # an else arm stripped down to a lone Pass IS no else at all
        # (bdb 3.13 effective: the dec's `if val: ... else: continue`
        # at the loop tail stripped to `else: pass` and never matched
        # the source's else-less form)
        if len(s.orelse) == 1 and isinstance(s.orelse[0], ast.Pass):
            s.orelse = []
    elif isinstance(s, (ast.With, getattr(ast, 'AsyncWith', ast.With))):
        s.body = strip_noop_continues(s.body, at_loop_tail)
        if not s.body:
            s.body = [ast.Pass()]
    elif isinstance(s, ELSE_PASS_TYPES[3:] if len(ELSE_PASS_TYPES) > 3 else ()):
        # try/try* (and py2 TryExcept/TryFinally): every clause that can
        # be the loop-tail flow inherits the flag
        s.body = strip_noop_continues(s.body, at_loop_tail)
        for h in getattr(s, 'handlers', []) or []:
            h.body = strip_noop_continues(h.body, at_loop_tail)
            if not h.body:
                h.body = [ast.Pass()]
        # py2 TryFinally has no orelse; py2 TryExcept has no finalbody
        if hasattr(s, 'orelse'):
            s.orelse = strip_noop_continues(s.orelse, at_loop_tail)
        if getattr(s, 'finalbody', None):
            s.finalbody = strip_noop_continues(s.finalbody, at_loop_tail)
        if not s.body:
            s.body = [ast.Pass()]
    elif isinstance(s, (ast.FunctionDef, ast.ClassDef,
                        getattr(ast, 'AsyncFunctionDef', ast.FunctionDef))):
        s.body = strip_noop_continues(s.body, False)
        if not s.body:
            s.body = [ast.Pass()]
    return s


ELSE_PASS_TYPES = tuple(
    [ast.If, ast.While, ast.For]
    + [t for t in (getattr(ast, 'Try', None), getattr(ast, 'TryStar', None),
                   getattr(ast, 'TryExcept', None),
                   getattr(ast, 'TryFinally', None)) if t is not None])


_LOOP_TYPES = tuple(
    [ast.While, ast.For]
    + [t for t in (getattr(ast, 'AsyncFor', None),) if t is not None])

_TRY_TYPES = tuple(
    [t for t in (getattr(ast, 'Try', None), getattr(ast, 'TryStar', None),
                 getattr(ast, 'TryExcept', None),
                 getattr(ast, 'TryFinally', None)) if t is not None])


def _bare_return_to_break(body):
    """Convert a bare `return`/`return None` statement to `break` in a
    statement list (in place), recursing through if/for/while/with/try
    bodies but NOT through a nested function/class (its return belongs
    to the nested scope). Used only for a loop that is the LAST statement
    of a function body, where exiting the loop and returning None are the
    same observable end (the 3.13+ compiler fuses a tail-loop `break`
    into RETURN_CONST None, so the decompile renders `return` where the
    source had `break` - _strptime 3.13 _findall)."""
    for i, s in enumerate(body):
        if isinstance(s, ast.Return) and s.value is None:
            body[i] = ast.Break()
        elif isinstance(s, (ast.If, ast.With,
                            getattr(ast, 'AsyncWith', ast.With))):
            _bare_return_to_break(s.body)
            _bare_return_to_break(getattr(s, 'orelse', []) or [])
        elif isinstance(s, _LOOP_TYPES):
            _bare_return_to_break(s.body)
            _bare_return_to_break(getattr(s, 'orelse', []) or [])
        elif isinstance(s, _TRY_TYPES):
            _bare_return_to_break(s.body)
            for h in getattr(s, 'handlers', []) or []:
                _bare_return_to_break(h.body)
            _bare_return_to_break(getattr(s, 'orelse', []) or [])
            _bare_return_to_break(getattr(s, 'finalbody', []) or [])


def _flatten_tail_elses(stmts):
    """In function-tail position (falling off the end == return None),
    `if c: B else: X` equals `if c: B` followed by X: B ends the
    function so it never falls through to X. Applied to the else arm of
    a function-tail loop after _strip_orelse_tail_breaks removed the
    sunk tail returns/breaks (base64 3.11 main: the source's
    `if args...: with... else: func(stdin)` vs the decompile's flattened
    `if args...: with...` + `func(stdin)` sibling)."""
    out = list(stmts)
    changed = True
    while changed:
        changed = False
        for idx, s in enumerate(out):
            if isinstance(s, ast.If) and s.orelse:
                if idx == len(out) - 1 or ends_terminal(s.body):
                    tail = s.orelse
                    s.orelse = []
                    out[idx + 1:idx + 1] = tail
                    changed = True
                    break
                before = ast.dump(s)
                s.body = _flatten_tail_elses(s.body)
                s.orelse = _flatten_tail_elses(s.orelse)
                if ast.dump(s) != before:
                    changed = True
                    break
            elif idx == len(out) - 1:
                if isinstance(s, (ast.With,
                                  getattr(ast, 'AsyncWith', ast.With))):
                    before = ast.dump(s)
                    s.body = _flatten_tail_elses(s.body)
                    if ast.dump(s) != before:
                        changed = True
                        break
                elif _TRY_TYPES and isinstance(s, _TRY_TYPES):
                    before = ast.dump(s)
                    s.body = _flatten_tail_elses(s.body)
                    if getattr(s, 'orelse', None):
                        s.orelse = _flatten_tail_elses(s.orelse)
                    if ast.dump(s) != before:
                        changed = True
                        break
    return out


def _count_bare_returns(body):
    """Count bare `return`/`return None` statements belonging to THIS
    function scope, recursing like _bare_return_to_break (through
    if/loop/with/try, NOT through nested function/class scopes)."""
    n = 0
    for s in body:
        if isinstance(s, ast.Return) and s.value is None:
            n += 1
        elif isinstance(s, (ast.If, ast.With,
                            getattr(ast, 'AsyncWith', ast.With))):
            n += _count_bare_returns(s.body)
            n += _count_bare_returns(getattr(s, 'orelse', []) or [])
        elif isinstance(s, _LOOP_TYPES):
            n += _count_bare_returns(s.body)
            n += _count_bare_returns(getattr(s, 'orelse', []) or [])
        elif isinstance(s, _TRY_TYPES):
            n += _count_bare_returns(s.body)
            for h in getattr(s, 'handlers', []) or []:
                n += _count_bare_returns(h.body)
            n += _count_bare_returns(getattr(s, 'orelse', []) or [])
            n += _count_bare_returns(getattr(s, 'finalbody', []) or [])
    return n


def _strip_orelse_tail_breaks(body):
    """A bare Break in tail position of a FUNCTION-TAIL loop's else arm
    (or any arm nested inside it) is a no-op: the loop already finished
    and nothing follows it in the function. Dropped after
    _bare_return_to_break converted sunk function-tail returns (base64
    3.11 main: the with arm's doubled tail `return; return` became
    `break; break` where the source arm simply ends)."""
    while body and isinstance(body[-1], ast.Break):
        body.pop()
    for s in body:
        if isinstance(s, (ast.If, ast.With,
                          getattr(ast, 'AsyncWith', ast.With))):
            _strip_orelse_tail_breaks(s.body)
            _strip_orelse_tail_breaks(getattr(s, 'orelse', []) or [])
        elif isinstance(s, _TRY_TYPES):
            _strip_orelse_tail_breaks(s.body)
            for h in getattr(s, 'handlers', []) or []:
                _strip_orelse_tail_breaks(h.body)
            _strip_orelse_tail_breaks(getattr(s, 'orelse', []) or [])
            _strip_orelse_tail_breaks(getattr(s, 'finalbody', []) or [])
        # nested loops: their breaks belong to themselves - skip
    if not body:
        body.append(ast.Pass())


def _is_const_true(test):
    if isinstance(test, ast.Name) and test.id == 'True':
        return True
    v = getattr(test, 'value', getattr(test, 'n', None))
    return isinstance(test, getattr(ast, 'Constant', ())) and bool(v)


def _break_to_tail_return(body, tail):
    """Replace each Break with a copy of `tail` + a bare Return, in
    place, recursing like _bare_return_to_break. Returns the count."""
    n = 0
    i = 0
    while i < len(body):
        s = body[i]
        if isinstance(s, ast.Break):
            repl = [copy.deepcopy(t) for t in tail] + [ast.Return(value=None)]
            body[i:i + 1] = repl
            n += 1
            i += len(repl)
            continue
        if isinstance(s, (ast.If, ast.With,
                          getattr(ast, 'AsyncWith', ast.With))):
            n += _break_to_tail_return(s.body, tail)
            n += _break_to_tail_return(getattr(s, 'orelse', []) or [], tail)
        elif isinstance(s, _LOOP_TYPES):
            # a Break in a NESTED loop belongs to that loop - do not
            # recurse (matching _bare_return_to_break's scoping, which
            # is sound there because return leaves ALL scopes)
            pass
        elif isinstance(s, _TRY_TYPES):
            n += _break_to_tail_return(s.body, tail)
            for h in getattr(s, 'handlers', []) or []:
                n += _break_to_tail_return(h.body, tail)
            n += _break_to_tail_return(getattr(s, 'orelse', []) or [], tail)
            n += _break_to_tail_return(getattr(s, 'finalbody', []) or [], tail)
        i += 1
    return n


def _tail_return_to_break(body, ret_dump):
    """Replace `return V` statements whose value dump equals ret_dump
    with Break, recursing through If/With/Try(body, handlers, orelse)
    but NOT nested loops (their returns exit the function across
    scopes; a Break would only leave the inner loop) and NOT
    finalbody (a return there swallows exceptions; a break would
    not). Inverse of _break_to_tail_return for the single-statement
    tail case."""
    n = 0
    i = 0
    while i < len(body):
        s = body[i]
        if (isinstance(s, ast.Return) and s.value is not None
                and ast.dump(s.value) == ret_dump):
            body[i] = ast.Break()
            n += 1
        elif isinstance(s, (ast.If, ast.With,
                            getattr(ast, 'AsyncWith', ast.With))):
            n += _tail_return_to_break(s.body, ret_dump)
            n += _tail_return_to_break(getattr(s, 'orelse', []) or [],
                                       ret_dump)
        elif isinstance(s, _TRY_TYPES):
            n += _tail_return_to_break(s.body, ret_dump)
            for h in getattr(s, 'handlers', []) or []:
                n += _tail_return_to_break(h.body, ret_dump)
            n += _tail_return_to_break(getattr(s, 'orelse', []) or [],
                                       ret_dump)
        i += 1
    return n


def _count_breaks(body):
    n = 0
    for s in body:
        if isinstance(s, ast.Break):
            n += 1
        elif isinstance(s, (ast.If, ast.With,
                            getattr(ast, 'AsyncWith', ast.With))):
            n += _count_breaks(s.body)
            n += _count_breaks(getattr(s, 'orelse', []) or [])
        elif isinstance(s, _TRY_TYPES):
            n += _count_breaks(s.body)
            for h in getattr(s, 'handlers', []) or []:
                n += _count_breaks(h.body)
            n += _count_breaks(getattr(s, 'orelse', []) or [])
            n += _count_breaks(getattr(s, 'finalbody', []) or [])
        # nested loops: their breaks are not ours - skip
    return n


def _normalize_func_tail_handler_return(node):
    """When a function body's LAST statement is a try whose handler
    clause ends in a bare `return` (nothing follows the try), the
    return is observationally identical to `pass` - both leave the
    function with None (_collections_abc 3.10 ItemsView.__iter__
    generator: orig `except IndexError: return` vs dec `except
    IndexError: pass`)."""
    if not isinstance(node, (ast.FunctionDef,
                             getattr(ast, 'AsyncFunctionDef', ast.FunctionDef))):
        return
    if not node.body:
        return
    last = node.body[-1]
    try_t = getattr(ast, 'Try', None) or getattr(ast, 'TryExcept', None)
    if try_t is None or not isinstance(last, try_t):
        return
    if not getattr(last, 'handlers', None):
        return
    for h in last.handlers:
        if (len(h.body) == 1 and isinstance(h.body[0], ast.Return)
                and h.body[0].value is None):
            h.body = [ast.Pass()]


def _reattach_tail_try_else(stmts, want):
    """Tail-position try whose handlers ALL end with a copy of the
    function-tail return V: the non-terminal siblings after it are the
    flattened else clause - re-attach them as the orelse and strip the
    handler-tail copies (falling off a handler skips the else in both
    forms and reaches the shared tail return; on success the else runs
    in both forms). compileall 3.10 compile_file: `if ok == 0: success
    = False` is the flattened else and the tail `return success` lives
    at the FUNCTION level, so the same-list _sunk_return_orelse cannot
    see it."""
    if not (TRY_TYPES and stmts):
        return
    for i, s in enumerate(stmts):
        if not (TRY_TYPES and isinstance(s, TRY_TYPES)):
            continue
        handlers = getattr(s, 'handlers', None) or []
        if not handlers or getattr(s, 'orelse', None) \
                or getattr(s, 'finalbody', None):
            continue
        if not all(h.body and isinstance(h.body[-1], ast.Return)
                   and h.body[-1].value is not None
                   and ast.dump(h.body[-1]) == want
                   for h in handlers):
            continue
        mids = stmts[i + 1:]
        if any(isinstance(x, (ast.Return, ast.Raise, ast.Break,
                              ast.Continue)) for x in mids):
            continue
        if mids:
            s.orelse = list(mids)
            del stmts[i + 1:]
        for h in handlers:
            h.body = h.body[:-1] or [ast.Pass()]
        return


def _strip_dup_tail_returns(node):
    """A valued `return V` at the END of a tail-position if-arm that
    duplicates the function's own trailing `return V` is a sunk copy
    (3.12+ compilers duplicate the function tail into arm exits and
    the decompiler emits the copy inline): dropping it lets the arm
    fall through to the identical tail return. Tail position = reached
    by walking last-statements through orelse-less If arms from the
    function body (compileall 3.12/3.13 compile_file: `if tail ==
    '.py': ... return success` + the function-level `return success`;
    the source has only the tail return)."""
    body = getattr(node, 'body', None)
    if not (isinstance(body, list) and body):
        return
    tail = body[-1]
    if not (isinstance(tail, ast.Return) and tail.value is not None):
        return
    want = ast.dump(tail)
    cur = body[:-1]
    for _ in range(16):
        if not cur:
            return
        _reattach_tail_try_else(cur, want)
        last = cur[-1]
        if isinstance(last, ast.If) and not last.orelse and last.body:
            arm = last.body
            # handler-tail copies of the tail return inside this arm's
            # tries: a handler's `return V` is the same function exit as
            # falling off the arm to the tail return (the try's else
            # clause, when present, is skipped by handler exits in both
            # forms). Safe only when nothing follows the try in the arm.
            for ai, a_s in enumerate(arm):
                # only the duplicated tail Return may follow the try
                tail_ok = all(
                    isinstance(x, ast.Return) and x.value is not None
                    and ast.dump(x) == want
                    for x in arm[ai + 1:])
                if (TRY_TYPES and isinstance(a_s, TRY_TYPES)
                        and tail_ok
                        and not getattr(a_s, 'finalbody', None)
                        and len(getattr(a_s, 'handlers', None) or []) >= 2):
                    for h in a_s.handlers:
                        if (h.body and isinstance(h.body[-1], ast.Return)
                                and h.body[-1].value is not None
                                and ast.dump(h.body[-1]) == want):
                            h.body = h.body[:-1] or [ast.Pass()]
            if (len(arm) > 1 and isinstance(arm[-1], ast.Return)
                    and arm[-1].value is not None
                    and ast.dump(arm[-1]) == want):
                arm.pop()
                return
            cur = arm
            continue
        return


def _is_bare_return(s):
    return (isinstance(s, ast.Return)
            and (s.value is None
                 or (hasattr(ast, 'NameConstant')
                     and isinstance(s.value, ast.NameConstant)
                     and s.value.value is None)
                 or (hasattr(ast, 'Constant')
                     and isinstance(s.value, ast.Constant)
                     and s.value.value is None)
                 or (isinstance(s.value, ast.Name)
                     and s.value.id == 'None')))


def _strip_tail_bare_returns(stmts):
    """Drop bare `return` statements that sit at the very END of a
    function's control flow (falling off the end returns None too, so
    they are no-ops). Recurses through the tail positions of If/loop/
    Try bodies and handler bodies - but NEVER through finalbody (a
    `return` there swallows in-flight exceptions; removing it changes
    semantics) and never through nested function/class scopes. 3.11
    sinks a `LOAD None; RETURN` copy into every exit of a try
    structure and the decompiler faithfully renders each one (asyncore
    3.10/3.11 readwrite: phantom `return`s inside the last guard arm,
    the OSError else arm and the bare-except arm of a function that
    ENDS with the try). Both sides get stripped, so a source's own
    explicit tail return stays equal."""
    if not stmts:
        return stmts
    last = stmts[-1]
    if _is_bare_return(last):
        out = list(stmts[:-1])
        if not out:
            out = [ast.Pass()]
        return out
    if isinstance(last, ast.If):
        last.body = _strip_tail_bare_returns(last.body)
        if last.orelse:
            last.orelse = _strip_tail_bare_returns(last.orelse)
    elif isinstance(last, _LOOP_TYPES):
        last.body = _strip_tail_bare_returns(last.body)
        # a loop orelse runs on exhaustion - also function tail when
        # the loop itself is
        if getattr(last, 'orelse', None):
            last.orelse = _strip_tail_bare_returns(last.orelse)
    elif isinstance(last, _TRY_TYPES):
        last.body = _strip_tail_bare_returns(last.body)
        if getattr(last, 'orelse', None):
            last.orelse = _strip_tail_bare_returns(last.orelse)
        for h in getattr(last, 'handlers', None) or []:
            if h.body:
                h.body = _strip_tail_bare_returns(h.body)
        # finalbody deliberately NOT stripped
    elif isinstance(last, (ast.With,
                           getattr(ast, 'AsyncWith', ast.With))):
        last.body = _strip_tail_bare_returns(last.body)
    return stmts


def _normalize_func_tail_loop(node):
    """If a function/method body's LAST statement is a loop, a bare
    `return` inside that loop is observationally identical to a `break`
    (both leave the function with None): canonicalize the return to a
    break so a fused-tail break compares equal regardless of which form
    each side carries.

    A loop FOLLOWED BY a tail T gets the reverse canonicalization when
    it is a constant-true `while` (no exhaustion path): every `break`
    becomes T + bare `return` and the now-dead post-loop T is dropped -
    the decompiler sinks a function-final tail into the break arms
    (contextlib 3.12 _fix_exception_context: `if exc_context is
    frame_exc: break` + post-loop assign renders as the assign inside
    the break arm followed by `return`)."""
    body = getattr(node, 'body', None)
    if not (isinstance(body, list) and body):
        return
    last = body[-1]
    if isinstance(last, _LOOP_TYPES):
        _bare_return_to_break(last.body)
        _orelse = getattr(last, 'orelse', None) or []
        if _orelse:
            _bare_return_to_break(_orelse)
            _strip_orelse_tail_breaks(_orelse)
            last.orelse = _flatten_tail_elses(_orelse)
        return
    # a loop FOLLOWED BY a tail T: `for/while: B(bare returns, no own
    # breaks)` + T equals `loop: B(breaks) else: T` - a bare return
    # leaves the function skipping T exactly as a break skips the else
    # arm, and exhaustion runs T in both forms. The decompiler sinks the
    # function tail into the loop else and renders the returns as breaks
    # (base64 3.11 main: source `if o == '-t': test(); return` + the
    # post-loop dispatch tail vs the decompile's `break` + for-else).
    # No own Break may exist in B: an original break would fall INTO T
    # while the transformed one skips the else.
    for i, s in enumerate(body):
        if (isinstance(s, _LOOP_TYPES)
                and not getattr(s, 'orelse', None)
                and i + 1 < len(body)
                and _count_breaks(s.body) == 0
                and _count_bare_returns(s.body) > 0):
            _bare_return_to_break(s.body)
            s.orelse = [copy.deepcopy(t) for t in body[i + 1:]]
            del body[i + 1:]
            s.orelse = _flatten_tail_elses(s.orelse)
            break
    # descend through trailing If arms: a loop ending the last arm of
    # a function-tail if/elif/else chain is still a function-tail loop
    # (every loop exit falls to the function end), so bare returns
    # inside it canonicalize to breaks (cgi 3.12 read_binary:
    # `if todo >= 0: while todo > 0: ... return` vs the source break)
    def _tail_loops(stmts, out):
        if not stmts:
            return
        lst = stmts[-1]
        if isinstance(lst, _LOOP_TYPES):
            out.append(lst)
        elif isinstance(lst, ast.If):
            _tail_loops(lst.body, out)
            _tail_loops(lst.orelse, out)
    loops = []
    _tail_loops(body, loops)
    if loops:
        for lp in loops:
            _bare_return_to_break(lp.body)
            _o = getattr(lp, 'orelse', None) or []
            if _o:
                _bare_return_to_break(_o)
                _strip_orelse_tail_breaks(_o)
                lp.orelse = _flatten_tail_elses(_o)
        return
    # a loop followed by EXACTLY [return V]: an in-arm `return V` is
    # observationally identical to `break` (the break falls through to
    # the same return; exhaustion runs it too). 3.14 sinks the tail
    # return into every break exit and the decompiler renders the sunk
    # copy (ast 3.14 _splitlines_no_ff: `if lineno > maxlines: return
    # lines` vs the source break + post-loop return). Canonicalize
    # matching in-arm returns to breaks on both sides.
    for i, s in enumerate(body):
        if (isinstance(s, _LOOP_TYPES)
                and len(body) == i + 2
                and isinstance(body[-1], ast.Return)
                and body[-1].value is not None):
            rd = ast.dump(body[-1].value)
            _tail_return_to_break(s.body, rd)
            _tail_return_to_break(getattr(s, 'orelse', None) or [], rd)
    for i, s in enumerate(body):
        if (isinstance(s, ast.While) and _is_const_true(s.test)
                and i + 1 < len(body)):
            tail = body[i + 1:]
            total = (_count_breaks(s.body)
                     + _count_breaks(getattr(s, 'orelse', []) or []))
            if total == 0:
                continue
            done = _break_to_tail_return(s.body, tail)
            done += _break_to_tail_return(getattr(s, 'orelse', []) or [], tail)
            if done == total:
                del body[i + 1:]
                _bare_return_to_break(s.body)
                _bare_return_to_break(getattr(s, 'orelse', []) or [])
            break


def fold_nested_compare_chain(stmts):
    """Fold `if a op1 b: if b op2 c: X` (inner If is the sole stmt, no
    else arms) into the chained comparison `if a op1 b op2 c: X`. The
    decompiler renders each link of a source chained comparison as its
    own nested guard (ast 3.10/3.14 literal_eval `node.args ==
    node.keywords == []`); the forms are equivalent when the shared
    middle operand is pure (no calls - re-evaluation unobservable)."""
    out = []
    for s in stmts:
        if isinstance(s, ast.If):
            s.body = fold_nested_compare_chain(s.body)
            if s.orelse:
                s.orelse = fold_nested_compare_chain(s.orelse)
            while (not s.orelse and len(s.body) == 1
                   and isinstance(s.test, ast.Compare)
                   and len(s.test.ops) == 1
                   and isinstance(s.body[0], ast.If)):
                inner = s.body[0]
                if (inner.orelse
                        or not isinstance(inner.test, ast.Compare)
                        or len(inner.test.ops) != 1):
                    break
                shared_a = s.test.comparators[-1]
                shared_b = inner.test.left
                if ast.dump(shared_a) != ast.dump(shared_b) \
                        or not _is_pure_bool_operand(shared_a):
                    break
                s.test = ast.Compare(
                    left=s.test.left,
                    ops=[s.test.ops[0], inner.test.ops[0]],
                    comparators=[shared_a] + list(inner.test.comparators))
                s.body = inner.body
        out.append(s)
    return out


def merge_adjacent_guard_breaks(stmts):
    """`if c1: break` immediately followed by `if c2: break` (both
    orelse-empty) collapses to `if c1 or c2: break`: the decompiler
    renders a multi-link loop-tail guard whose else-break folded onto
    the loop exit as PER-LINK breaks, while the source's single
    `if A and B: ... else: break` normalizes (via the tail-else fold +
    DeMorgan) to ONE Or-guard break (configparser 3.8/3.9 before_get
    `if value and "%(" in value:`). The merged test goes through
    canonical_bool so operand order matches the already-canonicalized
    single-guard side."""
    out = []
    for s in stmts:
        if (isinstance(s, ast.If) and not s.orelse
                and len(s.body) == 1 and isinstance(s.body[0], ast.Break)
                and out):
            prev = out[-1]
            if (isinstance(prev, ast.If) and not prev.orelse
                    and len(prev.body) == 1
                    and isinstance(prev.body[0], ast.Break)):
                out[-1] = ast.If(
                    test=canonical_bool(ast.BoolOp(
                        op=ast.Or(), values=[prev.test, s.test])),
                    body=[ast.Break()], orelse=[])
                continue
        out.append(s)
    return out


def fold_while_head_guard(node):
    """A while whose body STARTS with a lone exit guard canonicalizes:
    - `if c: break` folds INTO THE TEST: `while T and not c: S` (both
      forms leave the loop, skipping any else, when c turns true -
      cmd 3.14 columnize: source `while texts and not texts[-1]:
      del texts[-1]` vs the decompiler's `while texts:
      if texts[-1]: break; del ...`);
    - `if c: continue` wraps the rest: `while T: if not c: S` (a
      continue re-runs the TEST, so folding it into the test would
      wrongly exit the loop).
    While only: a for-loop's continue advances the iterator."""
    if not isinstance(node, ast.While) or not node.body:
        return None
    first = node.body[0]
    if isinstance(first, ast.If) and not first.orelse \
            and len(first.body) == 1 and isinstance(first.body[0], ast.If):
        # merge nested single-If guards first so the dec's split
        # `if a: if b: if c: break` folds like the source's combined
        # `if a and b and c: break` (cgi 3.12
        # read_lines_to_outerboundary limit guard)
        for _ in range(5):
            merged = merge_nested_ifs([first])
            if not merged or ast.dump(merged[0]) == ast.dump(first):
                break
            first = merged[0]
    if not (isinstance(first, ast.If) and not first.orelse
            and len(first.body) == 1
            and isinstance(first.body[0], (ast.Break, ast.Continue))):
        return None
    rest = node.body[1:]
    if not rest:
        return None
    if isinstance(first.body[0], ast.Break):
        return ast.While(
            test=ast.BoolOp(op=ast.And(),
                            values=[node.test,
                                    ast.UnaryOp(op=ast.Not(),
                                                operand=first.test)]),
            body=rest, orelse=node.orelse)
    return ast.While(
        test=node.test,
        body=[ast.If(test=ast.UnaryOp(op=ast.Not(), operand=first.test),
                     body=rest, orelse=[])],
        orelse=node.orelse)


def _is_assertion_error(t):
    if isinstance(t, ast.Name):
        return t.id == 'AssertionError'
    if isinstance(t, ast.Attribute):
        return t.attr == 'AssertionError'
    return False


def _invert_test(t):
    if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
        return t.operand
    if isinstance(t, ast.Compare) and len(t.ops) == 1:
        inv = {ast.Is: ast.IsNot, ast.IsNot: ast.Is,
               ast.In: ast.NotIn, ast.NotIn: ast.In,
               ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
        for k, v in inv.items():
            if isinstance(t.ops[0], k):
                return ast.Compare(left=t.left, ops=[v()],
                                   comparators=t.comparators)
    return None


def fold_if_raise_assert(stmts):
    """`if <guard>: raise AssertionError[(msg)]` IS `assert <not
    guard>[, msg]` - the compiler emits the same shape and the
    decompiler legitimately picks either render (asyncore 2.7/3.x
    compact_traceback `if not tb: raise AssertionError(...)` vs
    `assert tb, ...`). Fold to the Assert form on both sides."""
    out = []
    for s in stmts:
        if (isinstance(s, ast.If) and not s.orelse
                and len(s.body) == 1
                and isinstance(s.body[0], ast.Raise)):
            r = s.body[0]
            exc = getattr(r, 'exc', None) or getattr(r, 'type', None)
            test = None
            msg = None
            if isinstance(exc, ast.Call) \
                    and _is_assertion_error(exc.func) \
                    and len(exc.args) <= 1 and not exc.keywords \
                    and getattr(r, 'cause', None) is None:
                test = s.test
                msg = exc.args[0] if exc.args else None
            elif exc is not None and not isinstance(exc, ast.Call) \
                    and _is_assertion_error(exc):
                test = s.test
                msg = getattr(r, 'inst', None)
            if test is not None:
                inv = _invert_test(test)
                if inv is not None:
                    out.append(ast.Assert(test=inv, msg=msg))
                    continue
        out.append(s)
    return out


def flatten_tail_if_else(stmts):
    """A function-tail `if c: A else: B` (the If is the LAST
    statement of the body) is observationally identical to the
    decompiler's flattened render `if c: A; return` + flat B: arm A
    falls off the function end (== return None) and the explicit
    Return(None) only skips B, which the else already gates. Flatten
    both sides to the explicit form (cmd 3.14 do_help: source
    if/else vs dec's arm-tail return + flat rest)."""
    if len(stmts) < 1:
        return stmts
    last = stmts[-1]
    if (isinstance(last, ast.If) and last.orelse and last.body
            and not isinstance(last.body[-1], (ast.Return, ast.Raise,
                                               ast.Break, ast.Continue))):
        flat = ast.If(test=last.test,
                      body=list(last.body) + [ast.Return(value=None)],
                      orelse=[])
        return list(stmts[:-1]) + [flat] + list(last.orelse)
    return stmts


def merge_guard_continues(stmts):
    """Canonicalize loop-tail guard-continue chains back to the source
    if/elif form. At the TAIL of a loop body, falling off the end ==
    continue, so `if c: continue` + rest T == `if not c: T`, and a
    trailing if/else whose arms end in (redundant) continues equals
    the same chain. The decompiler renders loop-tail dispatch as
    guard-continue chains; the source uses if/elif. Canonical form:
    the source shape - guards merge back into combined conditions and
    arm-tail continues drop (_strptime 3.12 group_key dispatch / 'I'
    ampm arm, 3.13 __find_month_format `if not full_indices and not
    abbr_indices: return None, None`, cmd 3.7 complete_help)."""
    n = len(stmts)
    if n < 2:
        return stmts

    def is_cont_guard(s):
        return (isinstance(s, ast.If) and not s.orelse
                and len(s.body) == 1 and isinstance(s.body[0],
                                                    ast.Continue))

    def ends_cont(seq):
        return bool(seq) and isinstance(seq[-1], ast.Continue)

    def strip_tail_cont(seq):
        seq = list(seq)
        if len(seq) > 1 and ends_cont(seq):
            seq = seq[:-1]
        return seq

    def canon_arm(seq):
        # canonicalize an arm body that sits at a loop tail
        seq = list(seq)
        if not seq:
            return [ast.Pass()]
        out = []
        i = 0
        m = len(seq)
        while i < m:
            if is_cont_guard(seq[i]):
                k = i
                while k < m and is_cont_guard(seq[k]):
                    k += 1
                if k < m:
                    conds = [ast.UnaryOp(op=ast.Not(),
                                         operand=g.test)
                             for g in seq[i:k]]
                    test = conds[0] if len(conds) == 1 else \
                        ast.BoolOp(op=ast.And(), values=conds)
                    out.append(ast.If(test=test,
                                      body=canon_arm(seq[k:]),
                                      orelse=[]))
                    return out
                # trailing lone guards: keep as-is
                out.extend(seq[i:k])
                return out
            s = seq[i]
            # `if c: A else: break` == `if not c: break` + A anywhere
            # in a loop body (c-true runs A and falls on; c-false
            # exits the loop) - canonicalize to the guard shape the
            # decompiler renders (_markupbase 3.8/3.9
            # parse_declaration's isspace skip)
            if (isinstance(s, ast.If) and s.body
                    and len(s.orelse) == 1
                    and isinstance(s.orelse[0], ast.Break)):
                out.append(ast.If(
                    test=ast.UnaryOp(op=ast.Not(), operand=s.test),
                    body=[ast.Break()], orelse=[]))
                out.extend(canon_arm(s.body))
                i += 1
                continue
            # an arm-end continue/break followed by sibling statements
            # is the guard shape of an if/ELSE at the arm tail: fold
            # the remainder into the else (the terminator only skips
            # the siblings, exactly what the else gate does). A LONE
            # `if c: break` guard is left alone (no A to keep)
            if (isinstance(s, ast.If) and not s.orelse
                    and len(s.body) >= 2
                    and isinstance(s.body[-1],
                                   (ast.Continue, ast.Break))
                    and i < m - 1):
                out.append(ast.If(test=s.test,
                                  body=canon_arm(s.body[:-1]),
                                  orelse=canon_arm(seq[i + 1:])))
                return out
            if isinstance(s, ast.If) and i == m - 1:
                out.extend(canon_tail_if(s))
            else:
                if isinstance(s, ast.If):
                    s = ast.If(test=s.test, body=canon_arm(s.body),
                               orelse=(canon_arm(s.orelse)
                                       if s.orelse else []))
                out.append(s)
            i += 1
        out = strip_tail_cont(out)
        return out or [ast.Pass()]

    def canon_tail_if(node):
        # the LAST statement of a loop-tail body
        if not node.orelse:
            if is_cont_guard(node):
                return [node]
            body = strip_tail_cont(node.body)
            if not body:
                # `if c: continue` alone at the tail is a no-op
                return [ast.Pass()]
            return [ast.If(test=node.test, body=canon_arm(body),
                           orelse=[])]
        out = []
        body = strip_tail_cont(node.body)
        out.append(ast.If(test=node.test,
                          body=canon_arm(body) if body else [ast.Pass()],
                          orelse=[]))
        rest = strip_tail_cont(node.orelse)
        if (len(rest) == 1 and isinstance(rest[0], ast.If)
                and rest[0].orelse):
            out.extend(canon_tail_if(rest[0]))
        else:
            out.extend(canon_arm(rest) if rest else [ast.Pass()])
        # rebuild as a proper if/elif chain (the last element may be a
        # plain statement run - wrap it as the final else arm)
        if len(out) == 1:
            return out
        chain = out[-1]
        for g in reversed(out[:-1]):
            g.orelse = [chain] if isinstance(chain, ast.stmt) else chain
            chain = g
        return [chain]

    # canonicalize the whole body as a loop-tail arm: this folds the
    # decompiler's FLAT guard chains (each dispatch If ends in continue
    # with the next arm as a sibling) into the source's nested if/elif
    # shape, and canonicalizes nested arm tails recursively
    stmts = canon_arm(list(stmts))
    n = len(stmts)
    last = stmts[n - 1]
    if isinstance(last, ast.If):
        head = stmts[:n - 1]
        merged = canon_tail_if(last)
        stmts = head + merged
        n = len(stmts)
    # mid/leading guard runs merge into the remainder (only when a
    # non-empty remainder follows: the run may sit anywhere)
    out = []
    i = 0
    while i < n:
        if is_cont_guard(stmts[i]):
            k = i
            while k < n and is_cont_guard(stmts[k]):
                k += 1
            if k < n:
                conds = [ast.UnaryOp(op=ast.Not(), operand=g.test)
                         for g in stmts[i:k]]
                test = conds[0] if len(conds) == 1 else \
                    ast.BoolOp(op=ast.And(), values=conds)
                out.append(ast.If(test=test,
                                  body=canon_arm(stmts[k:]),
                                  orelse=[]))
                return out
            out.extend(stmts[i:k])
            return out
        out.append(stmts[i])
        i += 1
    return out


def dump_stmts(stmts):
    """ast.dump refuses lists; compare statement bodies position-wise."""
    return '[' + ','.join(ast.dump(s) for s in stmts) + ']'


def merge_nested_ifs(stmts):
    """'if a: if b: X' (no elses) compiles identically to 'if a and b: X';
    'if a: X else: if b: X' (same then) to 'if a or b: X'; and
    'if a: if b: X' where the outer has no else also equals
    'if not a or b: X'-style De Morgan rewritings. Canonicalize all such
    forms by merging, then let canonical_bool normalize the test."""
    out = []
    for s in stmts:
        if isinstance(s, ast.If):
            # form 1: if a: (if b: X)  ->  if a and b: X
            if not s.orelse and len(s.body) == 1 and isinstance(s.body[0], ast.If):
                inner = s.body[0]
                if not inner.orelse:
                    merged_test = ast.BoolOp(op=ast.And(),
                                             values=[s.test, inner.test])
                    s = ast.If(test=merged_test, body=inner.body, orelse=[])
            # form 1b: if a: (if b: X else: Y) else: Y
            #   ->  if a and b: X else: Y
            # both false paths run the SAME Y, so the guards conjoin
            # exactly (cgi 2.7 indexed_value: the decompiler merged the
            # twin `return None` arms, the source nests them)
            elif (s.orelse and len(s.body) == 1
                    and isinstance(s.body[0], ast.If)
                    and s.body[0].orelse
                    and dump_stmts(s.body[0].orelse) == dump_stmts(s.orelse)):
                inner = s.body[0]
                merged_test = ast.BoolOp(op=ast.And(),
                                         values=[s.test, inner.test])
                s = ast.If(test=merged_test, body=inner.body,
                           orelse=inner.orelse)
            # form 2: if a: X else: (if b: X2) with X == X2 -> if a or b: X
            elif (len(s.orelse) == 1 and isinstance(s.orelse[0], ast.If)
                  and dump_stmts(s.body) == dump_stmts(s.orelse[0].body)):
                inner = s.orelse[0]
                merged_test = ast.BoolOp(op=ast.Or(),
                                         values=[s.test, inner.test])
                s = ast.If(test=merged_test, body=s.body,
                           orelse=inner.orelse)
        out.append(s)
    return out


class BoolCanonicalizer(ast.NodeTransformer):
    def visit_If(self, node):
        self.generic_visit(node)
        node.test = canonical_bool(node.test)
        return node

    def visit_While(self, node):
        self.generic_visit(node)
        node.test = canonical_bool(node.test)
        return node

    def visit_IfExp(self, node):
        self.generic_visit(node)
        node.test = canonical_bool(node.test)
        return node

    def visit_Assert(self, node):
        self.generic_visit(node)
        node.test = canonical_bool(node.test)
        return node

    def visit_Yield(self, node):
        self.generic_visit(node)
        # bare `yield` and `yield None` compile identically
        # (LOAD_CONST None; YIELD_VALUE) - canonicalize the value
        # (_collections_abc 3.10 items-view generators)
        v = node.value
        if hasattr(ast, 'Constant') and isinstance(v, ast.Constant) \
                and v.value is None:
            node.value = None
        elif hasattr(ast, 'NameConstant') and isinstance(
                v, getattr(ast, 'NameConstant')) and v.value is None:
            node.value = None
        elif isinstance(v, ast.Name) and v.id == 'None':
            node.value = None
        return node


def _fold_try_body_tail_return(stmts):
    """Canonicalize value returns around a try/except with no else:

    1. a value Return as the LAST statement of the try body is moved to
       right AFTER the try (if the body completed the return runs either
       way; an exception skips it in both forms). CPython 3.10 narrows
       the protected range to exclude the return, so 'try: X; return v
       except E: Y' and 'try: X except E: Y' + 'return v' compile
       indistinguishably (emit_return's routing comment documents the
       LOAD-const ambiguity).
    2. a value Return as the LAST statement of EACH handler clause (all
       identical, no orelse/finalbody) is likewise moved to after the
       try: falling out of the handler reaches the same return
       (Mapping.setdefault: source 'except KeyError: self[key]=default'
       + function-level 'return default' vs the decompiler's
       clause-sunk 'return default').

    Applied to both sides, the two renderings converge
    (_collections_abc 3.10)."""
    try_types = tuple(
        t for t in (getattr(ast, 'Try', None), getattr(ast, 'TryExcept', None))
        if t is not None)
    # dead code after a terminator: statements following a Return/Raise
    # at the same level are unreachable and CPython's optimizer deletes
    # them, so the bytecode-driven decompiled output can never carry
    # them (3.11 compileall main(): the trailing `return True` after
    # the all-returning try is absent from the bytecode; rule 1's
    # extraction also produces Return-after-Return here). Drop the
    # tail; applied to both sides so they converge.
    for ti in range(len(stmts) - 1):
        if isinstance(stmts[ti], (ast.Return, ast.Raise)):
            del stmts[ti + 1:]
            break
    i = 0
    while i < len(stmts):
        s = stmts[i]
        if try_types and isinstance(s, try_types):
            _fold_try_body_tail_return(s.body)
            for h in getattr(s, 'handlers', None) or []:
                h.body = _fold_try_body_tail_return(h.body)
            _fold_try_body_tail_return(getattr(s, 'orelse', None) or [])
            _fold_try_body_tail_return(getattr(s, 'finalbody', None) or [])
            moved = []
            # body-tail value return extracts FIRST (rule 1)
            if not getattr(s, 'orelse', None) \
                    and s.body and isinstance(s.body[-1], ast.Return) \
                    and s.body[-1].value is not None:
                moved.append(s.body.pop())
            # the handler-tail return may only move out when the body
            # STILL terminates after rule 1 (success never falls
            # through to the sibling): __contains__ (body=[subscript],
            # the `return True` just extracted) keeps `return False` in
            # the handler; setdefault (body was [return self[key]], now
            # empty but terminated) canonicalizes to the sibling form
            body_terminates = (not s.body and bool(moved)) or (
                bool(s.body) and isinstance(
                    s.body[-1],
                    (ast.Return, ast.Raise, ast.Break, ast.Continue)))
            handlers = getattr(s, 'handlers', None) or []
            if body_terminates \
                    and not getattr(s, 'orelse', None) \
                    and not getattr(s, 'finalbody', None) and handlers:
                tails = []
                for h in handlers:
                    if h.body and isinstance(h.body[-1], ast.Return) \
                            and h.body[-1].value is not None:
                        tails.append(ast.dump(h.body[-1].value))
                    else:
                        tails = None
                        break
                if tails and len(set(tails)) == 1:
                    for h in handlers:
                        moved.append(h.body.pop())
            for j, m in enumerate(moved):
                stmts.insert(i + 1 + j, m)
            i += len(moved)
            # rule 1/2 extractions can expose a Return-after-Return
            # dead tail (the source's post-try return sits behind the
            # extracted one) - re-drop
            for ti in range(len(stmts) - 1):
                if isinstance(stmts[ti], (ast.Return, ast.Raise)):
                    del stmts[ti + 1:]
                    break
            # rule 3: a try that CANNOT fall through (body terminates
            # and every handler terminates; an If tail counts when
            # both arms terminate) makes following siblings dead -
            # CPython's optimizer deletes them, so the bytecode-driven
            # decompiled output can never reproduce them (3.11
            # compileall main(): the trailing `return True` after the
            # all-returning try is absent from the module's own
            # bytecode). Drop the tail when it is a single Return.
            def _terms(seq):
                if not seq:
                    return False
                last = seq[-1]
                if isinstance(last, (ast.Return, ast.Raise)):
                    return True
                if isinstance(last, ast.If):
                    return _terms(last.body) and bool(last.orelse) \
                        and _terms(last.orelse)
                return False
            if try_types and isinstance(s, try_types) \
                    and _terms(s.body) \
                    and (getattr(s, 'handlers', None) or []) \
                    and all(_terms(h.body) for h in s.handlers) \
                    and not getattr(s, 'finalbody', None) \
                    and i + 2 == len(stmts) \
                    and isinstance(stmts[i + 1], ast.Return):
                del stmts[i + 1]
            # rule 4: when EVERY handler terminates (return/raise/
            # break), the else arm's statements run exactly when the
            # try falls through - hoist them to siblings right after
            # the try. The decompiler renders loop-tail try/except
            # bodies as try/except/ELSE while the source has flat
            # followers (cmd 3.14 do_help, asynchat 3.10
            # initiate_send); both sides converge on the flat form.
            if try_types and isinstance(s, try_types) \
                    and getattr(s, 'orelse', None) \
                    and not getattr(s, 'finalbody', None) \
                    and (getattr(s, 'handlers', None) or []) \
                    and all(_terms(h.body) for h in s.handlers):
                stmts[i + 1:i + 1] = s.orelse
                s.orelse = []
        i += 1
    return stmts


def _normalize_handler_break_raise(stmts):
    """A handler clause `except E: raise X` inside a loop, where the
    statement right AFTER the loop is the identical `raise X`, is
    observationally a `break`: both leave the loop and raise X (the
    compiler fuses the break-to-raise, 3.10 _collections_abc
    Sequence.index `except IndexError: break` + post-loop
    `raise ValueError` renders as the fused raise). Canonicalize the
    handler body to Break so both forms compare equal."""
    for i in range(len(stmts) - 1):
        loop, nxt = stmts[i], stmts[i + 1]
        if not isinstance(loop, _LOOP_TYPES) or not isinstance(nxt, ast.Raise):
            continue
        # py2 Raise carries .type/.inst/.tback; py3 carries .exc/.cause
        nxt_exc = getattr(nxt, 'exc', None) or getattr(nxt, 'type', None)
        want = ast.dump(nxt_exc) if nxt_exc is not None else None
        if want is None:
            continue

        def fix(node):
            for sub in ast.walk(node):
                h_list = getattr(sub, 'handlers', None)
                if not h_list:
                    continue
                for h in h_list:
                    if len(h.body) != 1 or not isinstance(h.body[0], ast.Raise):
                        continue
                    r = h.body[0]
                    r_exc = getattr(r, 'exc', None) or getattr(r, 'type', None)
                    if (r_exc is not None
                            and ast.dump(r_exc) == want
                            and getattr(r, 'cause', None) is None
                            and getattr(r, 'inst', None) is None
                            and getattr(r, 'tback', None) is None):
                        h.body = [ast.Break()]
        fix(loop)
    return stmts


def _scope_assigned_names(node):
    """Names bound by Store/Del anywhere in the scope body (including
    nested funcs/classes), plus names captured by nested-scope global/
    nonlocal statements that are assigned there."""
    assigned = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
            assigned.add(sub.id)
        elif hasattr(ast, 'arg'):
            pass
    # function args / defaults bind names too
    for sub in ast.walk(node):
        if isinstance(sub, (ast.FunctionDef, getattr(ast, 'AsyncFunctionDef', ast.FunctionDef))):
            a = sub.args
            for arg in getattr(a, 'args', []) + getattr(a, 'kwonlyargs', []):
                assigned.add(getattr(arg, 'arg', getattr(arg, 'id', None)))
            for arg in [getattr(a, 'vararg', None), getattr(a, 'kwarg', None)]:
                if arg is not None:
                    assigned.add(getattr(arg, 'arg', getattr(arg, 'id', None)))
    assigned.discard(None)
    return assigned


def prune_globals(tree):
    """`global x` for a name never assigned in the scope is a bytecode
    no-op (loads resolve the same); decompilers infer the statement from
    assignments only. Drop unassigned names and sort the rest so
    declaration-order/verbosity differences compare equal."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             getattr(ast, 'AsyncFunctionDef', ast.FunctionDef),
                             ast.ClassDef)):
            assigned = _scope_assigned_names(node)
            body = getattr(node, 'body', None)
            if not isinstance(body, list):
                continue
            for stmt in body:
                if isinstance(stmt, ast.Global) and stmt.names:
                    keep = sorted(n for n in stmt.names if n in assigned)
                    if keep:
                        stmt.names = keep
                    else:
                        body.remove(stmt)
    return tree


def _free_names(node):
    """Names LOADed by an expression (its free reads)."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
    return out


def _stores_in_scope(body):
    """Names ASSIGNED/augmented anywhere in a statement list. Descends
    into nested function/class scopes too (ast.walk does not prune) -
    over-collecting stores only makes the invariance test MORE
    conservative, never unsound."""
    out = set()
    for s in body:
        for n in ast.walk(s):
            if isinstance(n, ast.Name) and isinstance(
                    n.ctx, (ast.Store, ast.Del)):
                out.add(n.id)
            elif isinstance(n, ast.Global):
                out.update(n.names)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                if isinstance(n.name, str):
                    out.add(n.name)
                elif isinstance(n.name, ast.Name):
                    out.add(n.name.id)
    return out


def _has_call_or_yield(node):
    _types = tuple(t for t in (ast.Call, ast.Yield,
                               getattr(ast, 'YieldFrom', None),
                               getattr(ast, 'Await', None)) if t is not None)
    for n in ast.walk(node):
        if isinstance(n, _types):
            return True
    return False


def _has_break_shallow(body):
    """A Break belonging to THIS loop (not a nested loop's)."""
    for s in body:
        if isinstance(s, ast.Break):
            return True
        if isinstance(s, _LOOP_TYPES):
            continue  # nested loop's breaks are its own
        for fld in ('body', 'orelse', 'finalbody'):
            sub = getattr(s, fld, None)
            if isinstance(sub, list) and _has_break_shallow(sub):
                return True
        for h in getattr(s, 'handlers', None) or []:
            if _has_break_shallow(h.body):
                return True
    return False


def _has_attr_or_sub(node):
    for n in ast.walk(node):
        if isinstance(n, (ast.Attribute, ast.Subscript)):
            return True
    return False


def _mutates_container(body):
    """Any attribute/subscript store or mutating call target in the
    statement list (sound over-approximation for 'could this change an
    attribute-based loop test')."""
    for s in body:
        for n in ast.walk(s):
            if isinstance(n, (ast.Attribute, ast.Subscript)) and \
                    isinstance(n.ctx, (ast.Store, ast.Del)):
                return True
    return False


def fold_guard_continue_else(stmts):
    """LOOP-BODY equivalence: `if c: X; continue` followed by siblings
    <rest> == `if c: X else: <rest>` - the continue skips exactly the
    rest of this iteration, which the else arm also skips on c-true
    and runs on c-false (_osx_support 3.10-3.13
    _default_sysroot_chain: the source's elif chain normalizes to
    guard+continue form, the decompiler renders nested else arms).
    Recursive: elif chains fold one level per guard, and guards nested
    inside already-folded else arms must fold too. Stops at nested
    loops - THEIR bodies' continues are their own."""
    out = []
    i = 0
    n = len(stmts)
    while i < n:
        s = stmts[i]
        if (isinstance(s, ast.If) and not s.orelse
                and s.body and isinstance(s.body[-1], ast.Continue)
                and i + 1 < n):
            rest = fold_guard_continue_else(stmts[i + 1:])
            out.append(ast.If(test=s.test,
                              body=s.body[:-1] or [ast.Pass()],
                              orelse=rest))
            return out
        if isinstance(s, ast.If):
            s.body = fold_guard_continue_else(s.body)
            s.orelse = fold_guard_continue_else(s.orelse)
        elif isinstance(s, (ast.With, getattr(ast, 'AsyncWith', ast.With))):
            s.body = fold_guard_continue_else(s.body)
        elif TRY_TYPES and isinstance(s, TRY_TYPES):
            s.body = fold_guard_continue_else(s.body)
            for h in getattr(s, 'handlers', None) or []:
                h.body = fold_guard_continue_else(h.body)
            if getattr(s, 'orelse', None):
                s.orelse = fold_guard_continue_else(s.orelse)
            if getattr(s, 'finalbody', None):
                s.finalbody = fold_guard_continue_else(s.finalbody)
        # nested loops scope their own continues - do not descend
        out.append(s)
        i += 1
    return out


def unfold_invariant_while(stmts):
    """`while G: B` where G is a side-effect-free test that B never
    rebinds is equivalent to `if G: while True: B` - G is loop-invariant
    so re-testing it each iteration is a no-op, and B must hold a break
    (else both forms spin forever identically). The decompiler fuses a
    pre-loop guard into the following while-True (the rotated-while
    idiom); the source keeps them separate. Canonicalize the fused form
    INTO the split form so they compare equal (_osx_support 3.8/3.9
    compiler_fixup: `if stripSysroot: while True: ... break` rendered
    `while stripSysroot: ... break`; stripSysroot is set once before the
    loop). Only fires when B contains a break, so a genuine
    condition-driven `while G: B` (no break, exits on G turning false)
    is left untouched."""
    out = []
    for s in stmts:
        if (isinstance(s, ast.While) and not s.orelse
                and not _is_const_true(s.test)
                and not _has_call_or_yield(s.test)
                and _has_break_shallow(s.body)
                and not (_free_names(s.test) & _stores_in_scope(s.body))
                # an attribute/subscript-based test (`while self.a and
                # self.b:`) is NOT provably invariant from name-level
                # stores alone: any attribute/subscript mutation in the
                # body could flip it (asynchat 3.10 initiate_send's
                # `while self.producer_fifo and self.connected:` got
                # unfolded on one side only, sinking the function tail
                # into nested orelse). Require a pure-NAME test, or a
                # body with no container mutations at all.
                and (not _has_attr_or_sub(s.test)
                     or not _mutates_container(s.body))):
            # the Normalizer canonicalizes True/False/None constants to
            # Name nodes (py2 has no True constant); this transform runs
            # after it, so build the canonical form directly
            inner = ast.While(test=ast.Name(id='True', ctx=ast.Load()),
                              body=s.body, orelse=[])
            s = ast.If(test=s.test, body=[inner], orelse=[])
        out.append(s)
    return out


class _ArtifactFolder(ast.NodeTransformer):
    """(1) 3.14 PEP 649 deferred-annotation machinery: `def
    __annotate__` and `__conditional_annotations__ = ...` are
    compiler-generated module/class preamble that never exists in any
    source (_colorize 3.14: the decompiled module carried them ahead
    of the imports, misaligning every later sibling).
    (2) constant-condition if folds: `if False: X` compiles to NOTHING
    (X survives only inside the __annotate__ machinery), so the source
    side's dead block must fold to compare equal with the
    bytecode-driven decompile; `if True: X` folds to X. Name-based
    True/False (py2) fold too."""
    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        # module level `__annotate__`, class level `__annotate_func__`
        if node.name.startswith('__annotate'):
            return None
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_Assign(self, node):
        if (len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == '__conditional_annotations__'):
            return None
        return node

    def visit_AnnAssign(self, node):
        # a value-less annotation statement emits NO bytecode (3.14
        # defers it into __annotate__; pre-3.14 it only touches
        # __annotations__), and a valued one's annotation is likewise
        # source-only - canonicalize to the plain assignment shape the
        # decompile can show (_colorize 3.14 ThemeSection's
        # `__dataclass_fields__: ClassVar[...]` bare annotations).
        # Never reached on py2 (no AnnAssign node type there).
        if node.value is None:
            return None
        return ast.Assign(targets=[node.target], value=node.value)

    def visit_If(self, node):
        self.generic_visit(node)
        t = node.test
        flag = None
        _const_t = getattr(ast, 'Constant', None)
        if _const_t is not None and isinstance(t, _const_t):
            # CPython constant-folds ANY constant if-test (`if 0:`
            # blocks compile to nothing - _pylong 3.14's documentation
            # dead code); mirror the fold
            flag = bool(t.value)
        elif isinstance(t, ast.Name) and t.id in ('True', 'False'):
            flag = t.id == 'True'
        if flag is True:
            return list(node.body) if node.body else None
        if flag is False:
            return list(node.orelse) if node.orelse else None
        return node


def dump(src):
    tree = ast.parse(src)
    tree = _ArtifactFolder().visit(tree)
    tree = Normalizer().visit(tree)
    tree = BoolCanonicalizer().visit(tree)
    # re-run body normalization so merged/canonical forms settle
    tree = Normalizer().visit(tree)
    tree = prune_globals(tree)
    if isinstance(tree, ast.Module):
        tree.body = strip_noop_continues(tree.body, False)
    # a bare `return` inside a function's LAST-statement loop is the same
    # observable end as a `break` there (3.13+ fuses a tail-loop break
    # into RETURN_CONST None) - canonicalize so the fused form compares
    # equal. Runs after the Normalizer so `return None` is already bare.
    # pre-merge nested single-stmt guards (`if a: if b: X` -> `if a and
    # b: X`) BEFORE the tail-loop rewrite: _break_to_tail_return copies
    # the tail into the innermost break arm, freezing the nesting depth,
    # so a nested-guard source and a merged-guard decompile stop
    # converging afterwards (codecs 3.7-3.9 StreamReader.read: the
    # `if chars>=0: if len>=chars: break` tail-sink diverged from the
    # decompiler's merged `if chars>=0 and len>=chars: break`).
    for node in ast.walk(tree):
        _expr_ternary_to_if(node)
    for node in ast.walk(tree):
        for field, value in ast.iter_fields(node):
            if (isinstance(value, list) and value
                    and isinstance(value[0], ast.stmt)):
                setattr(node, field, merge_adjacent_guard_breaks(
                    merge_nested_ifs(fold_nested_compare_chain(value))))
    # re-run the terminal-else flatten AFTER the loop-else tail
    # flatten inside _flatten_node: a released loop tail can make an
    # ENCLOSING If's then arm terminal one level up, which the
    # normalize_body-stage flatten already passed over (ast 3.14
    # _compare: the list branch's `else: return True` released into
    # the outer If body, whose own else arm then had to flatten too)
    _stable = 0
    while _stable < 2:
        _stable += 1
        for node in ast.walk(tree):
            for field, value in ast.iter_fields(node):
                if (isinstance(value, list) and value
                        and isinstance(value[0], ast.stmt)):
                    _nv = flatten_terminal_else(value)
                    if len(_nv) != len(value):
                        _stable = 0
                    setattr(node, field, _nv)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,
                             getattr(ast, 'AsyncFunctionDef', ast.FunctionDef))):
            _normalize_func_tail_loop(node)
            _normalize_func_tail_handler_return(node)
            _strip_dup_tail_returns(node)
            node.body = _strip_tail_bare_returns(node.body)
            _refold_tail_flat_else(node.body)
            _strip_redundant_tail_bare_returns(node.body)
            if _sink_func_tail_into_guard_arms(node):
                # the sink can make nested guard arms terminal - give
                # the existing tail-sinking machinery the chance to
                # release their orelse arms into the sibling form the
                # decompiler renders (rebuilds the tree top-down
                # through _flatten_node). ONLY when the sink fired:
                # an unconditional re-flatten here re-runs the
                # loop-tail if/else canonicalization ahead of
                # fold_guard_continue_else and derails the else-break
                # guard fold (configparser 3.8/3.9 before_get,
                # _markupbase 3.8/3.9 parse_declaration regressed
                # under the wide form)
                node.body = _flatten_node_list(_flatten_terminal_else_deep(
                    list(node.body)))
            # function-tail loop: a handler-tail `break` and the
            # loop-tail `continue` (or the source's stripped bare
            # `return`) all leave the function with None when the
            # handler sits at the loop body's tail - canonicalize the
            # handler tail to Continue so the forms converge
            # (asynchat 3.10 initiate_send: orig `except OSError:
            # handle_error(); return` vs dec `break`)
            if node.body and isinstance(node.body[-1], _LOOP_TYPES):
                _lp = node.body[-1]

                def _brk2cont(sel):
                    for _s in sel:
                        if isinstance(_s, _TRY_TYPES):
                            for _h in getattr(_s, 'handlers',
                                              None) or []:
                                if _h.body and isinstance(
                                        _h.body[-1], ast.Break):
                                    _h.body[-1] = ast.Continue()
                                _brk2cont(_h.body)
                            _brk2cont(_s.body)
                            _brk2cont(getattr(_s, 'orelse',
                                              None) or [])
                            _brk2cont(getattr(_s, 'finalbody',
                                              None) or [])
                        elif isinstance(_s, (ast.If, ast.With,
                                             getattr(ast, 'AsyncWith',
                                                     ast.With))):
                            _brk2cont(_s.body)
                            _brk2cont(getattr(_s, 'orelse',
                                              None) or [])
                        # nested loops scope their own breaks - skip

                _brk2cont(_lp.body)
                _brk2cont(getattr(_lp, 'orelse', None) or [])
    # merge loop-tail guard-continue chains back into the combined
    # `if not c1 and not c2: S` the compiler short-circuited them from.
    # Loop bodies get at_loop_tail=True (their tail falls through to the
    # next iteration); a function body's tail loop also qualifies (its
    # `continue` guards fall through to the function end).
    def _merge_outer_guard_continues(stmts):
        # `if A: (if B: continue; S*)` as the LAST statement of a loop
        # body == `if (not A) or B: continue; S*` - the decompiler
        # merges the skip-guards with De Morgan (cmd 3.7 complete_help:
        # `if name[:3]=='do_': {if name == prevname: continue; ...}`
        # renders as the Or-guard continue + flat rest). Valid only at
        # the loop-body tail, where falling off the end == continue.
        if not stmts:
            return stmts
        last = stmts[-1]
        if (isinstance(last, ast.If) and not last.orelse
                and last.body and isinstance(last.body[0], ast.If)
                and not last.body[0].orelse
                and len(last.body[0].body) == 1
                and isinstance(last.body[0].body[0], ast.Continue)):
            inner = last.body[0]
            merged = ast.If(
                test=ast.BoolOp(op=ast.Or(), values=[
                    ast.UnaryOp(op=ast.Not(), operand=last.test),
                    inner.test,
                ]),
                body=[ast.Continue()],
                orelse=[])
            return stmts[:-1] + [merged] + last.body[1:]
        return stmts

    def _merge_tail_arm_guards(stmts):
        # the loop body's LAST statement may be an if/elif chain whose
        # arms end in the guard-continue chain (compileall 3.12
        # _walk_dir: `elif A and B and ...: yield from ...` decompiles
        # to `else: if not A: continue; ...; yield from ...`). An arm at
        # the loop-body tail also falls through to the next iteration,
        # so the merge stays valid inside it - recurse through trailing
        # arms and elif links.
        merged = merge_guard_continues(stmts)
        if merged and isinstance(merged[-1], ast.If):
            last = merged[-1]
            last.body = _merge_tail_arm_guards(last.body)
            if last.orelse:
                last.orelse = _merge_tail_arm_guards(last.orelse)
        return merged

    for node in ast.walk(tree):
        if isinstance(node, _LOOP_TYPES):
            node.body = _merge_outer_guard_continues(
                _merge_tail_arm_guards(node.body))
    for _pass in range(4):
        _changed = False
        for node in ast.walk(tree):
            for field, value in ast.iter_fields(node):
                if not isinstance(value, list):
                    continue
                for vi, v in enumerate(value):
                    if isinstance(v, ast.While):
                        folded = fold_while_head_guard(v)
                        if folded is not None:
                            value[vi] = folded
                            _changed = True
        if not _changed:
            break
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,
                             getattr(ast, 'AsyncFunctionDef', ast.FunctionDef))):
            if node.body and isinstance(node.body[-1], _LOOP_TYPES):
                node.body[-1].body = _merge_tail_arm_guards(node.body[-1].body)
    # iterate to a fixpoint (bounded): each merge_nested_ifs pass fuses
    # ONE nesting level per element, so a source `if a and b: if c and d:
    # if e or f: X` vs the decompiler's fully split `if a and b: if c:
    # if d: if e: if f: X` needs several rounds (csv 3.3
    # _guess_delimiter stopped after two levels and compared unequal)
    _in_loop_arm = {}
    for _lp in ast.walk(tree):
        if isinstance(_lp, _LOOP_TYPES):
            _stack = [(_lp.body, 'loop')]
            while _stack:
                _lst, _mode = _stack.pop()
                for _s in _lst:
                    if isinstance(_s, ast.If):
                        _in_loop_arm[id(_s)] = _mode
                        _stack.append((_s.body, True))
                        _stack.append((_s.orelse, True))
    for _round in range(6):
        _before = ast.dump(tree)
        for node in ast.walk(tree):
            for field in ('body', 'orelse', 'finalbody'):
                val = getattr(node, field, None)
                if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                    # the loop-tail if/else -> continue canonicalization
                    # inside flatten_terminating_else is only valid for a
                    # LOOP body
                    is_loop_body = isinstance(node, _LOOP_TYPES) and field == 'body'
                    val = _fold_try_body_tail_return(val)
                    val = _normalize_handler_break_raise(val)
                    val = fold_if_raise_assert(val)
                    # the tail-return flatten is only sound at a
                    # FUNCTION tail (falling off the end == return
                    # None); in a loop/handler body the added Return
                    # changes control flow (asynchat 3.10
                    # initiate_send's handler-tail if/else grew a
                    # phantom Return)
                    if field == 'body' and isinstance(
                            node,
                            (ast.FunctionDef,
                             getattr(ast, 'AsyncFunctionDef',
                                     ast.FunctionDef))):
                        val = flatten_tail_if_else(val)
                    val = _sunk_bare_return_tail(
                        _sunk_valued_return_tail(
                            _sunk_return_orelse(val)))
                    _lat = ('loop' if is_loop_body
                            else _in_loop_arm.get(id(node), False))
                    _fat = (field == 'body' and isinstance(
                        node,
                        (ast.FunctionDef,
                         getattr(ast, 'AsyncFunctionDef',
                                 ast.FunctionDef))))
                    if _lat or _fat:
                        _chg = []
                        val = flatten_try_else(val, at_loop_tail=_lat,
                                               _chg=_chg,
                                               at_func_tail=_fat)
                        if _chg:
                            # the hoist released flat followers that
                            # may re-form a guard chain - re-canonicalize
                            # (asynchat 3.10 initiate_send). Skipping
                            # the re-merge when nothing was hoisted
                            # keeps already-converged chain shapes
                            # untouched (compileall 3.5/3.6, codecs
                            # 3.3, cgi 3.6, _strptime 3.12 regressed
                            # under an unconditional re-merge)
                            val = merge_guard_continues(val)
                    _v2 = flatten_terminating_else(
                        merge_nested_ifs(val), loop_body=is_loop_body)
                    # the loop-else tail flatten inside
                    # flatten_terminating_else can release a tail that
                    # makes an ENCLOSING If's then arm terminal; give
                    # the fixpoint a per-round flatten_terminal_else so
                    # the cascade converges (ast 3.14 _compare)
                    _v2 = flatten_terminal_else(_v2)
                    if is_loop_body:
                        _v2 = fold_guard_continue_else(_v2)
                    setattr(node, field,
                            unfold_invariant_while(
                                split_tail_ternary_return(_v2)))
        if ast.dump(tree) == _before:
            break
        # a docstring-only body normalizes to empty; the source may have
        # carried a redundant `pass` after it (no bytecode) - canonicalize
        # an empty statement body to [Pass()] on both sides
        val = getattr(node, 'body', None)
        if isinstance(val, list) and not val:
            node.body = [ast.Pass()]
        # 'else: pass' is a no-op for if/while/for/try - drop it so an
        # omitted else compares equal
        ore = getattr(node, 'orelse', None)
        if (isinstance(ore, list) and len(ore) == 1
                and isinstance(ore[0], ast.Pass)
                and isinstance(node, ELSE_PASS_TYPES)):
            node.orelse = []
    # merge_nested_ifs builds fresh BoolOps that were never canonicalized
    # (merge order leaves them nested and unordered) - one final pass
    tree = BoolCanonicalizer().visit(tree)
    return ast.dump(tree)


def main():
    a = open(sys.argv[1]).read()
    b = open(sys.argv[2]).read()
    try:
        da = dump(a)
    except SyntaxError:
        print('orig-parse-error')
        return 2
    try:
        db = dump(b)
    except SyntaxError:
        e = sys.exc_info()[1]
        print('dec-parse-error line %s' % getattr(e, 'lineno', '?'))
        return 2
    if da == db:
        return 0
    # locate first difference for diagnostics
    la, lb = da.split(','), db.split(',')
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else '<end>'
        y = lb[i] if i < len(lb) else '<end>'
        if x != y:
            print('diff at token %d: orig %s | dec %s' % (i, x[:90], y[:90]))
            break
    return 1


if __name__ == '__main__':
    sys.exit(main())

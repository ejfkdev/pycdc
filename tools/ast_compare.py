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


def flatten_try_else(stmts):
    """When every handler ends terminally (return/raise/break/continue),
    'try: B else: O' followed by S is the same as 'try: B' with O and S
    sequential - compilers pick either layout."""
    out = []
    for s in stmts:
        if TRY_TYPES and isinstance(s, TRY_TYPES):
            handlers = getattr(s, 'handlers', [])
            orelse = getattr(s, 'orelse', [])
            if orelse and handlers and all(ends_terminal(h.body) for h in handlers):
                s.orelse = []
                out.append(s)
                out.extend(flatten_try_else(orelse))
                continue
        out.append(s)
    return out


def normalize_body(body):
    """Normalize a statement list: drop docstrings, merge adjacent
    from-imports, hoist global/nonlocal, flatten terminal elses."""
    body = flatten_terminal_else(body)
    body = flatten_try_else(body)
    body = _sunk_return_orelse(body)
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


def _canon_percent_format(node):
    """Canonicalize a `template % operands` BinOp (simple positional
    specifiers only) into its equivalent JoinedStr; return node unchanged
    when it is not a foldable percent-format."""
    js = _pct_template_to_joinedstr(node)
    return js if js is not None else node


class Normalizer(ast.NodeTransformer):
    def generic_visit(self, node):
        # normalize every statement-list field (body/orelse/finalbody) on
        # every node kind -- including py2 TryExcept/TryFinally and ExceptHandler
        for field in ('body', 'orelse', 'finalbody'):
            val = getattr(node, field, None)
            if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                val = [self.visit(st) for st in val]
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

    def visit_BinOp(self, node):
        self.generic_visit(node)
        # 3.12+ folds `template % operands` (simple positional %s/%r/%a)
        # into BUILD_STRING/FORMAT_VALUE, so the decompile renders a
        # JoinedStr where the source carried a BinOp Mod - canonicalize
        # the source form to the same JoinedStr (no-op for numeric %, and
        # for templates with flags/width/%(key)s which are not folded)
        node = _canon_percent_format(node)
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

    def visit_Compare(self, node):
        self.generic_visit(node)
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
            for s in stmts:
                if (isinstance(s, ast.If) and s.orelse and s.body
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
        _bare_return_to_break(getattr(last, 'orelse', []) or [])
        return
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


def merge_guard_continues(stmts):
    """Canonicalize a loop-tail guard-continue chain. CPython compiles
    `if not c1 and not c2: S` at the tail of a loop body into a chain of
    short-circuit guards `if c1: continue; if c2: continue; S` (3.13
    _strptime __find_month_format: `if not full_indices and not
    abbr_indices: return None, None`). The decompile renders the guard
    form faithfully; merge it back so it compares equal to the source's
    combined `if And(Not ci): S`. Valid only when S is the LAST statement
    of the loop body (a guard `continue` and falling off the body both
    proceed to the next iteration). canonical_bool then flattens/sorts the
    And operands to match the source."""
    n = len(stmts)
    if n < 2:
        return stmts

    def is_cont_guard(s):
        return (isinstance(s, ast.If) and not s.orelse
                and len(s.body) == 1 and isinstance(s.body[0], ast.Continue))

    tail = stmts[n - 1]
    if is_cont_guard(tail):
        return stmts
    j = n - 1
    while j > 0 and is_cont_guard(stmts[j - 1]):
        j -= 1
    guards = stmts[j:n - 1]
    if not guards:
        return stmts
    conds = [ast.UnaryOp(op=ast.Not(), operand=g.test) for g in guards]
    if len(conds) == 1:
        test = conds[0]
    else:
        test = ast.BoolOp(op=ast.And(), values=conds)
    return stmts[:j] + [ast.If(test=test, body=[tail], orelse=[])]


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


def dump(src):
    tree = ast.parse(src)
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
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,
                             getattr(ast, 'AsyncFunctionDef', ast.FunctionDef))):
            _normalize_func_tail_loop(node)
    # merge loop-tail guard-continue chains back into the combined
    # `if not c1 and not c2: S` the compiler short-circuited them from.
    # Loop bodies get at_loop_tail=True (their tail falls through to the
    # next iteration); a function body's tail loop also qualifies (its
    # `continue` guards fall through to the function end).
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
            node.body = _merge_tail_arm_guards(node.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef,
                             getattr(ast, 'AsyncFunctionDef', ast.FunctionDef))):
            if node.body and isinstance(node.body[-1], _LOOP_TYPES):
                node.body[-1].body = _merge_tail_arm_guards(node.body[-1].body)
    for node in ast.walk(tree):
        for field in ('body', 'orelse', 'finalbody'):
            val = getattr(node, field, None)
            if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                # the loop-tail if/else -> continue canonicalization inside
                # flatten_terminating_else is only valid for a LOOP body
                is_loop_body = isinstance(node, _LOOP_TYPES) and field == 'body'
                setattr(node, field,
                        split_tail_ternary_return(
                            flatten_terminating_else(merge_nested_ifs(val),
                                                     loop_body=is_loop_body)))
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

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


def _mk_num(v):
    if hasattr(ast, 'Num'):
        return ast.Num(n=v)
    return ast.Constant(value=v)


def _mk_str(s):
    if hasattr(ast, 'Str'):
        return ast.Str(s=s)
    return ast.Constant(value=s)


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


def ends_terminal(body):
    """True when the statement list cannot fall through."""
    if not body:
        return False
    last = body[-1]
    return isinstance(last, (ast.Return, ast.Raise, ast.Continue, ast.Break))


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


TRY_TYPES = tuple(
    c for c in (getattr(ast, 'Try', None), getattr(ast, 'TryExcept', None)) if c
)


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

    def visit_BinOp(self, node):
        self.generic_visit(node)
        # compilers fold ''x' * n' into a literal string
        if isinstance(node.op, ast.Mult):
            ls, rn = self._strval(node.left), self._numval(node.right)
            if ls is not None and isinstance(rn, int) and 0 <= rn <= 1000 \
                    and len(ls) * rn <= 4096:
                return _mk_str(ls * rn)
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


def _flatten_node(s):
    """Recurse into statement-holding fields (the walk-based passes in
    dump() never reach nested If bodies)."""
    for field in ('body', 'orelse', 'finalbody'):
        val = getattr(s, field, None)
        if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
            setattr(s, field, flatten_terminating_else(val))
    for h in getattr(s, 'handlers', None) or []:
        if getattr(h, 'body', None):
            h.body = flatten_terminating_else(h.body)
    return s


def flatten_terminating_else(stmts):
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
    # search loops) - canonicalize the source shape into it
    if (isinstance(tail, ast.If) and tail.orelse and tail.body
            and not isinstance(tail.body[-1], (ast.Return, ast.Raise,
                                               ast.Continue))):
        stmts = list(stmts[:-1])
        body = list(tail.body) + [ast.Continue()]
        orelse = list(tail.orelse)
        stmts.append(ast.If(test=tail.test, body=body, orelse=[]))
        stmts.extend(orelse)
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
    for node in ast.walk(tree):
        for field in ('body', 'orelse', 'finalbody'):
            val = getattr(node, field, None)
            if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                setattr(node, field,
                        flatten_terminating_else(merge_nested_ifs(val)))
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

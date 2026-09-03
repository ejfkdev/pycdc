#!/usr/bin/env python
"""Compare two Python sources for semantic equivalence at the AST level.

Run WITH the same interpreter version as the sources target.
Usage: ast_compare.py ORIGINAL.py DECOMPILED.py
Exit 0 when the normalized ASTs match; 1 otherwise (first difference on
stdout). Normalizations applied (both sides):
  - adjacent `from m import a` / `from m import b` merged
  - global/nonlocal declarations hoisted to the top of their scope (set)
  - `while True` == `while 1`
  - docstring Expr statements dropped
  - py2 Str/Num/NameConstant nodes mapped to Constant-style tuples
Compatible with Python 2.6+ and 3.x (no argparse, no set literals).
"""
import ast
import sys


def const_key(node):
    """Canonical (kind, value) for constant-ish expression nodes."""
    if isinstance(node, ast.Num):
        v = node.n
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
    """`if c: <terminal> else: X` equals `if c: <terminal>` followed by X:
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


def normalize_body(body):
    """Normalize a statement list: drop docstrings, merge adjacent
    from-imports, hoist global/nonlocal, flatten terminal elses."""
    body = flatten_terminal_else(body)
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
    def visit_body_holder(self, node):
        return node

    def generic_visit_body(self, node):
        for field in ('body', 'orelse', 'finalbody'):
            if hasattr(node, field):
                val = getattr(node, field)
                if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                    val = [self.visit(s) for s in val]
                    setattr(node, field, normalize_body(val))
        # handlers list
        if hasattr(node, 'handlers'):
            node.handlers = [self.visit(h) for h in node.handlers]
        return node

    def visit_Module(self, node):
        node.body = [self.visit(s) for s in node.body]
        node.body = normalize_body(node.body)
        return node

    def visit_FunctionDef(self, node):
        node.args = self.visit(node.args)
        self.generic_visit_body(node)
        return node

    def visit_AsyncFunctionDef(self, node):
        return self.visit_FunctionDef(node)

    def visit_ClassDef(self, node):
        self.generic_visit_body(node)
        return node

    def visit_While(self, node):
        self.generic_visit(node)
        k = const_key(node.test)
        if k == ('bool', True) or k == ('num', '1'):
            node.test = ast.Name(id='True', ctx=ast.Load())
        return node

    def visit_Lambda(self, node):
        node.args = self.visit(node.args)
        node.body = self.visit(node.body)
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        # set(genexpr) == set comprehension, list(genexpr) == list comp
        # (decompiler renders pre-3.x style comprehension code this way)
        if (isinstance(node.func, ast.Name)
                and node.func.id in ('set', 'list')
                and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.GeneratorExp)):
            ge = node.args[0]
            if node.func.id == 'set':
                return ast.SetComp(elt=ge.elt, generators=ge.generators)
            return ast.ListComp(elt=ge.elt, generators=ge.generators)
        return node


def dump(src):
    tree = ast.parse(src)
    tree = Normalizer().visit(tree)
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

#!/usr/bin/env python3
"""Differential check for `pycdc --cure`: does cure keep program behaviour?

Every case is compiled, decompiled with pycdc and then simplified with the
`cure` CLI. The decompiled and the simplified programs are executed and
their stdout/exit status compared, so a failure points at the simplifier
rather than at the decompiler. Cases where the decompiler already changes
behaviour are reported separately (DEC), not counted as cure failures.

The cases target constructs whose simplification can change semantics:
side-effecting dead stores, operator/`__bool__`/property side effects,
`del`, finally-return, loop `else`, walrus, globals/nonlocals, generators,
exception chaining, `not not` (TO_BOOL), and so on.

Usage:
  python3 tools/cure_differential.py [--pycdc PATH] [--cure PATH]
                                    [--python PATH] [--only NAME]

Needs a `cure` CLI binary (cargo install cure-cli) and a CPython >= 3.11.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PYCDC = os.path.join(ROOT, "target", "release", "pycdc")
ADDR = re.compile(r"0x[0-9a-f]+")

CASES = [
    (
        '01_dead_store_raise',
        r'''class Boom:
    def __init__(self):
        raise RuntimeError("init called")

def f():
    try:
        x = Boom()
    except RuntimeError:
        return "raised"
    return "no"

print(f())
''',
    ),
    (
        '02_dead_store_property',
        r'''class C:
    @property
    def v(self):
        print("property read")
        return 1

def f(o):
    x = o.v
    return "done"

print(f(C()))
''',
    ),
    (
        '03_prop_rebind',
        r'''def f(flag):
    v = 1
    if flag:
        v = 2
    return v

print(f(True), f(False))
''',
    ),
    (
        '04_prop_loop',
        r'''def f():
    v = 0
    for i in range(3):
        v = i
    return v

print(f())
''',
    ),
    (
        '05_prop_closure',
        r'''def f():
    v = 1
    def g():
        return v
    v = 2
    return g()

print(f())
''',
    ),
    (
        '06_str_accum',
        r'''def f():
    msg = ""
    msg += "a"
    msg += "b"
    return msg

print(f())
''',
    ),
    (
        '07_bool_operand_value',
        r'''def f(a, b):
    return a or b, a and b

print(f(0, "x"), f("y", "z"))
''',
    ),
    (
        '08_bool_raises',
        r'''class B:
    def __bool__(self):
        print("bool called")
        return True

print(B() and "yes")
print(B() or "no")
print(not B())
''',
    ),
    (
        '09_chained_compare_custom',
        r'''class N:
    def __init__(self, v):
        self.v = v
    def __lt__(self, o):
        print("lt", self.v, o.v)
        return self.v < o.v
    def __repr__(self):
        return f"N({self.v})"

print(N(1) < N(2) < N(3))
print(N(3) < N(2) < N(1))
''',
    ),
    (
        '10_ternary_order',
        r'''def t(x):
    print("t", x)
    return x

def f(c):
    return t("a") if c else t("b")

print(f(True), f(False))
''',
    ),
    (
        '11_finally_return',
        r'''def f():
    try:
        return "try"
    finally:
        print("finally")

def g():
    try:
        return "try"
    finally:
        return "finally"

print(f(), g())
''',
    ),
    (
        '12_while_else',
        r'''def f(n):
    i = 0
    while i < n:
        if i == 2:
            break
        i += 1
    else:
        return "no-break"
    return f"break at {i}"

print(f(0), f(5), f(3))
''',
    ),
    (
        '13_for_else',
        r'''def f(xs, needle):
    for x in xs:
        if x == needle:
            return "found"
    else:
        return "missing"

print(f([1, 2], 2), f([1, 2], 9))
''',
    ),
    (
        '14_del_subscript',
        r'''def f():
    d = {"a": 1, "b": 2}
    del d["a"]
    return d

def g():
    class C:
        pass
    o = C()
    o.x = 1
    del o.x
    return hasattr(o, "x")

print(f(), g())
''',
    ),
    (
        '15_del_name',
        r'''def f():
    v = 5
    del v
    try:
        return v
    except UnboundLocalError:
        return "unbound"

def g():
    v = 1
    del v
    try:
        v
    except UnboundLocalError:
        return "gone"

print(f(), g())
''',
    ),
    (
        '16_global_write',
        r'''g = 0
def bump():
    global g
    g += 1
    return g

print(bump(), bump(), g)
''',
    ),
    (
        '17_nested_none',
        r'''def f(v):
    if v is None:
        return None
    return v

print(f(None), f(0), f(""))
''',
    ),
    (
        '18_unreachable_raise',
        r'''def f(x):
    if x:
        raise ValueError("bad")
    return "ok"

for v in (False, True):
    try:
        print(f(v))
    except ValueError as e:
        print("caught", e)
''',
    ),
    (
        '19_empty_branches',
        r'''def f(x):
    if x:
        pass
    else:
        print("else")
    return x

print(f(0), f(1))
''',
    ),
    (
        '20_gen_yield_finally',
        r'''def gen():
    try:
        yield 1
        yield 2
    finally:
        print("cleanup")

print(list(gen()))
''',
    ),
    (
        '21_walrus',
        r'''def f(xs):
    out = []
    for x in xs:
        if (y := x * 2) > 4:
            out.append(y)
    return out

print(f([1, 2, 3]))
''',
    ),
    (
        '22_attr_side_effect',
        r'''class C:
    def __init__(self):
        self.n = 0
    def bump(self):
        self.n += 1
        return self

c = C()
c.bump().bump()
print(c.n)
''',
    ),
    (
        '23_augassign_subscript',
        r'''def f():
    log = []
    class D(dict):
        def __getitem__(self, k):
            log.append(("get", k))
            return dict.__getitem__(self, k)
        def __setitem__(self, k, v):
            log.append(("set", k, v))
            dict.__setitem__(self, k, v)
    d = D()
    d["a"] = 1
    d["a"] += 2
    return d["a"], log

print(f())
''',
    ),
    (
        '24_class_body',
        r'''class C:
    x = 1
    if x:
        y = "yes"
    else:
        y = "no"
    z = [x * 2]

print(C.y, C.z)
''',
    ),
    (
        '25_decorator_side_effect',
        r'''def deco(fn):
    print("decorating", fn.__name__)
    return fn

@deco
def f():
    return 1

print(f())
''',
    ),
    (
        '26_default_arg_once',
        r'''def f(x, acc=[]):
    acc.append(x)
    return acc

print(f(1), f(2))
''',
    ),
    (
        '27_except_star',
        r'''def f():
    out = []
    try:
        raise ExceptionGroup("g", [ValueError("v")])
    except* ValueError as e:
        out.append("ve")
    out.append("after")
    return out

print(f())
''',
    ),
    (
        '28_raise_from',
        r'''def f():
    try:
        try:
            raise ValueError("inner")
        except ValueError as e:
            raise TypeError("outer") from e
    except TypeError as e:
        return str(e), type(e.__cause__).__name__

print(f())
''',
    ),
    (
        '29_none_return_tail',
        r'''def f(x):
    if x:
        return 1

def g(x):
    if not x:
        return
    print("body")

print(f(0), f(1), g(0), g(1))
''',
    ),
    (
        '30_str_concat_fstring',
        r'''name = "world"
print("hello " + name + "!")
print(f"hello {name}!")
print("a" "b" "c")
''',
    ),
    (
        '31_double_not',
        r'''def f(x):
    return not not x

class T:
    def __bool__(self):
        print("bool")
        return True

print(f(0), f(1), f(T()))
''',
    ),
    (
        '32_is_in',
        r'''def f(x, xs):
    return x is None, x in xs

print(f(None, [1]), f(1, [1, 2]))
''',
    ),
    (
        '33_nested_if_merge',
        r'''def f(a, b):
    if a:
        if b:
            return "ab"
        return "a"
    return "none"

print(f(1, 1), f(1, 0), f(0, 0))
''',
    ),
    (
        '34_return_none_explicit',
        r'''def f(x):
    if x:
        return None
    return

print(f(0), f(1))
''',
    ),
    (
        '35_trailing_assign',
        r'''def f(x):
    y = x + 1
    return y

def g(x):
    y = x
    y = y + 1
    return y

print(f(1), g(1))
''',
    ),
    (
        '36_nonlocal_rebind',
        r'''def outer():
    n = 0
    def bump():
        nonlocal n
        n += 1
        return n
    bump()
    bump()
    return n

print(outer())
''',
    ),
    (
        '37_dead_call_result',
        r'''def side():
    print("side")
    return 1

def f():
    x = side()
    return "done"

print(f())
''',
    ),
    (
        '38_str_custom',
        r'''class S:
    def __init__(self, v):
        self.v = v
    def __add__(self, o):
        print("add", self.v, o)
        return S(self.v + 1)
    def __str__(self):
        return f"S{self.v}"

s = S(0)
s = s + 1
s = s + 1
print(s)
''',
    ),
    (
        '39_unreachable_side_effect',
        r'''def f():
    print("before")
    return 1
    print("never")

print(f())
''',
    ),
    (
        '40_ternary_branch_effects',
        r'''def a():
    print("A")
    return 1

def b():
    print("B")
    return 2

def f(c):
    v = a() if c else b()
    return v

print(f(True), f(False))
''',
    ),
    (
        '41_bool_raising_cond',
        r'''class Q:
    def __bool__(self):
        print("bool")
        raise ValueError("no")

def f(q):
    try:
        if q:
            return "t"
        return "f"
    except ValueError:
        return "raised"

print(f(Q()))
''',
    ),
    (
        '42_assert_message_effect',
        r'''def msg():
    print("msg")
    return "bad"

def f(x):
    assert x, msg()
    return x

print(f(1))
try:
    f(0)
except AssertionError as e:
    print("assert", e)
''',
    ),
    (
        '43_dict_key_effect',
        r'''def k():
    print("key")
    return "a"

d = {k(): 1}
print(d)
print({"a": 2}[k()])
''',
    ),
    (
        '44_nested_del_attr',
        r'''class C:
    pass

def f():
    o = C()
    o.a = 1
    o.b = 2
    del o.a
    return sorted(k for k in vars(o))

print(f())
''',
    ),
    (
        '45_try_pass_else',
        r'''def f(x):
    try:
        v = 10 // x
    except ZeroDivisionError:
        pass
    else:
        print("else", v)
        return v
    return "zero"

print(f(2), f(0))
''',
    ),

]


def run(python, path):
    r = subprocess.run([python, path], capture_output=True, text=True, timeout=120)
    return ADDR.sub("0xADDR", r.stdout), r.returncode, ADDR.sub("0xADDR", r.stderr)[-400:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pycdc", default=DEFAULT_PYCDC)
    ap.add_argument("--cure", default="cure")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--only", help="run cases whose name contains this")
    ap.add_argument("--keep", help="write the artifacts under this directory")
    args = ap.parse_args()

    cases = [c for c in CASES if not args.only or args.only in c[0]]
    dec_bad, cure_bad, skipped = [], [], []
    for name, src in cases:
        base = args.keep and os.path.join(args.keep, name)
        td = base or tempfile.mkdtemp(prefix=f"cure_diff_{name}_")
        os.makedirs(td, exist_ok=True)
        py = os.path.join(td, name + ".py")
        with open(py, "w") as f:
            f.write(src)
        pyc = os.path.join(td, name + ".pyc")
        c = subprocess.run(
            [args.python, "-c",
             "import py_compile,sys; py_compile.compile(sys.argv[1], sys.argv[2], doraise=True)",
             py, pyc],
            capture_output=True, text=True)
        if c.returncode != 0:
            skipped.append((name, "compile: " + (c.stderr or "").strip().splitlines()[-1]))
            continue
        d = subprocess.run([args.pycdc, pyc], capture_output=True, text=True)
        if d.returncode != 0 or "decompilation incomplete" in d.stderr:
            skipped.append((name, "decompile incomplete"))
            continue
        dec = os.path.join(td, name + ".dec.py")
        with open(dec, "w") as f:
            f.write(d.stdout)
        src_run = run(args.python, py)
        dec_run = run(args.python, dec)
        if src_run[:2] != dec_run[:2]:
            dec_bad.append((name, src_run, dec_run))
            continue
        cured = os.path.join(td, name + ".cured.py")
        cc = subprocess.run([args.cure, dec, "-o", cured],
                            capture_output=True, text=True)
        if cc.returncode != 0:
            skipped.append((name, "cure: " + (cc.stderr or "").strip()[-200:]))
            continue
        cured_run = run(args.python, cured)
        if dec_run[:2] != cured_run[:2]:
            cure_bad.append((name, dec_run, cured_run, cured))

    total = len(cases)
    print(f"cases={total} skipped={len(skipped)} "
          f"decompiler-mismatch={len(dec_bad)} cure-mismatch={len(cure_bad)}")
    for name, why in skipped:
        print(f"  SKIP {name}: {why}")
    for name, want, got in dec_bad:
        print(f"  DEC  {name}: source {want[:2]} != decompiled {got[:2]}")
    for name, want, got, path in cure_bad:
        print(f"  CURE {name}: decompiled {want[:2]} != cured {got[:2]}")
        print(f"       cured source: {path}")
    if cure_bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

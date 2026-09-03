#!/usr/bin/env python3
"""Round-trip test harness for the Rust pycdc.

For each (interpreter, fixture): compile the fixture to a pyc, decompile it
with target/debug/pycdc, recompile the decompiled source with the same
interpreter, and compare structural disassembly of both code objects
(opnames + argreprs, addresses/lines/offsets normalized).

Usage: python3 tests/roundtrip.py [--only NAME] [--list-versions]
"""
import argparse
import dis
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYCDC = os.path.join(ROOT, "target", "debug", "pycdc")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

INTERPRETERS = [
    ("3.9", "/usr/bin/python3"),
    ("3.10", os.path.expanduser("~/.local/share/uv/python/cpython-3.10-macos-aarch64-none/bin/python3.10")),
    ("3.11", os.path.expanduser("~/.local/share/uv/python/cpython-3.11-macos-aarch64-none/bin/python3.11")),
    ("3.12", os.path.expanduser("~/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12")),
    ("3.13", "/opt/homebrew/bin/python3.13"),
    ("3.14", "/opt/homebrew/bin/python3.14"),
]


def structural_dump(pyc_path, interp):
    """Return a normalized structural signature of a pyc's code objects."""
    script = r"""
import dis, marshal, sys, types

def sig(code, out):
    out.append((code.co_name, code.co_argcount))
    insts = list(dis.get_instructions(code))
    skip = set()
    for i, inst in enumerate(insts):
        # __firstlineno__ reflects source line numbering of the text, which
        # legitimately shifts after decompile; drop it and its LOAD_CONST
        if inst.opname == 'STORE_NAME' and inst.argrepr in (
                '__firstlineno__', '__static_attributes__'):
            skip.add(i)
            if i > 0 and insts[i - 1].opname in ('LOAD_CONST', 'LOAD_SMALL_INT'):
                skip.add(i - 1)
    for i, inst in enumerate(insts):
        if i in skip:
            continue
        r = inst.argrepr
        # normalize code-object and function reprs
        if r.startswith('<code object'):
            r = '<code %s>' % r.split()[2]
        out.append((inst.opname, r))
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            sig(c, out)

data = open(sys.argv[1], 'rb').read()
magic = int.from_bytes(data[:2], 'little')
off = 16 if magic >= 3390 else (12 if magic >= 3200 else 8)
code = marshal.loads(data[off:])
out = []
sig(code, out)
for item in out:
    print(repr(item))
"""
    p = subprocess.run([interp, "-c", script, pyc_path], capture_output=True, text=True)
    if p.returncode != 0:
        return None, p.stderr
    return p.stdout, None


def compile_fixture(interp, src_path, out_pyc):
    code = "import py_compile; py_compile.compile(%r, %r, doraise=True)" % (src_path, out_pyc)
    p = subprocess.run([interp, "-c", code], capture_output=True, text=True)
    return p.returncode == 0, p.stderr


def run_case(interp_name, interp, fixture, verbose=False):
    src = os.path.join(FIXTURES, fixture)
    with tempfile.TemporaryDirectory() as td:
        pyc = os.path.join(td, "f.pyc")
        ok, err = compile_fixture(interp, src, pyc)
        if not ok:
            return "COMPILE-ERR", err[-400:]
        p = subprocess.run([PYCDC, pyc], capture_output=True, text=True)
        if p.returncode != 0:
            return "DEC-ERR", (p.stderr or "")[-400:]
        decompiled = p.stdout
        out_py = os.path.join(td, "out.py")
        with open(out_py, "w") as f:
            f.write(decompiled)
        pyc2 = os.path.join(td, "f2.pyc")
        ok, err = compile_fixture(interp, out_py, pyc2)
        if not ok:
            return "RECOMPILE-ERR", err[-600:] + "\n--- source ---\n" + decompiled[:1500]
        sig1, e1 = structural_dump(pyc, interp)
        sig2, e2 = structural_dump(pyc2, interp)
        if sig1 is None or sig2 is None:
            return "SIG-ERR", (e1 or "") + (e2 or "")
        if sig1 == sig2:
            return "PASS", ""
        # diff summary
        l1 = sig1.splitlines()
        l2 = sig2.splitlines()
        diff = []
        for i in range(max(len(l1), len(l2))):
            a = l1[i] if i < len(l1) else "<missing>"
            b = l2[i] if i < len(l2) else "<missing>"
            if a != b:
                diff.append("  line %d:\n    orig: %s\n    got : %s" % (i, a, b))
            if len(diff) >= 3:
                break
        note = " [incomplete]" if "WARNING: Decompyle incomplete" in (p.stderr or "") else ""
        return "DIFF" + note, "\n".join(diff) + ("\n--- source ---\n" + decompiled[:1200] if verbose else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="only run fixture whose name contains this")
    ap.add_argument("--version", help="only run this interpreter version")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    fixtures = sorted(f for f in os.listdir(FIXTURES) if f.endswith(".py"))
    if args.only:
        fixtures = [f for f in fixtures if args.only in f]

    total = passed = 0
    results = {}
    for ver, interp in INTERPRETERS:
        if args.version and ver != args.version:
            continue
        if not os.path.exists(interp):
            print("skip %s (interpreter missing: %s)" % (ver, interp))
            continue
        for fx in fixtures:
            total += 1
            status, detail = run_case(ver, interp, fx, args.verbose)
            results[(ver, fx)] = status
            if status == "PASS":
                passed += 1
            else:
                print("== FAIL %s / %s: %s" % (ver, fx, status))
                if detail:
                    print(detail)
    # matrix
    print()
    hdr = "%-24s" % "fixture" + "".join("%-8s" % v for v, i in INTERPRETERS if os.path.exists(i))
    print(hdr)
    for fx in fixtures:
        row = "%-24s" % fx
        for ver, interp in INTERPRETERS:
            if not os.path.exists(interp):
                continue
            st = results.get((ver, fx), "-")
            mark = "PASS" if st == "PASS" else st.split()[0][:7]
            row += "%-8s" % mark
        print(row)
    print("\n%d/%d passed" % (passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

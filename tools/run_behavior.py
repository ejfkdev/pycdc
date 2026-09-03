#!/usr/bin/env python3
"""Behavior-equivalence test matrix.

For each (case, interpreter version):
  1. compile the case source with THAT interpreter -> pyc
  2. decompile the pyc with pycdc
  3. run BOTH the original source and the decompiled source with the
     same interpreter and compare stdout+returncode
Verdicts: PASS / DIFF (output differs, detail=first diff line) /
DECOMP-ERR (pycdc failed) / ORIG-ERR (case itself fails on this
interpreter, skipped silently as N/A).

Usage:
  python3 tools/run_behavior.py [--version X.Y[.Z]] [--case NAME]
                                [--pycdc PATH] [--jobs N] [--quiet]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "tests", "behavior", "cases")
DEFAULT_PYCDC = os.path.join(ROOT, "target", "release", "pycdc")


def find_interpreters():
    found = {}
    pats = []
    home = os.path.expanduser("~")
    pats += glob.glob(home + "/.pyenv/versions/*/bin/python3")
    pats += glob.glob(home + "/.pyenv/versions/*/bin/python")
    pats += glob.glob(home + "/.local/share/uv/python/cpython-*/bin/python3.*")
    pats += glob.glob("/opt/homebrew/bin/python3.*")
    for p in pats:
        if not os.path.exists(p) or not os.access(p, os.X_OK):
            continue
        try:
            out = subprocess.run(
                [p, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
                capture_output=True, text=True, timeout=30)
            if out.returncode != 0:
                continue
            v = out.stdout.strip().splitlines()[-1]
            found.setdefault(v, p)
        except Exception:
            continue
    best = {}
    for v, p in found.items():
        parts = tuple(int(x) for x in v.split("."))
        xy = parts[:2]
        if xy not in best or parts > best[xy][0]:
            best[xy] = (parts, v, p)
    return {v: p for _, v, p in best.values()}


def case_gate(path):
    lo, hi = (2, 6), (99, 99)
    with open(path, encoding="utf-8", errors="replace") as f:
        head = f.read(400)
    m = re.search(r"MIN_VERSION:\s*(\d+)\.(\d+)", head)
    if m:
        lo = (int(m.group(1)), int(m.group(2)))
    m = re.search(r"MAX_VERSION:\s*(\d+)\.(\d+)", head)
    if m:
        hi = (int(m.group(1)), int(m.group(2)))
    return lo, hi


def compile_case(interp, src, td):
    pyc = os.path.join(td, "case.pyc")
    code = ("import py_compile; py_compile.compile(%r, %r, doraise=True)"
            % (src, pyc))
    r = subprocess.run([interp, "-c", code], capture_output=True, text=True,
                       timeout=120)
    if r.returncode != 0 or not os.path.exists(pyc):
        # py2.5 and older lack py_compile signature; fallback
        code2 = ("import imp, sys; f=open(%r,'rb'); "
                 "src=f.read(); f.close(); "
                 "compile(src, %r, 'exec')" % (src, src))
        return None
    return pyc


def run_py(interp, path, cwd):
    try:
        r = subprocess.run([interp, path], capture_output=True, text=True,
                           timeout=120, cwd=cwd)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -99, "", "timeout"


def run_case(interp, ver, pycdc, case_path, keep):
    name = os.path.basename(case_path)[:-3]
    res = {"case": name, "version": ver}
    with tempfile.TemporaryDirectory() as td:
        # 1. original run
        rc0, out0, err0 = run_py(interp, case_path, td)
        if rc0 != 0:
            res["verdict"] = "N/A"
            res["detail"] = (err0 or "").strip().splitlines()[-1:][0:1] and \
                (err0 or "").strip().splitlines()[-1][:120] or "orig failed"
            return res
        # 2. compile -> pyc
        pyc = compile_case(interp, case_path, td)
        if pyc is None:
            res["verdict"] = "N/A"
            res["detail"] = "compile failed"
            return res
        # 3. decompile
        d = subprocess.run([pycdc, pyc], capture_output=True, text=True,
                           timeout=120)
        if d.returncode != 0:
            res["verdict"] = "DECOMP-ERR"
            res["detail"] = (d.stderr or "")[-200:]
            return res
        dec_src = d.stdout
        dec_warn = "WARNING" in (d.stderr or "") or "/*" in dec_src
        dec_path = os.path.join(td, name + "_dec.py")
        with open(dec_path, "w") as f:
            f.write(dec_src)
        # 4. run decompiled
        rc1, out1, err1 = run_py(interp, dec_path, td)
        res["warned"] = dec_warn
        if rc1 != 0:
            res["verdict"] = "RUNTIME-ERR"
            last = [l for l in (err1 or "").strip().splitlines() if l.strip()]
            res["detail"] = (last[-1][:160] if last else "rc=%d" % rc1)
            return res
        if out1 == out0:
            res["verdict"] = "PASS" if not dec_warn else "PASS-WARN"
            return res
        # diff
        l0, l1 = out0.splitlines(), out1.splitlines()
        diff = None
        for i in range(max(len(l0), len(l1))):
            a = l0[i] if i < len(l0) else "<eof>"
            b = l1[i] if i < len(l1) else "<eof>"
            if a != b:
                diff = "line %d: want %r got %r" % (i + 1, a[:70], b[:70])
                break
        res["verdict"] = "DIFF"
        res["detail"] = diff or ""
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="only this X.Y or X.Y.Z")
    ap.add_argument("--case", help="only cases whose name contains this")
    ap.add_argument("--pycdc", default=DEFAULT_PYCDC)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", help="write results json here")
    args = ap.parse_args()

    interps = find_interpreters()
    cases = sorted(glob.glob(os.path.join(CASES, "*.py")))
    if args.case:
        cases = [c for c in cases if args.case in os.path.basename(c)]
    results = []
    for ver in sorted(interps, key=lambda v: tuple(map(int, v.split(".")))):
        if args.version and not ver.startswith(args.version):
            continue
        xy = tuple(int(x) for x in ver.split(".")[:2])
        interp = interps[ver]
        tasks = []
        for c in cases:
            lo, hi = case_gate(c)
            if not (lo <= xy <= hi):
                continue
            tasks.append(c)
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(run_case, interp, ver, args.pycdc, c, False)
                    for c in tasks]
            for f in futs:
                results.append(f.result())
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("TOTAL:", "  ".join("%s=%d" % kv for kv in sorted(counts.items())))
    good = counts.get("PASS", 0) + counts.get("PASS-WARN", 0)
    run_total = len(results) - counts.get("N/A", 0)
    if run_total:
        print("behavior pass rate: %d/%d = %.1f%%"
              % (good, run_total, 100.0 * good / run_total))
    if not args.quiet:
        cur = None
        for r in sorted(results, key=lambda r: (r["version"], r["case"])):
            if r["verdict"] in ("PASS", "N/A"):
                continue
            if r["version"] != cur:
                cur = r["version"]
                print("--- %s" % cur)
            print("   %-18s %-12s %s" % (r["case"], r["verdict"],
                                         (r.get("detail") or "")[:110]))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()

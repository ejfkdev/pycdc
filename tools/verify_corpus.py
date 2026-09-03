#!/usr/bin/env python3
"""Corpus verification driver (runs on any modern Python 3).

For each tests/corpus/<X.Y.Z>/ directory:
  1. run pycdc on every <module>.pyc            -> out/<module>.py
  2. recompile out/<module>.py with the SAME Python version
  3. compute structural signatures of the original pyc and the recompiled
     pyc (tools/sig_dump.py executed by that interpreter) and compare

Verdicts:
  PASS        signatures identical (semantic + structural equivalence)
  AST-PASS    bytecode differs, but the normalized AST of the decompiled
              source is equivalent to the original source (semantic pass)
  INCOMPLETE  decompiler emitted /* ... */ markers or a WARNING
  SYNTAX-ERR  decompiled source does not compile
  SIG-DIFF    compiles, but bytecode structure differs (first diff reported)
  DEC-ERR     pycdc failed to load/decompile
  NO-INTERP   no interpreter found for this version

Usage:
  python3 tools/verify_corpus.py [--version X.Y[.Z]] [--module NAME]
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
CORPUS = os.path.join(ROOT, "tests", "corpus")
SIG_DUMP = os.path.join(ROOT, "tools", "sig_dump.py")
AST_COMPARE = os.path.join(ROOT, "tools", "ast_compare.py")
DEFAULT_PYCDC = os.path.join(ROOT, "target", "release", "pycdc")


def find_interpreters():
    """version string -> interpreter path"""
    found = {}
    pats = []
    home = os.path.expanduser("~")
    pats += glob.glob(home + "/.pyenv/versions/*/bin/python3")
    pats += glob.glob(home + "/.pyenv/versions/*/bin/python")
    pats += glob.glob(home + "/.local/share/uv/python/cpython-*/bin/python3.*")
    pats += glob.glob("/opt/homebrew/bin/python3.*")
    pats += glob.glob("/opt/homebrew/opt/python@3.*/bin/python3.*")
    pats += ["/usr/bin/python3"]
    for p in pats:
        if not os.path.exists(p) or not os.access(p, os.X_OK):
            continue
        try:
            out = subprocess.run([p, "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
                                 capture_output=True, text=True, timeout=20)
            if out.returncode != 0:
                continue
            v = out.stdout.strip().splitlines()[-1]
            found.setdefault(v, p)
        except Exception:
            continue
    # keep only the newest patch release per X.Y series
    best = {}
    for v, p in found.items():
        parts = tuple(int(x) for x in v.split("."))
        xy = parts[:2]
        if xy not in best or parts > best[xy][0]:
            best[xy] = (parts, v, p)
    return {v: p for _, v, p in best.values()}


def sig_of(interp, pyc_path):
    p = subprocess.run([interp, SIG_DUMP, pyc_path], capture_output=True, text=True)
    if p.returncode != 0:
        return None, p.stderr[-500:]
    return p.stdout, None


def verify_module(interp, pycdc, vdir, pyc, outdir, keep):
    name = os.path.basename(pyc)[:-4]
    out_py = os.path.join(outdir, name + ".py")
    result = {"module": name}
    # 1. decompile
    p = subprocess.run([pycdc, pyc], capture_output=True, text=True)
    if p.returncode != 0:
        result["verdict"] = "DEC-ERR"
        result["detail"] = (p.stderr or "")[-300:]
        return result
    src = p.stdout
    warned = "WARNING: Decompyle incomplete" in (p.stderr or "") or "/*" in src
    with open(out_py, "w") as f:
        f.write(src)
    # 2. recompile with the same interpreter
    with tempfile.TemporaryDirectory() as td:
        pyc2 = os.path.join(td, "re.pyc")
        code = ("import py_compile; py_compile.compile(%r, %r, doraise=True)"
                % (out_py, pyc2))
        c = subprocess.run([interp, "-c", code], capture_output=True, text=True)
        if c.returncode != 0:
            err = c.stderr
            m = re.search(r"SyntaxError[^\n]*", err)
            result["verdict"] = "SYNTAX-ERR" if (warned or m) else "SYNTAX-ERR"
            result["detail"] = (m.group(0) if m else err[-300:])[:300]
            if warned:
                result["verdict"] = "INCOMPLETE"
            return result
        # 3. structural signatures
        s1, e1 = sig_of(interp, pyc)
        s2, e2 = sig_of(interp, pyc2)
        if s1 is None or s2 is None:
            result["verdict"] = "SIG-ERR"
            result["detail"] = (e1 or "") + (e2 or "")
            return result
    if s1 == s2:
        result["verdict"] = "PASS"
        return result
    # semantic equivalence: normalized-AST comparison against the original
    # source (the user's correctness bar); only meaningful when the output
    # carries no incompleteness markers
    orig_py = os.path.join(vdir, name + ".py")
    if not warned and os.path.exists(orig_py):
        a = subprocess.run([interp, AST_COMPARE, orig_py, out_py],
                           capture_output=True, text=True)
        if a.returncode == 0:
            result["verdict"] = "AST-PASS"
            return result
        result["ast_detail"] = (a.stdout or "").strip()[:200]
    if warned:
        result["verdict"] = "INCOMPLETE"
    else:
        result["verdict"] = "SIG-DIFF"
    l1, l2 = s1.splitlines(), s2.splitlines()
    diff = []
    ndiff = 0
    for i in range(max(len(l1), len(l2))):
        a = l1[i] if i < len(l1) else "<missing>"
        b = l2[i] if i < len(l2) else "<missing>"
        if a != b:
            ndiff += 1
            if len(diff) < 3:
                diff.append("line %d: orig %s | got %s" % (i, a[:100], b[:100]))
    result["ndiff"] = ndiff
    result["ntotal"] = max(len(l1), len(l2))
    result["detail"] = "\n".join(diff)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", help="only this X.Y or X.Y.Z")
    ap.add_argument("--module", help="only modules whose name contains this")
    ap.add_argument("--pycdc", default=DEFAULT_PYCDC)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    interps = find_interpreters()
    vdirs = sorted(
        d for d in os.listdir(CORPUS)
        if os.path.isdir(os.path.join(CORPUS, d)) and re.match(r"^\d+\.\d+", d)
    )
    if args.version:
        vdirs = [d for d in vdirs if d.startswith(args.version)]

    summary = {}
    for vd in vdirs:
        vdir = os.path.join(CORPUS, vd)
        pyvs = vd.rsplit(".", 1)[0]  # X.Y
        interp = interps.get(vd)
        if interp is None:
            for k, v in interps.items():
                if k.rsplit(".", 1)[0] == pyvs:
                    interp = v
                    break
        pycs = sorted(glob.glob(os.path.join(vdir, "*.pyc")))
        if args.module:
            pycs = [p for p in pycs if args.module in os.path.basename(p)]
        if interp is None:
            summary[vd] = {"verdict": "NO-INTERP", "count": len(pycs)}
            print("%-10s NO-INTERP (%d pycs)" % (vd, len(pycs)))
            continue
        outdir = os.path.join(vdir, "out")
        os.makedirs(outdir, exist_ok=True)
        results = []
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = [
                ex.submit(verify_module, interp, args.pycdc, vdir, p, outdir, True)
                for p in pycs
            ]
            for f in futs:
                results.append(f.result())
        counts = {}
        for r in results:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        summary[vd] = {"interp": interp, "counts": counts, "results": results}
        line = "%-10s %s" % (vd, "  ".join("%s=%d" % kv for kv in sorted(counts.items())))
        print(line)
        if not args.quiet:
            for r in results:
                if r["verdict"] not in ("PASS",):
                    print("   %-24s %-11s %s" % (
                        r["module"], r["verdict"],
                        (r.get("detail", "") or "").splitlines()[0][:110]
                        if r.get("detail") else ""))
        with open(os.path.join(vdir, "report.json"), "w") as f:
            json.dump({"version": vd, "interp": interp, "counts": counts,
                       "results": results}, f, indent=1)

    # overall
    tot = {}
    for vd, s in summary.items():
        if "counts" in s:
            for k, v in s["counts"].items():
                tot[k] = tot.get(k, 0) + v
    print("\nTOTAL:", "  ".join("%s=%d" % kv for kv in sorted(tot.items())))
    # aggregate closeness: modules with small diffs
    near = 0
    for vd, s2_ in summary.items():
        for r in s2_.get("results", []):
            if r["verdict"] in ("SIG-DIFF", "INCOMPLETE") and r.get("ndiff", 999) <= 5:
                near += 1
    print("near-pass (<=5 diff lines):", near)
    n = sum(tot.values())
    if n:
        good = tot.get("PASS", 0)
        sem = good + tot.get("AST-PASS", 0)
        print("strict pass rate: %d/%d = %.1f%%" % (good, n, 100.0 * good / n))
        print("semantic pass rate (PASS+AST-PASS): %d/%d = %.1f%%" % (sem, n, 100.0 * sem / n))
    with open(os.path.join(CORPUS, "summary.json"), "w") as f:
        json.dump({vd: {k: v for k, v in s.items() if k != "results"}
                   for vd, s in summary.items()}, f, indent=1)


if __name__ == "__main__":
    main()

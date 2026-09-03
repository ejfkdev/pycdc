#!/usr/bin/env python3
"""Build a multi-version pyc corpus from each Python release's own stdlib.

For version X.Y.Z (run with that version's interpreter):
  * select a deterministic set of stdlib .py modules
  * compile each to tests/corpus/<X.Y.Z>/<module>.pyc
  * copy the source to tests/corpus/<X.Y.Z>/<module>.py

Usage (via build_corpus.sh or directly):
  <interp> tools/build_corpus.py --stdlib DIR --out DIR [--limit N]
"""
import argparse
import os
import py_compile
import sys

# modules that are known to be problematic to compile standalone or are
# platform/generated noise
SKIP_NAMES = {
    "this", "antigravity", "__phello__", "_pydecimal",
}
SKIP_DIRS = {
    "test", "tests", "site-packages", "lib2to3", "idle_test", "venv",
    "distutils", "lib-tk", "lib2to3", "encodings", "email", "importlib",
    "json", "logging", "unittest", "xml", "http", "asyncio", "collections",
    "concurrent", "ctypes", "curses", "dbm", "sqlite3", "wsgiref",
    "multiprocessing", "tkinter", "ensurepip", "libpasteurize", "future",
    "idlelib", "pydoc_data", "venv", "__phello__", "msilib",
}


def candidates(stdlib):
    out = []
    for name in sorted(os.listdir(stdlib)):
        path = os.path.join(stdlib, name)
        if os.path.isdir(path):
            if name in SKIP_DIRS or name.startswith((".", "_")):
                continue
            # one level down: packages like re/, but keep it simple: only
            # top-level modules are used
            continue
        if not name.endswith(".py"):
            continue
        base = name[:-3]
        if base in SKIP_NAMES:
            continue
        size = os.path.getsize(path)
        if size < 200 or size > 60000:
            continue
        out.append(path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdlib", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    if not os.path.isdir(args.out):
        os.makedirs(args.out)
    picked = 0
    failed = []
    for src in candidates(args.stdlib):
        if picked >= args.limit:
            break
        base = os.path.basename(src)[:-3]
        pyc = os.path.join(args.out, base + ".pyc")
        try:
            py_compile.compile(src, cfile=pyc, doraise=True)
        except Exception as e:
            failed.append((base, str(e)[:120]))
            continue
        with open(src, "rb") as f:
            data = f.read()
        with open(os.path.join(args.out, base + ".py"), "wb") as f:
            f.write(data)
        picked += 1
    ver = sys.version.split()[0]
    print("python %s: picked %d modules into %s" % (ver, picked, args.out))
    for b, e in failed:
        print("  compile-skip %s: %s" % (b, e))


if __name__ == "__main__":
    main()

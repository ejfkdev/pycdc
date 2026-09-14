#!/usr/bin/env python3
"""Build a multi-version pyc corpus from each Python release's own stdlib.

For version X.Y.Z (run with that version's interpreter):
  * select a deterministic set of stdlib .py modules
  * compile each to tests/corpus/<X.Y.Z>/<module>.pyc
  * copy the source to tests/corpus/<X.Y.Z>/<module>.py

Usage (via build_corpus.sh or directly):
  <interp> tools/build_corpus.py --stdlib DIR --out DIR [--limit N]
"""
import os
import py_compile
import sys

# modules that are known to be problematic to compile standalone or are
# platform/generated noise
SKIP_NAMES = set(["this", "antigravity", "__phello__", "_pydecimal"])
SKIP_DIRS = set([
    "test", "tests", "site-packages", "lib2to3", "idle_test", "venv",
    "distutils", "lib-tk", "encodings", "email", "importlib",
    "json", "logging", "unittest", "xml", "http", "asyncio", "collections",
    "concurrent", "ctypes", "curses", "dbm", "sqlite3", "wsgiref",
    "multiprocessing", "tkinter", "ensurepip", "libpasteurize", "future",
    "idlelib", "pydoc_data", "__phello__", "msilib",
])


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
    # plain argv parsing: Python 2.6 has no argparse
    argv = sys.argv[1:]
    stdlib = argv[argv.index("--stdlib") + 1]
    outdir = argv[argv.index("--out") + 1]
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 40

    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    picked = 0
    failed = []
    for src in candidates(stdlib):
        if picked >= limit:
            break
        base = os.path.basename(src)[:-3]
        pyc = os.path.join(outdir, base + ".pyc")
        py = os.path.join(outdir, base + ".py")
        with open(src, "rb") as f:
            data = f.read()
        # sanitize local paths before the fixture is committed:
        # _sysconfigdata embeds the build prefix in string constants, and
        # every pyc would otherwise carry the absolute source path as its
        # co_filename (dfile below replaces it with a bare module name)
        home = os.path.expanduser("~")
        try:
            hb = home.encode("utf-8")
        except Exception:
            hb = home
        if home and home != "~":
            data = data.replace(hb, b"~")
        with open(py, "wb") as f:
            f.write(data)
        try:
            py_compile.compile(py, cfile=pyc, dfile=base + ".py",
                               doraise=True)
        except Exception:
            failed.append((base, str(sys.exc_info()[1])[:120]))
            continue
        picked += 1
    ver = sys.version.split()[0]
    print("python %s: picked %d modules into %s" % (ver, picked, outdir))
    for b, e in failed:
        print("  compile-skip %s: %s" % (b, e))


if __name__ == "__main__":
    main()

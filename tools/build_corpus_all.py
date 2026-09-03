#!/usr/bin/env python3
"""Build corpora for every discovered interpreter: one directory per exact
version X.Y.Z under tests/corpus/, filled with stdlib modules compiled by
that interpreter itself.

Usage: python3 tools/build_corpus_all.py [--limit N] [--version X.Y]
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_corpus import find_interpreters, CORPUS, ROOT  # noqa: E402

BUILD = os.path.join(ROOT, "tools", "build_corpus.py")


def stdlib_of(interp):
    p = subprocess.run(
        [interp, "-c", "import sysconfig; print(sysconfig.get_paths()['stdlib'])"],
        capture_output=True, text=True, timeout=30,
    )
    if p.returncode != 0:
        return None
    return p.stdout.strip().splitlines()[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--version", help="only build for this X.Y prefix")
    ap.add_argument("--force", action="store_true", help="rebuild even if dir exists")
    args = ap.parse_args()

    interps = find_interpreters()
    versions = sorted(interps.keys(), key=lambda v: tuple(int(x) for x in v.split(".")))
    for v in versions:
        if args.version and not v.startswith(args.version):
            continue
        interp = interps[v]
        outdir = os.path.join(CORPUS, v)
        if os.path.isdir(outdir) and not args.force:
            import glob as _g
            if _g.glob(os.path.join(outdir, "*.pyc")):
                print("skip %s (exists)" % v)
                continue
        stdlib = stdlib_of(interp)
        if not stdlib or not os.path.isdir(stdlib):
            print("skip %s: no stdlib dir (%s)" % (v, stdlib))
            continue
        os.makedirs(outdir, exist_ok=True)
        print("=== building %s with %s (stdlib %s)" % (v, interp, stdlib))
        subprocess.run(
            [interp, BUILD, "--stdlib", stdlib, "--out", outdir,
             "--limit", str(args.limit)],
            check=False,
        )


if __name__ == "__main__":
    main()

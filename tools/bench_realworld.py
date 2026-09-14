#!/usr/bin/env python3
"""Real-world corpus benchmark for pycdc.

Decompiles the corpus created by tools/fetch_realworld.sh (seven large
projects at their latest release tags, every .py compiled to .pyc with
`compileall -b`) and reports, per project:

  * files, source bytes
  * serial and parallel batch wall time + peak RSS (one pycdc process
    per project, --quiet)
  * recompilability: the decompiled .py must parse under the same
    interpreter that produced the corpus (our acceptance criterion)

Usage:
  python3 tools/bench_realworld.py [--jobs N] [--out benchmarks/realworld.json]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CORPUS = os.path.join(ROOT, "tests/realworld")
PYCDC = os.environ.get("BENCH_PYCDC", os.path.join(ROOT, "target/release/pycdc"))
INTERP = os.environ.get(
    "BENCH_INTERP",
    os.path.expanduser(
        "~/.local/share/uv/python/cpython-3.12.14-macos-aarch64-none/bin/python3.12"
    ),
)

RSS_RE = __import__("re").compile(r"(\d+)\s+maximum resident set size")


def sanitize_paths(obj):
    """Home dir -> ~, repo-internal paths -> repo-relative (the committed
    realworld.json must not leak local paths)."""
    home = os.path.expanduser("~")
    if isinstance(obj, str):
        # repo-relative first (ROOT starts with the home dir, so the
        # order matters), then the home dir -> ~
        root = ROOT + os.sep
        out = obj[len(root):] if obj.startswith(root) else obj
        return out.replace(home, "~")
    if isinstance(obj, dict):
        return {k: sanitize_paths(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_paths(v) for v in obj]
    return obj

def timed(cmd):
    """/usr/bin/time -l wrapped run -> (rc, wall_seconds, peak_rss_mb, stderr)"""
    t0 = time.monotonic()
    p = subprocess.run(["/usr/bin/time", "-l"] + cmd, capture_output=True)
    wall = time.monotonic() - t0
    m = RSS_RE.search(p.stderr.decode("utf-8", "replace"))
    return p.returncode, wall, (int(m.group(1)) / 1048576 if m else 0.0), p.stderr


def parses(path):
    try:
        src = open(path, "rb").read()
        r = subprocess.run(
            [INTERP, "-c", "import ast,sys; ast.parse(sys.stdin.buffer.read())"],
            input=src,
            capture_output=True,
        )
        return r.returncode == 0
    except Exception:
        return False


def project_stats(corpus, name, out_root):
    src_dir = os.path.join(corpus, name)
    pycs = [
        os.path.join(dp, f)
        for dp, _, fs in os.walk(src_dir)
        for f in fs
        if f.endswith(".pyc")
    ]
    if not pycs:
        return None
    src_bytes = sum(
        os.path.getsize(p[:-1]) for p in pycs if os.path.exists(p[:-1])
    )
    row = {"project": name, "files": len(pycs), "source_bytes": src_bytes}

    for mode, jobs in (("serial", "1"), ("parallel", None)):
        out = os.path.join(out_root, f"{name}-{mode}")
        cmd = [PYCDC, "-q"]
        if jobs:
            cmd += ["-j", jobs]
        cmd += [src_dir, "-o", out]
        rc, wall, rss, err = timed(cmd)
        row[f"{mode}_wall_s"] = round(wall, 2)
        row[f"{mode}_rss_mb"] = round(rss, 1)
        if rc != 0:
            row[f"{mode}_rc"] = rc
            row[f"{mode}_err"] = err.decode("utf-8", "replace")[:200]
        if mode == "parallel":
            # recompilability of the parallel output
            outs = [
                os.path.join(dp, f)
                for dp, _, fs in os.walk(out)
                for f in fs
                if f.endswith(".py")
            ]
            with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
                ok = sum(ex.map(parses, outs, chunksize=16))
            row["decompiled"] = len(outs)
            row["recompiles"] = ok
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=DEFAULT_CORPUS)
    ap.add_argument("--out", default=os.path.join(ROOT, "benchmarks/realworld.json"))
    ap.add_argument("--tmp", default=None, help="where the .py outputs land")
    a = ap.parse_args()

    out_root = a.tmp or os.path.join("/tmp", f"pycdc-realworld-{os.getpid()}")
    os.makedirs(out_root, exist_ok=True)

    projects = sorted(
        d
        for d in os.listdir(a.corpus)
        if os.path.isdir(os.path.join(a.corpus, d))
    )
    rows = []
    for name in projects:
        r = project_stats(a.corpus, name, out_root)
        if r:
            rows.append(r)
            print(
                f"{name:12s} files={r['files']:5d}  serial={r['serial_wall_s']:6.2f}s"
                f" (rss {r['serial_rss_mb']:5.1f}MB)  parallel={r['parallel_wall_s']:6.2f}s"
                f" (rss {r['parallel_rss_mb']:5.1f}MB)  recompiles="
                f"{r.get('recompiles', 0)}/{r.get('decompiled', 0)}",
                flush=True,
            )

    total = {
        "project": "TOTAL",
        "files": sum(r["files"] for r in rows),
        "source_bytes": sum(r["source_bytes"] for r in rows),
        "serial_wall_s": round(sum(r["serial_wall_s"] for r in rows), 2),
        "parallel_wall_s": round(sum(r["parallel_wall_s"] for r in rows), 2),
        "serial_rss_mb": max(r["serial_rss_mb"] for r in rows),
        "parallel_rss_mb": max(r["parallel_rss_mb"] for r in rows),
        "decompiled": sum(r.get("decompiled", 0) for r in rows),
        "recompiles": sum(r.get("recompiles", 0) for r in rows),
    }
    print(
        f"TOTAL        files={total['files']:5d}  serial={total['serial_wall_s']:.2f}s"
        f"  parallel={total['parallel_wall_s']:.2f}s  peak RSS="
        f"{total['parallel_rss_mb']:.1f}MB  recompiles={total['recompiles']}/{total['decompiled']}"
    )

    doc = {
        "corpus": a.corpus,
        "pycdc": PYCDC,
        "interp": INTERP,
        "host": subprocess.run(["uname", "-mrs"], capture_output=True)
        .stdout.decode()
        .strip(),
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "one pycdc process per project (batch directory mode); "
        "serial = -j 1, parallel = default worker count; recompiles = "
        "decompiled output parses under the corpus interpreter",
        "projects": rows,
        "total": total,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(sanitize_paths(doc), f, indent=1)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())
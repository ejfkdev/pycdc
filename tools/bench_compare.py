#!/usr/bin/env python3
"""Cross-tool pyc decompiler benchmark.

Measures, for every .pyc in a corpus built from a real stdlib tree
(compileall -b, so the original .py sits next to each .pyc):

  * wall time per file (serial, one process per file — the way the CLIs
    are actually used), via /usr/bin/time
  * peak RSS per invocation (max over the corpus)
  * success rate (exit 0 + non-empty stdout)
  * compilability of the decompiled output under the corpus interpreter
  * semantic equivalence: normalized AST of the output vs the original
    source (ast.dump with all docstring statements stripped)

The original source is available because the corpus is compiled from
it, which is what makes the semantic check possible at all.

Usage:
  python3 tools/bench_compare.py --corpus /tmp/bench312/src \
      --interp <python-that-produced-the-pycs> \
      --tools pycdc-rs,pycdc-cpp --out benchmarks/bench-312.json

Tool binaries are resolved from BENCH_<NAME> environment variables or
the defaults below (edit for your machine).
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_TOOLS = {
    "pycdc-rs": os.environ.get(
        "BENCH_PYDC_RS", os.path.join(ROOT, "target/release/pycdc")),
    "pycdc-cpp": os.environ.get(
        "BENCH_PYDC_CPP",
        os.path.expanduser("~/Documents/github/python-decompile/pycdc/build/pycdc")),
    "uncompyle6": os.environ.get("BENCH_UNCOMPYLE6", "/tmp/venv38/bin/uncompyle6"),
    "decompyle3": os.environ.get("BENCH_DECOMPYLE3", "/tmp/venv38/bin/decompyle3"),
}

TIME_RE = re.compile(r"^\s*([\d.]+)\s+real", re.M)
RSS_RE = re.compile(r"(\d+)\s+maximum resident set size", re.M)


class DocStrip(ast.NodeTransformer):
    """Drop docstring expression statements so decompiler comment
    artifacts or missing docstrings don't break the comparison."""

    def _strip(self, node):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            v = body[0].value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                node.body = body[1:] or [ast.Pass()]
        return node

    def visit_Module(self, node):
        self.generic_visit(node)
        return self._strip(node)

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        return self._strip(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        return self._strip(node)


def norm_ast(src):
    tree = ast.parse(src)
    tree = DocStrip().visit(tree)
    ast.fix_missing_locations(tree)
    return ast.dump(tree, annotate_fields=False)


def run_timed(cmd, infile):
    """-> (rc, stdout, wall_seconds, peak_rss_bytes)"""
    # wall time from our own monotonic clock: /usr/bin/time only
    # resolves to 10 ms, which reads 0.00 for the fast native tools
    t0 = time.monotonic()
    p = subprocess.run(
        ["/usr/bin/time", "-l"] + cmd + [infile],
        capture_output=True,
    )
    wall = time.monotonic() - t0
    r = RSS_RE.search(p.stderr.decode("utf-8", "replace"))
    return (
        p.returncode,
        p.stdout,
        wall,
        int(r.group(1)) if r else 0,
    )


def bench_tool(name, cmd, files, interp, limit):
    ok = compiles = semantic = 0
    wall_sum = 0.0
    peak_rss = 0
    rss_samples = []
    errs = {}
    for path in files[:limit] if limit else files:
        src_py = path[:-1]  # .pyc -> .py
        rc, out, wall, rss = run_timed(cmd, path)
        wall_sum += wall
        peak_rss = max(peak_rss, rss)
        rss_samples.append(rss)
        text = out.decode("utf-8", "replace")
        if rc != 0 or not text.strip():
            errs[os.path.basename(path)] = f"rc={rc}"
            continue
        ok += 1
        # semantic validation against the original source
        try:
            with open(src_py, "rb") as f:
                orig = f.read().decode("utf-8", "replace")
            c = subprocess.run(
                [interp, "-c",
                 "import ast,sys; ast.parse(open(sys.argv[1],'rb').read())",
                 "/dev/stdin"],
                input=text.encode(),
                capture_output=True,
            )
            if c.returncode != 0:
                continue
            compiles += 1
            if norm_ast(text) == norm_ast(orig):
                semantic += 1
        except Exception:
            pass
    n = len(files[:limit] if limit else files)
    rss_samples.sort()
    return {
        "tool": name,
        "cmd": cmd,
        "files": n,
        "success": ok,
        "success_rate": round(ok / n, 4) if n else 0,
        "compiles": compiles,
        "semantic_exact_ast": semantic,
        "wall_total_s": round(wall_sum, 2),
        "wall_per_file_ms": round(wall_sum / n * 1000, 1) if n else 0,
        "peak_rss_mb": round(peak_rss / 1048576, 1),
        "median_rss_mb": round(
            (rss_samples[len(rss_samples) // 2] if rss_samples else 0) / 1048576, 1),
        "first_errors": dict(list(errs.items())[:5]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--interp", required=True,
                    help="interpreter that produced the corpus pycs")
    ap.add_argument("--tools", default="pycdc-rs,pycdc-cpp,uncompyle6,decompyle3")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    files = sorted(
        os.path.join(a.corpus, f)
        for f in os.listdir(a.corpus)
        if f.endswith(".pyc") and os.path.exists(os.path.join(a.corpus, f[:-1]))
    )
    print(f"corpus: {len(files)} pyc files with matching sources", flush=True)

    results = []
    for name in [t.strip() for t in a.tools.split(",") if t.strip()]:
        cmd = DEFAULT_TOOLS[name]
        if isinstance(cmd, str):
            cmd = [cmd]
        print(f"== {name}: {' '.join(cmd)}", flush=True)
        r = bench_tool(name, cmd, files, a.interp, a.limit)
        results.append(r)
        print(json.dumps(r, indent=1), flush=True)

    meta = {
        "corpus": a.corpus,
        "interp": a.interp,
        "host": subprocess.run(["uname", "-mrs"], capture_output=True)
        .stdout.decode().strip(),
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "serial per-file CLI invocations; semantic_exact_ast = "
        "decompiled output parses and its docstring-stripped AST equals "
        "the original source's",
        "results": results,
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(meta, f, indent=1)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

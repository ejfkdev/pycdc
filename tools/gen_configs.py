#!/usr/bin/env python3
"""Generate version data configs for the Rust pycdc.

Outputs (into configs/):
  magics.json              magic int -> version string   (from xdis.magics)
  opcodes/python_X_Y.json  per-version opcode metadata

Data sources:
  * xdis (reference checkout) for Python 2.0 - 3.10 (+ 3.15 dev)
  * native interpreter dumps (tools/dump_native.py, run via uv) for 3.11+

Usage:
  python3 tools/gen_configs.py [--xdis /path/to/xdis-checkout] [--native]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_XDIS = os.environ.get("XDIS_DIR", "")

XDIS_VERSIONS = [
    (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6), (2, 7),
    (3, 0), (3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (3, 6), (3, 7),
    (3, 8), (3, 9), (3, 10), (3, 15),
]
NATIVE_VERSIONS = ["3.11", "3.12", "3.13", "3.14"]


def sorted_list(v):
    return sorted(set(int(x) for x in v))


def emit(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", path)


def gen_magics(xdis_dir):
    sys.path.insert(0, xdis_dir)
    from xdis.magics import magicint2version

    table = {}
    for magic, version in magicint2version.items():
        table[str(int(magic))] = str(version)
    outdir = os.path.join(ROOT, "configs")
    os.makedirs(outdir, exist_ok=True)
    emit(os.path.join(outdir, "magics.json"), table)


def gen_from_xdis(xdis_dir):
    sys.path.insert(0, xdis_dir)
    from xdis.op_imports import get_opcode_module

    outdir = os.path.join(ROOT, "configs", "opcodes")
    os.makedirs(outdir, exist_ok=True)
    for vt in XDIS_VERSIONS:
        try:
            m = get_opcode_module(vt, "CPython")
        except Exception as e:  # pragma: no cover
            print("skip %s: %s" % (vt, e))
            continue
        data = {
            "version": "%d.%d" % vt,
            "implementation": "cpython",
            "have_argument": int(m.HAVE_ARGUMENT),
            "wordcode": vt >= (3, 6),
            "opmap": {k: int(v) for k, v in m.opmap.items()},
            "hasjrel": sorted_list(m.hasjrel),
            "hasjabs": sorted_list(m.hasjabs),
            "hasarg": sorted_list(
                getattr(m, "hasarg", [i for i in range(m.HAVE_ARGUMENT, 256)])
            ),
            "hascompare": sorted_list(m.hascompare),
            "hasconst": sorted_list(m.hasconst),
            "hasname": sorted_list(m.hasname),
            "haslocal": sorted_list(m.haslocal),
            "hasfree": sorted_list(m.hasfree),
            "nofollow": sorted_list(getattr(m, "nofollow", [])),
            "cmp_op": list(m.cmp_op),
            "cache_entries": {},
        }
        name = "python_%d_%d.json" % vt
        emit(os.path.join(outdir, name), data)


def gen_from_native(uv_versions):
    outdir = os.path.join(ROOT, "configs", "opcodes")
    os.makedirs(outdir, exist_ok=True)
    script = os.path.join(HERE, "dump_native.py")
    for ver in uv_versions:
        proc = subprocess.run(
            ["uv", "run", "--no-project", "--python", ver, "python", script],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            print("skip native %s:\n%s" % (ver, proc.stderr[-2000:]))
            continue
        raw = json.loads(proc.stdout)
        vt = tuple(int(x) for x in raw["version"][:2])
        data = {
            "version": "%d.%d" % vt,
            "implementation": "cpython",
            "have_argument": 90,
            "wordcode": True,
            "opmap": {k: int(v) for k, v in raw["opmap"].items()},
            "hasjrel": sorted_list(raw["hasjrel"]),
            "hasjabs": sorted_list(raw["hasjabs"]),
            "hasarg": sorted_list(raw["hasarg"]),
            "hascompare": sorted_list(raw["hascompare"]),
            "hasconst": sorted_list(raw["hasconst"]),
            "hasname": sorted_list(raw["hasname"]),
            "haslocal": sorted_list(raw["haslocal"]),
            "hasfree": sorted_list(raw["hasfree"]),
            "nofollow": [],
            "cmp_op": raw["cmp_op"],
            "cache_entries": {int(k): int(v) for k, v in raw["cache_entries"].items()},
        }
        name = "python_%d_%d.json" % vt
        emit(os.path.join(outdir, name), data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xdis", default=DEFAULT_XDIS,
                    help="path to a python-xdis checkout (or $XDIS_DIR)")
    ap.add_argument("--native", action="store_true", default=True,
                    help="also generate 3.11+ configs from live interpreters via uv")
    ap.add_argument("--no-native", dest="native", action="store_false")
    args = ap.parse_args()

    if not args.xdis or not os.path.isdir(args.xdis):
        ap.error("xdis generation needs --xdis /path/to/xdis-checkout "
                 "or $XDIS_DIR; use --native for 3.11+ only")
    gen_magics(args.xdis)
    gen_from_xdis(args.xdis)
    if args.native:
        gen_from_native(NATIVE_VERSIONS)


if __name__ == "__main__":
    main()

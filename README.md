# pycdc-rs

English | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-2.0--3.15-yellow.svg)](#)
[![Corpus](https://img.shields.io/badge/corpus-622%2F622%20semantic-brightgreen.svg)](#verification)
[![Behavior](https://img.shields.io/badge/behavior-754%2F754-brightgreen.svg)](#verification)
[![Built with ZCode](https://img.shields.io/badge/Built%20with%20ZCode-000000.svg?style=flat&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMTgiIGhlaWdodD0iMTAwIiB2aWV3Qm94PSIwIDAgMjU2IDIxOCI+PHBhdGggZmlsbD0iI2ZmZmZmZiIgZD0iTTEzNC40IDAuMTMwMTUyTDExNi40OCAyNS42MDIyQzExMy42NjUgMjkuNTY5OSAxMDkuMDU0IDMyLjAwMTkgMTA0LjA2NCAzMi4wMDE5SDYuMzk5OVYwQzYuMzk5OSAwLjEzMDE0OSAxMzQuNCAwLjEzMDE1MiAxMzQuNCAwLjEzMDE1MloiLz48cGF0aCBmaWxsPSIjZmZmZmZmIiBkPSJNMjU2IDAuMTMwMTI3TDEwMi40MDEgMjE3LjczMkgwTDE1My41OTkgMC4xMzAxMjdIMjU2WiIvPjxwYXRoIGZpbGw9IiNmZmZmZmYiIGQ9Ik0xMjEuNjAxIDIxNy43MzJMMTM5LjY1IDE5Mi4xMzRDMTQyLjQ2NSAxODguMTY2IDE0Ny4wNzYgMTg1LjczNCAxNTIuMDY3IDE4NS43MzRIMjQ5LjYwNFYyMTcuNzM2SDEyMS42MDFWMjE3LjczMloiLz48L3N2Zz4=)](https://zcode.z.ai/)

Decompile and disassemble Python bytecode (`.pyc`) from **Python 2.0 through 3.15** back into readable source — written in Rust, no Python required at runtime, with an optional in-process pass through the [`cure`](https://github.com/ejfkdev/cure) simplifier.

```sh
pycdc program.pyc          # decompile to stdout
pycdc dis program.pyc      # disassemble (exception tables, line numbers, nested code)
```

## Highlights

- **100% semantic equivalence** on a 622-module real-stdlib corpus across 14 interpreters (2.6–3.15); 80.2% are signature-exact
- **Behavior matrix 754/754 = 100%**: every case passes on 2.6–3.15, including the new 3.15 bytecode encodings
- Modern syntax: PEP 695/696 type parameters, PEP 750 t-strings, PEP 649 deferred annotations, match/case, walrus, async, f-strings
- Optional `--cure`: folds the output through the `cure` simplifier/formatter in-process — no external binary, no Python — turning `if cond: return a` / `return b` into `return a if cond else b` and trimming ~10% of the lines
- Version differences are pure data: one embedded opcode table per release, overridable via `--opcodes`
- Graceful degradation: unrecognized constructs become comment placeholders — never a crash

## Install

**Homebrew (macOS & Linux):**

```sh
brew install ejfkdev/tap/pycdc
```

**Scoop (Windows):**

```powershell
scoop install https://raw.githubusercontent.com/ejfkdev/scoop-bucket/main/bucket/pycdc.json
```

The manifest selects x64 or arm64 automatically and installs both `pycdc`
and `pycdas`. To install by name instead, add the bucket once:

```powershell
scoop bucket add ejfkdev https://github.com/ejfkdev/scoop-bucket
scoop install pycdc
```

**cargo, from [crates.io](https://crates.io/crates/pycdc):**

```sh
cargo install pycdc
```

**Prebuilt binaries:** raw executables (no archive wrapper) on the
[Releases](https://github.com/ejfkdev/pycdc/releases) page —
Linux / Windows x86_64 + arm64, macOS arm64 + x86_64; Linux and Windows
builds are UPX-compressed, macOS ships uncompressed.

**From source:**

```sh
cargo build --release      # -> target/release/pycdc + pycdas
cargo install --path .     # or install both binaries from a checkout
```

Every method provides both `pycdc` and `pycdas`.

## Usage

```sh
# single file -> stdout, a file, or a directory
pycdc program.pyc > program.py
pycdc program.pyc -o program.py
pycdc program.pyc -o ./outdir/

# stdin (pipelines): - reads the pyc from stdin
cat program.pyc | pycdc -

# batch: mirror a directory tree (parallel by default, -j N to control,
# -q suppresses the per-file src -> dst lines)
pycdc ./pyc-corpus -o ./src-out
pycdc ./pyc-corpus               # -> ./pyc-corpus-decompiled/
pycdc a.pyc b.pyc                # -> a.py, b.py next to the inputs
pycdc ./pyc-corpus -o ./src-out -q -j 8

# raw marshal (no pyc header) with an explicit version
pycdc -v 3.8 payload.marshal

# disassembly — same CLI surface (files, dirs, stdin, -o/-j/-q)
pycdc dis program.pyc
pycdc dis ./pyc-corpus -o ./dis-out # -> mirrored .dis files
# the standalone `pycdas` binary is kept as a compatibility alias
# with byte-identical output
pycdas program.pyc

# optional simplification/formatting pass (cure, linked in-process)
pycdc --cure program.pyc
```

`--cure` is opt-in and purely cosmetic: pycdc's output is already
verified, so the default stays untouched. With it, conditionals collapse
into ternaries, quotes normalize to single quotes, and formatting is
reflowed:

```python
# default                                  # --cure
def classify(v):                           def classify(v):
    if v is True:                              return 1 if v is True else 0
        return 1
    return 0
```

If the input cannot be parsed by `cure`, if it contains
compiler-introspection metadata (`__annotate__`, `co_freevars`,
`__conditional_annotations__`, `__classdict__`) where simplifying could
change runtime behaviour, or if it deletes a local name (`del v`, which
cure 0.4 mis-propagates — fixed upstream, awaiting a release), the file
is emitted unchanged and a note with the reason goes to stderr. The
behavior matrix passes 754/754 both with and without `--cure`, and all
622 corpus modules still compile under their own interpreter with it.
Because the pass deliberately rewrites statement shapes (if/else →
ternary), the corpus's bytecode-signature metric is not meaningful for
`--cure` output; judge it by the behavior matrix.

`pycdc --help`, `pycdc dis --help` and `pycdas --help` document every
flag. Exit codes: `0` success, `1` a file failed to process, `2` usage
error.

## Performance

Apple Silicon, 526 real `.pyc` files (~9.5 MB, Python 2.6–3.14 stdlib):

| Scenario | Time | Peak RSS |
|---|---|---|
| Batch, parallel (default) | **≈0.05 s** | ≈25 MB |
| Batch, serial (`-j 1`) | ≈0.34 s | ≈13 MB |
| Largest single file (74 KB, incl. startup) | ≈5.5 ms | ≈4.4 MB |
| Process startup | ≈2 ms | — |

### Real-world corpus (seven large projects, latest release tags)

`tools/fetch_realworld.sh` sparse-checks-out one directory from each of
seven projects **at its latest release tag**, compiles every `.py` to
`.pyc` (`compileall -b`), and lands the tree in `tests/realworld/`
(git-ignored — the script is the way to recreate it):

| Project (tag) | modules | serial `-j 1` | parallel (default) | recompiles | AST-identical¹ |
|---|---|---|---|---|---|
| yt-dlp (2026.08.19) | 1045 | 0.52 s | 0.08 s | **1045/1045** | 502/1045 |
| matplotlib (v3.11.2) | 253 | 0.28 s | 0.06 s | **253/253** | 60/253 |
| pandas (v3.0.5) | 1420 | 0.93 s | 0.13 s | **1420/1420** | 586/1420 |
| django (6.1.1) | 907 | 0.35 s | 0.10 s | **907/907** | 470/907 |
| sympy (1.14.0) | 1532 | 3.03 s | 1.51 s | **1532/1532** | 482/1532 |
| scikit-learn (1.9.1) | 671 | 0.55 s | 0.07 s | **671/671** | 216/671 |
| ansible (v2.21.4) | 583 | 0.25 s | 0.04 s | **583/583** | 186/583 |
| **total** | **6411** | **5.91 s** | **1.99 s** | **6411/6411 (100 %)** | 2502/6411 |

¹ strict: docstring-stripped AST equal to the original source —
equivalent normalizations (an if/else instead of a ternary, a redundant
`*()`/`**{}` around an unpack, reordered keyword arguments) count as
differences, so treat it as a shape-fidelity floor rather than an error
rate. The parse/recompile column is the acceptance bar.

One pycdc process per project: ~0.92 ms per module serial, peak RSS
≈82 MB for the whole 6.4 k-module batch. **All 6411 modules recompile**;
the last family (a dict comprehension nested inside a generator
expression's element, call arguments included) was closed by the
community PR batch. Raw data: [`benchmarks/realworld.json`](benchmarks/realworld.json),
harness: [`tools/bench_realworld.py`](tools/bench_realworld.py).


## Verification

Three independent harnesses, all runnable locally (need pyenv/uv interpreters 2.6–3.15):

| Harness | What it proves | Current |
|---|---|---|
| [`tools/verify_corpus.py`](tools/verify_corpus.py) | 622 stdlib modules: decompile → recompile with the *same* interpreter → compare bytecode signatures, fall back to normalized-AST diff | **622/622 semantic** (499 signature-exact, 0 syntax errors, 0 placeholders) |
| [`tools/run_behavior.py`](tools/run_behavior.py) | 96 behavior cases × 14 interpreters: run original vs decompiled, compare stdout + exit code | **754/754 = 100%** (2.6–3.15) |
| [`tests/roundtrip.py`](tests/roundtrip.py) | fixture matrix: compile → decompile → recompile → strict bytecode compare | 49/54 strict (exceptions fixtures differ structurally, semantically equivalent) |

The 3.15 result reflects CPython 3.15.0/3.15.1, whose inline-comprehension,
call and import encodings changed; its opcode table is generated from the
live interpreter. All behavior cases pass and pandas+scikit-learn recompile
2091/2091 under 3.15; the remaining `with`-body-return edge is documented
in [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

Per-version results live in `tests/corpus/<version>/report.json`.
A cross-tool comparison (speed, memory, output quality vs
Decompyle++, uncompyle6, decompyle3) lives in
[benchmarks/](benchmarks/README.md). Beyond
these harnesses, releases are gated by ad-hoc quality batteries: a 25-shape
syntax-family fuzz matrix (×10 interpreters), a hostile-input robustness
suite (truncated/corrupted/OOM-bomb pycs — zero crashes), and a
third-party venv smoke (six/packaging/click/attrs/pluggy). See
[docs/LIMITATIONS.md](docs/LIMITATIONS.md) for the detailed known-gap list
and the third-party backlog.

## Project layout

```
src/    loader → marshal → bytecode → decompiler → codegen  (version.rs/opcode.rs hold the per-version data; simplify.rs wraps cure)
configs/ embedded opcode + magic tables (regenerate: tools/gen_configs.py)
tools/   config generation, corpus building, verification harnesses
tests/   Rust tests, fixtures, 622-module corpus, 96 behavior cases
```

## Acknowledgements

Design informed by [Decompyle++ (pycdc)](https://github.com/zrax/pycdc), [uncompyle6/decompyle3](https://github.com/rocky/python-decompyle3) and [xdis](https://github.com/rocky/python-xdis). The optional `--cure` post-processing is provided by [cure](https://github.com/ejfkdev/cure).

## License

[MIT](LICENSE)

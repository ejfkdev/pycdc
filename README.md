# pycdc-rs

English | [简体中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-2.0--3.15-yellow.svg)](#)
[![Corpus](https://img.shields.io/badge/corpus-520%2F520%20semantic-brightgreen.svg)](#verification)
[![Behavior](https://img.shields.io/badge/behavior-490%2F490-brightgreen.svg)](#verification)

Decompile and disassemble Python bytecode (`.pyc`) from **Python 2.0 through 3.15 (dev)** back into readable source — written in Rust, three dependencies, no Python required at runtime.

```sh
pycdc program.pyc          # decompile to stdout
pycdas program.pyc         # disassemble (exception tables, line numbers, nested code)
```

## Highlights

- **100% semantic equivalence** on a 520-module real-stdlib corpus across 13 interpreters (2.6–3.14); 76.5% are byte-exact at the bytecode-signature level
- **Behavior matrix 490/490**: decompiled code runs identically to the original under the same interpreter
- Modern syntax: PEP 695/696 type parameters, PEP 750 t-strings, PEP 649 deferred annotations, match/case, walrus, async, f-strings
- Version differences are pure data: one embedded opcode table per release, overridable via `--opcodes`
- Graceful degradation: unrecognized constructs become comment placeholders — never a crash

## Build

```sh
cargo build --release      # -> target/release/pycdc + pycdas
cargo install --path .     # optional: install both binaries
```

## Usage

```sh
# single file -> stdout, a file, or a directory
pycdc program.pyc > program.py
pycdc program.pyc -o program.py
pycdc program.pyc -o ./outdir/

# batch: mirror a directory tree (parallel by default, -j N to control)
pycdc ./pyc-corpus -o ./src-out
pycdc ./pyc-corpus               # -> ./pyc-corpus-decompiled/
pycdc a.pyc b.pyc                # -> a.py, b.py next to the inputs

# raw marshal (no pyc header) with an explicit version
pycdc -v 3.8 payload.marshal

# disassembly
pycdas program.pyc
```

`pycdc --help` documents every flag, including `-j/--jobs` and `--opcodes`.

## Performance

Apple Silicon, 526 real `.pyc` files (~9.5 MB, Python 2.6–3.14 stdlib):

| Scenario | Time | Peak RSS |
|---|---|---|
| Batch, parallel (default) | **≈0.05 s** | ≈25 MB |
| Batch, serial (`-j 1`) | ≈0.34 s | ≈13 MB |
| Largest single file (74 KB, incl. startup) | ≈5.5 ms | ≈4.4 MB |
| Process startup | ≈2 ms | — |

## Verification

Three independent harnesses, all runnable locally (need pyenv/uv interpreters 2.6–3.14):

| Harness | What it proves | Current |
|---|---|---|
| [`tools/verify_corpus.py`](tools/verify_corpus.py) | 520 stdlib modules: decompile → recompile with the *same* interpreter → compare bytecode signatures, fall back to normalized-AST diff | **520/520 semantic** (398 signature-exact, 0 syntax errors, 0 placeholders) |
| [`tools/run_behavior.py`](tools/run_behavior.py) | 48 behavior cases × 13 interpreters: run original vs decompiled, compare stdout + exit code | **490/490 = 100%** |
| [`tests/roundtrip.py`](tests/roundtrip.py) | fixture matrix: compile → decompile → recompile → strict bytecode compare | 49/54 strict (exceptions fixtures differ structurally, semantically equivalent) |

Per-version results live in `tests/corpus/<version>/report.json`. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for the detailed known-gap list.

## Project layout

```
src/    loader → marshal → bytecode → decompiler → codegen  (version.rs/opcode.rs hold the per-version data)
configs/ embedded opcode + magic tables (regenerate: tools/gen_configs.py)
tools/   config generation, corpus building, verification harnesses
tests/   Rust tests, fixtures, 520-module corpus, 48 behavior cases
```

## Acknowledgements

Design informed by [Decompyle++ (pycdc)](https://github.com/zrax/pycdc), [uncompyle6/decompyle3](https://github.com/rocky/python-decompyle3) and [xdis](https://github.com/rocky/python-xdis).

## License

[MIT](LICENSE)

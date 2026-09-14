# Changelog

All notable changes to pycdc-rs. The full verification baseline for every
release: 520-module stdlib corpus (semantic 520/520) + behavior matrix +
cargo tests, on 13 interpreters (2.6–3.14).

## v0.5.0 — 2026-09-14

### CLI
- stdin input: `-` reads a pyc (or with `-v`, raw marshal) from stdin
- `pycdc -q/--quiet`: suppress per-file batch lines
- `pycdas` reaches full parity with `pycdc`: directories (mirrored
  `.dis` output), `-o`, `-j` parallel workers, `-q`, stdin,
  `-V/--version`, BrokenPipe-safe stdout
- exit-code convention: `0` success, `1` file processing failure,
  `2` usage error
- help screen redesign (both binaries): header now carries the program
  name + version, a description, the repository URL
  (https://github.com/ejfkdev/pycdc) and an `Examples` section; running
  with no arguments prints help (exit 0), and missing the required input
  argument defaults to the help screen (exit 2)

### Packaging / repo
- GitHub Actions CI (build + test + smoke on Linux/macOS/Windows,
  informational clippy)
- tag-triggered release job: pushes of `v*` tags build `pycdc`/`pycdas`
  for x86_64/aarch64 Linux, x86_64 Windows and x86_64/arm64 macOS;
  Linux/Windows binaries are UPX-compressed (macOS is not UPX-supported
  and ships uncompressed); the crate version is rewritten from the tag
  before building and the binaries' printed version is asserted to equal
  the tag, then artifacts are uploaded to the GitHub Release
- `repository`/`homepage` metadata point at the GitHub project
- crate package slimmed from ~14 MB to ~0.6 MB: the verification corpus,
  behavior matrix, python tooling, docs and `.github/` are excluded from
  the published `.crate` (they stay in the git repo); the cli test
  fixture moved to `tests/pyc/base64.3.8.pyc` so `cargo package`
  verification is self-contained
- `rust-version = "1.70"` (MSRV), CHANGELOG, sanitized `report.json`
  (no local home paths)

## v0.4.1 — 2026-09-14

Quality-testing batch driven by three new batteries: a 25-shape syntax
family fuzz matrix (×10 interpreters), a hostile-input robustness suite
(zero crashes), and a 67-module third-party venv smoke
(six/packaging/click/attrs/pluggy).

### Fixed
- comprehension-element ternaries lost their else arm on every version
- negated genexpr filters (`if not C`) on 3.12+ and py2.6
- `assert` messages lost on 3.11–3.14 (incl. f-string-folded messages)
- `try/except/finally` with a body-tail return collapsed on 3.8–3.10
- in-handler `return <expr>` inside loops split apart on 3.9–3.14
- `import a.b as c` rendered as a from-import (runtime ImportError) —
  all three bytecode eras (IMPORT_FROM form, SWAP/ROT_TWO walk,
  LOAD_ATTR walk)
- 3.12/3.13 stacked class decorators produced a syntax error
- py2 nested inline comprehensions flattened; lambda elements in 3.12+
  inline comprehensions

### Comparator (tools/ast_compare.py)
- PEP 563 string annotations parse back to expressions
- `...` ≡ `pass`, constant List ≡ Tuple iteration, no-op
  `try/finally: pass` unwrapping

## v0.4.0 — 2026-09-14

- Relicensed GPL-3.0-or-later → **MIT** (author-authorized)
- READMEs rewritten lean (English primary + 简体中文); detailed
  known-gap list moved to docs/LIMITATIONS.md

## v0.3.0 — 2026-09-14

- **PEP 695/696 type parameters** (3.12+): `type X[T] = ...`,
  `def f[T](...)`, `class C[T](...)` incl. bounds, constraints,
  `*Ts`/`**P`, defaults
- **PEP 649 module/class-scope annotations** (3.14): `__annotate__` /
  `__conditional_annotations__` machinery restored to real annotation
  statements; runtime `get_annotations` VALUE/FORWARDREF exact
- try/finally family: empty `finally: pass` chains render as real
  structure; `finally: return X` swallow shapes fixed on both eras
- the 2.7–3.9 elif-nested-if gap re-verified as fixed (case demoted to
  all versions)
- behavior matrix grown to 48 cases / 490 runs

## v0.2.0 — 2026-09-14

- Performance: ~2.5× faster serial decompile, ~13× parallel batch
  (new `-j/--jobs`), −24% single-file RSS — profile-guided (cached
  debug-flag lookups, bitset DFS visitation, FxHash offset maps, lazy
  per-version opcode tables, fat LTO)
- zero compiler warnings; GPL LICENSE file; refreshed corpus reports
  (semantic 520/520 first reached in this cycle)

## v0.1.0

- Initial release: Python 2.0–3.15 (dev) pyc decompiler/disassembler,
  data-driven per-version opcode tables, 520-module corpus verification
  pipeline, CLI with batch directory mirroring

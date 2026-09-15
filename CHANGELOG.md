# Changelog

All notable changes to pycdc-rs. The full verification baseline for every
release: 520-module stdlib corpus (semantic 520/520) + behavior matrix +
cargo tests, on 13 interpreters (2.6–3.14).

## Unreleased

### Fixed
- value-position and-chains in a ternary: `try_dup_tail_ternary` now
  absorbs leading same-target cond jumps into the condition, so
  `lambda x: d[np.nan if isinstance(x, float) and np.isnan(x) else x]`
  (pandas core/algorithms) renders verbatim instead of leaving the first
  link as an `if` (which produced a marked-incomplete lambda). The
  duplicated arm tails still hoist through the existing single-slot
  merge, so `d[a if c and e else b]` keeps the shared lookup.

### Benchmarks
- real-world corpus: 6408/6411 modules recompile (99.95%); pandas is at
  1419/1420 with only the nested-comprehension family left (sklearn ×2,
  pandas to_dict)


### Fixed
- genexp element calls lost their callable when the call carried `**`, and
  dropped keyword names for `KW_NAMES`-annotated calls: the comprehension
  walker now merges `DICT_MERGE`/`DICT_UPDATE` operands and records
  `KW_NAMES`, so `(f(**d) for x in xs)` renders `f(..., **{**d})` instead
  of `{}(*{}, **d)` and `(f(x, y=1) for x in xs)` keeps `y=1` (both were
  *silently wrong* before — they parsed fine)

### Benchmarks
- the real-world harness also reports strict AST equality against the
  original sources (2488/6411 — a shape-fidelity floor: equivalent
  normalizations count as differences), so silently-wrong output cannot
  hide behind a green parse count


### Fixed
- chained comparisons lost their middle operand on the negated path
  (`assert x is sx is False` -> `x is sx and ??? is False`, `f'{...}'`
  family of asserts in sympy/pandas/matplotlib): the or-chain operand
  scan now simulates its region from the live stack, and the acceptance
  rule is seed-relative so *consecutive* chained statements (sympy
  test_boolalg) keep the operand
- lambda bodies: an if/else over two returns folds back into a ternary
  (`lambda x: d[np.nan if ... and ... else x]`), and a tuple body gets
  its parentheses (`lambda: (*gen, ...)` was invalid)
- f-string interpolations: a space separates the brace when the
  expression starts or ends with `{`/`}` (`f'{ {1: 2}[k] }'`); the guard
  is skipped when a `!conv`/`:spec` follows so `f'{name:>{w}}'` keeps
  its format spec intact
- `slice(...)` calls with a starred argument are no longer rewritten into
  a slice display (`obj[*argvals:]` was not valid source)

### Real-world corpus
- benchmark now 6407/6411 modules recompile (99.94%, was 99.7%):
  matplotlib, sympy, yt-dlp, django and ansible are at 100%


### Fixed
- dict displays rendered `**` entries without parentheses
  (`{**a or b}`, `{**x if c else y}` are syntax errors) — django
  contrib/gis/measure and matplotlib figure.py
- `CALL_FUNCTION_EX` kwargs dicts with a non-constant or non-identifier
  key were split into named keywords, producing a positional argument
  after keywords (`f(kw=1, v)`) or `my col=v` — they now stay in the
  `**{...}` form (django, pandas)

### Real-world corpus
- `tools/fetch_realworld.sh` builds a 6411-module corpus from seven
  large projects **at their latest release tags** (yt-dlp, matplotlib,
  pandas, django, sympy, scikit-learn, ansible) into the git-ignored
  `tests/realworld/`; `tools/bench_realworld.py` measures it. Current
  numbers: 6.61 s serial / 2.14 s parallel for the whole corpus
  (~1.0 ms/module), peak RSS ≈102 MB, 6394/6411 = 99.7 % of outputs
  recompile (README "Performance" section).


Benchmark-driven fixes: decompiling the full 3.12 and 3.8 stdlib corpora
(1017 + 1251 modules) surfaced one crash and nineteen modules whose
output did not parse. After this batch both corpora recompile at 99.9%
(1003/1004 and 1228/1229; the remainder is two documented long-tail
shapes — see benchmarks/README.md), with no regressions: 520/520 corpus
and 516/516 behavior unchanged.

### Fixed
- stack overflow (crash) on module-level `try: CODESET` in locale 3.12:
  the try's tail emission could re-enter itself for the same span
  through a nested region walk; emission is now re-entrancy-guarded
- control characters (NUL in smtplib's `"\0%s\0%s"`) were written raw
  into f-string literals — they now escape as `\xNN`
- tuple defaults/annotations in signatures rendered without parens
  (`def f(a=('localhost', P))` became two parameters, logging 3.12/3.8)
- `assert cond, (a, b)` message tuples lost their parens (profile 3.12,
  statistics 3.8); same for `with (a, b):` items and `raise (a, b)`
- `return (yield from x)` lost its parens (asyncio/tasks 3.8)
- `with ctx as (a, b):` — the tuple as-target was merged into the next
  statement as a bogus assignment (xml.etree.ElementTree 3.12)
- comprehension element/value dict displays (`{v: {} for v in ORDER}`)
  were dropped by the comprehension walker's stack machine
- 3.11+ calls: an attribute callee (`str(pathlib.Path(row[0]))`)
  blindly consumed the enclosing expression as a "method receiver"
  (pip 3.12)

## v0.6.0 — 2026-09-14

### CLI
- `pycdas` is merged into `pycdc` as the `dis` subcommand (`disasm` is an
  alias): `pycdc dis [OPTIONS] <INPUT>...` produces byte-identical output
  to the standalone binary; the disasm CLI now lives in the library
  (`pycdc::cli_disasm`) and `pycdas` remains as a thin compatibility
  wrapper so existing invocations keep working
- release artifacts cover six platforms: Linux/Windows x86_64 + arm64
  (Windows arm64 cross-compiled), macOS arm64 + x86_64; Linux/Windows
  binaries UPX-compressed, macOS uncompressed; artifacts are the raw
  binaries (no zip wrappers)

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

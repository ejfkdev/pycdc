# Changelog

All notable changes to pycdc-rs. The full verification baseline for every
release: stdlib corpus (semantic 622/622) + behavior matrix + cargo tests,
on 14 interpreters (2.6–3.15).

## Unreleased

### Reconstruction fixes (PR #29, EiNSTeiN-)
- Merged 22 focused commits that recover constructs which previously
  produced incomplete or wrong output: disjunctive guards inside `for`
  loops, padded bare/calculated returns around protected regions,
  chained-comparison ternaries inside inline comprehensions, generator
  expressions with repeated unpacking targets, boolean values behind
  `continue`-shaped filters, captured generators and generator walrus
  cells in bounded expression simulation, `async with` exception regions
  across suspension cleanup, context exits across early returns and
  `finally`, computed returns through nested context and loop handlers,
  private handler clauses after nested `try`, handler `break` after
  iterator disposal, and None-led rejection guards / shared validation
  raises with formatted messages and causes.
- `src/decompiler.rs` +933 lines, plus a new `src/decompiler_stack_tests.rs`
  unit-test module; no dependency, build or CI changes.
- Verification (merged tree): cargo tests 45 + 9 + 62 all pass; stdlib
  corpus **622/622 semantic** (499 signature-exact) after the new
  fixtures; behavior matrix **754/754 = 100%** (2.6–3.15, with and
  without `--cure`); real-world corpus **6411/6411 recompile** and
  **2502 AST-identical** (was 2493); roundtrip 198/234 on the enlarged
  fixture set (was 189/234 with the same fixtures).
- No regressions: on the original 528 corpus modules the verdicts are
  527 identical + 1 improved and 0 worse; across the 349 real-world
  modules whose output changed, bytecode-signature comparison shows 0
  regressions and 50 files moving to signature-identical; 1564 mutated
  or truncated pycs produce no panics.

### Fixes
- **`TO_BOOL` coercion was dropped** (Python 3.12+): a bool that escapes as
  a value was rendered as its operand, so `return not not x` decompiled to
  `return x` — returning a non-bool (and skipping a raising `__bool__`)
  instead of `bool(x)`. The instruction is still transparent when the next
  instruction re-coerces (conditional jump, `UNARY_NOT`), and now renders
  as `not not x` when the value escapes; `if x:` output is unchanged.
  Found with the new `tools/cure_differential.py` battery.
- `tools/cure_differential.py`: 45-case differential harness for `--cure`
  (source → pycdc → run vs. cure → run), covering side-effecting dead
  stores, `__bool__`/operator/property effects, `del`, `finally` returns,
  loop `else`, walrus, closures, generators, exception chaining and
  `not not`. Against cure 0.4.1 it reports the `del` regression; against
  the fixed cure it is clean.
- Fixtures `tests/fixtures/bool_coercion.py` + `.pyc` for 3.12–3.15 and an
  integration test pinning the three shapes (value, assignment, branch).

### Dependencies
- `cure-engine` / `cure-python-{parser,print,simplify}` 0.2 → **0.4.1**
  (all still dependency-free, MSRV stays 1.74). 0.4 adds comment
  fidelity, three new Python rules and directive-comment freezing.
- `serde_json` 1.0.151 → **1.0.154**, `thiserror` 2.0.20 → **2.0.21**
  (plus transitive `syn` 3.0.9, `unicode-ident` 1.0.27); no API changes.
- **`--cure` guard for deleted locals**: cure 0.4.1 propagates a local's
  last literal into reads that follow `del name` (turning a real
  `UnboundLocalError` into a value) and can drop a bare read entirely.
  The integration now skips modules that contain a `del` of a bare name
  and says why on stderr; `del obj.attr` / `del box[k]` still get the
  pass, so only 111 of the 6411 real-world modules (1.7%) are skipped.
  Root cause fixed upstream (`cure` `collect_deleted_names`); the guard
  can be removed once a cured release carries it.
- Re-verification with 0.4.1: behavior matrix **754/754 = 100%** with
  and without `--cure`; corpus 622/622 semantic on the default path and
  all 622 still compile under `--cure`; real-world 6411/6411 recompile
  (2502 AST-identical), and `--cure` output for those modules is
  parseable with **−9.39% lines** (1 690 293 → 1 531 610).

## v0.8.0 — 2026-10-26

### `--cure`: optional simplification and formatting
- New opt-in flag `pycdc --cure` runs the decompiled source through
  [`cure`](https://github.com/ejfkdev/cure) (MIT), linked in-process — no
  external binary and still no Python at runtime. It folds early-return
  guards and if/else assignments into ternaries, removes redundant
  parentheses, normalizes quote style and reflows formatting.
- Measured on the full real-world corpus (6411 modules, seven projects):
  0 parse errors and 0 recompile errors that were not already present in
  the default output; 1 690 169 → 1 528 230 lines (−9.58%). On the
  528-module stdlib corpus every cured module still compiles under its
  own interpreter (no syntax errors, no incompleteness markers).
- The default path is untouched: pycdc's verified output stays byte-for-byte
  as before, and `--cure` can only replace it when the whole module parses
  cleanly. Sources mentioning compiler introspection metadata
  (`__annotate__`, `co_freevars`, `__conditional_annotations__`,
  `__classdict__`) are emitted unchanged, because folding the annotation
  registration gates changes `__annotate__.__code__.co_freevars` at runtime.
- `src/simplify.rs` wraps the zero-dependency `cure` crates
  (`cure-engine`, `cure-python-parser`, `cure-python-simplify`,
  `cure-python-print`, plus `cure-python-ast` transitively) behind a
  `simplify_python(&str) -> Option<String>` fallible API.
- `tools/run_behavior.py --cure` runs the behavior matrix through the new
  pass: **663/663 = 100%** with and without it. `tools/verify_corpus.py
  --cure` repeats the corpus run into `out-cure/` + `report-cure.json`,
  leaving the default baseline intact.
- MSRV raised 1.70 → 1.74 (required by cure).

## v0.7.0 — 2026-10-24

### Python 3.15
- `tools/gen_configs.py` now generates 3.15 from the live interpreter
  (`NATIVE_VERSIONS`) instead of the stale xdis table. `dump_native.py`
  reads 3.15's `frozendict` `_inline_cache_entries`, so the committed
  `configs/opcodes/python_3_15.json` carries all 22 inline-cache counts
  and the 6-entry `cmp_op`; the previous empty table mis-decoded every
  cached instruction.
- decompiler support for 3.15's changed encodings: inline comprehensions
  (`GET_ITER` between the accumulator build and `FOR_ITER`, append arg 3),
  the extended `LOAD_COMMON_CONSTANT` table (list/set/None/''/True/False/
  -1), `IMPORT_NAME`'s name index at `arg >> 2`, `yield from` encoded as
  `GET_ITER 3`, the loop-return cleanup `SWAP 3; POP_TOP; POP_TOP`, and the
  `list`/`set` inline guards.
- PEP 649/749: strip the compiler's module-scope
  `__conditional_annotations__ = set()` prologue (3.14+) so
  `from __future__ import ...` stays at the top of the file.
- handler-loop returns: 3.15 closes them with
  `SWAP 3; POP_TOP; POP_TOP; SWAP 2; POP_EXCEPT; RETURN_VALUE`; the
  return-cleanup scan now looks through POP_EXCEPT, and the forward
  condition-chain merger accepts LOAD_SMALL_INT/LOAD_COMMON_CONSTANT
  epilogue stubs. The seeded value-region simulator handles 3.15's
  constant args, closing OR chains such as `if A and B: ... elif C or D:`.
- genexp/with refinements (also fixes 3.14): a computed callable inside a
  genexpr element no longer mistakes a preceding attribute value for a
  method receiver (`enet_tol=self.enet_tol, max_iter=int(...)`); a ternary
  used as a call argument folds at its merge label instead of only at
  YIELD/LIST_APPEND; the inline tuple/all/any fast-path guard is
  recognized inside a genexpr element; nested class-body protocol
  assignments (`__classdictcell__`, `__static_attributes__`) are stripped
  recursively; and the with success-exit recognizer accepts 3.15's
  common-constant Nones.
- with as-targets: the sync enter-call scan now resumes at the as-target's
  object load instead of skipping it, so `with ctx as h.attr:` and
  `with ctx as d[k]:` recover the target (previously 3.14/3.15 emitted
  `/*with-result*/(None.__enter__)`).
- genexp walker: `SET_FUNCTION_ATTRIBUTE` pops the closure tuple, fixing
  nested `genexpr` closures used as filter calls; `is_pure_value_op`
  accepts `LIST_EXTEND`/`SET_UPDATE`/`DICT_UPDATE`/`LIST_TO_TUPLE`, so an
  inline `any([...])` guard inside a comprehension filter is recognized.
- verification: behavior matrix **663/663 = 100%** (2.6–3.15), stdlib
  corpus 528/528 semantic, real-world corpus 6411/6411. pandas and
  scikit-learn compiled with 3.15: **2091/2091 (100%)** recompile. One
  `with`-body-return edge remains documented in `docs/LIMITATIONS.md`.

### Community fixes (PRs #1–#26)
- merged 26 targeted fixes from @EiNSTeiN- covering 3.11–3.14 bytecode
  families: chained assignments and comparison chains; COPY/SWAP and
  walrus in the bounded expression simulator; keyword calls and ordered
  `**` expansions; comprehension filter polarity, Boolean elements,
  nested conditional elements and nested comprehensions inside generator
  expressions; `for x in await f()` iteration protocol; padded handler
  returns; EXTENDED_ARG loop back edges; guarded `else` suites; split
  try/except/else/finally printing; marshalled slice constants vs runtime
  `slice()` calls; and PEP 649 class-annotation registration gates.
- the 26 branches and their regression tests were merged and verified
  together. Three textual conflicts were resolved by keeping both sides:
  PR #6 stacks on #5, all PRs append tests at the same point in
  `tests/integration.rs`, and #4/#5/#6/#24 append test-module
  declarations at the end of `decompiler.rs`.

### Fixed
- value-position and-chains in a ternary: `try_dup_tail_ternary` now
  absorbs leading same-target cond jumps into the condition, so
  `lambda x: d[np.nan if isinstance(x, float) and np.isnan(x) else x]`
  (pandas core/algorithms) renders verbatim instead of leaving the first
  link as an `if` (which produced a marked-incomplete lambda). The
  duplicated arm tails still hoist through the existing single-slot
  merge, so `d[a if c and e else b]` keeps the shared lookup.

### Benchmarks
- real-world corpus: 6411/6411 modules recompile (100%); the former
  nested-comprehension family (pandas `to_dict`, sklearn `_logistic`,
  `pairwise`) is closed, and strict AST equality rises to 2493/6411


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

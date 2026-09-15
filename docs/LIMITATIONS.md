# Known limitations / 已知限制

Detailed gap list as of v0.4.0. Headline numbers: corpus **520/520 semantic**
(zero syntax errors, zero placeholders), behavior matrix **490/490**.
Everything below is either (a) a rare shape that stays semantically
equivalent, or (b) a corner with no occurrence in the 520-module corpus.

截至 v0.4.0 的完整缺口清单。总体：语料 **520/520 语义等价**（零语法错误、
零占位符），行为矩阵 **490/490**。以下条目要么 (a) 罕见形状但语义仍等价，
要么 (b) 520 模块语料中零触发的边角。

## try / except / finally

- 3.11+ rebuilds from the exception table (except*, nested chains,
  continue/return inside handlers, inline-finally copy pruning in loops,
  sibling module-level tries, sunk `return None` normalization); 3.8–3.10
  SETUP_* era via a chain state machine; py2 else-region emission gated by
  provenance. Empty `finally: pass` chains render as real try/finally;
  `finally: return X` swallow shapes are placed correctly in both eras.
- **Gap (2.x/3.5–3.10)**: "continue inside an except branch + finally on the
  same try + inside a loop" can lose loop-nesting structure (may emit a
  placeholder on 3.10; behavior usually still equivalent).
- **Gap (3.9/3.10)**: an inline try inside a with body may flatten and leak
  `__exit__` protocol calls (behavior-equivalent, with placeholder).
- **Gap (3.11 only)**: a handler whose loop-exit FOR_ITER target lands
  directly on POP_EXCEPT (no END_FOR separator — 3.12+ has one) loses the
  handler's post-loop tail statements (e.g. `except E: for ...: ...; return
  'miss'` drops the final return). In-loop returns are unaffected.
- Bare-except placement can add one semantically-equivalent `continue` at the
  tail of a handler inside a loop.
- 2.x/3.5–3.10 中「except 分支内 continue + 同 try 带 finally + 位于循环内」
  可能丢失循环嵌套（3.10 可触发占位符，行为多数仍等价）；3.9/3.10 的 with
  体内联 try 可能平铺并泄漏 __exit__ 协议调用（行为等价、含占位符）。

## match / case (3.10–3.14)

- Supported: literal/capture/wildcard/or/sequence (incl. `*rest`)/mapping
  (incl. value patterns and `**rest`)/class patterns/singletons/guards,
  match inside loops. Or-arms may render as multiple cases sharing a body
  (equivalent).
- **Gaps**: 3.10 legacy per-attribute extraction (BINARY_SUBSCR+ROT),
  recursive nesting inside pattern slots, or-expansion between non-literal
  patterns, and the inverted in-loop last-case shape (`case 2: return`) —
  can degrade to a wildcard/condition stub (behavior usually equivalent).
- 缺口：3.10 旧式逐属性提取、模式槽位内递归嵌套、非字面量模式间 or 展开、
  循环内倒置最后 case 形状——可退化为通配/条件残桩（行为多数仍等价）。

## Annotations (3.14 PEP 649)

- Function/method/module/class-level annotations are restored to real
  annotation statements, including `__conditional_annotations__`-gated ones;
  runtime `get_annotations` VALUE/FORWARDREF match the original exactly.
- **Corner**: entries inside dead branches the compiler folded away
  (`if False:`) are dropped — VALUE/FORWARDREF semantics still match; only
  the STRING-format annotation dict differs (the original keeps the dead
  entry's text).
- 边角：死分支（`if False:` 内）注解条目被丢弃——VALUE/FORWARDREF 与原始
  一致，仅 STRING 格式注解字典有差异。

## Misc / 其他

- `with a, b:` renders as nested with statements (equivalent).
- Async gaps: inlined async comprehensions, async-generator asend/athrow
  protocol, the 3.7 SETUP_EXCEPT-guarded async-for break+else combination.
- Ternaries inside comprehension elements can be misplaced on some old
  versions.
- py2 deep-nesting shape "if containing an if + sibling elif + dangling tail
  return" may lose subsequent branches.
- A few 3.3 modules (_weakrefset/copy/copyreg) are AST-PASS with an empty
  `orelse=[]` placement difference (not else-body loss).
- Python 1.x: marshal loads, but no opcode tables are bundled.
- PyPy/Jython/GraalPy variants: best effort via matching CPython tables.
- `with a, b:` 输出为嵌套 with（等价）；async 缺口：内联 async 推导式、
  async 生成器 asend/athrow 协议、3.7 守卫式 async-for break+else；推导式
  元素三元表达式在部分旧版本可能错位；py2 深嵌套「if 内嵌 if + 同级 elif +
  尾部悬挂 return」可能丢后续分支；Python 1.x 可加载 marshal 但无 opcode 表。

## Third-party package long tail (3.12 venv smoke: six/packaging/click/attrs/pluggy)

67 modules: 0 syntax errors, 0 decompile errors, 34 normalized-AST passes
after this round's fixes (dotted-as imports, stacked class decorators,
PEP 563 string annotations). The remaining ~30 AST-diffs form the backlog
queue (each reproducible by decompile -> recompile -> ast_compare against
the installed source):

- bool-chain polarity renders Or where source had And (De Morgan placement
  not normalized): click/_textwrap, click/shell_completion, packaging/tags,
  packaging/requirements, packaging/version, pluggy/_manager
- `assert not c` rendered as `if c: raise AssertionError` (equivalent under
  normal runs; differs under -O): click/decorators, pluggy/_hooks
- statement displacement around `while True` loops: click/_compat,
  click/termui
- extra no-op Try nesting around with-in-try (3.12 exception-table
  artifact): click/core
- nested constant tuple flattened one level: packaging/_ranges
- multi-name `from m import a, b` split into single-name statements
  (comparator merge misses non-adjacent order): click/__init__
- genexpr element corruption: attr/validators; nonlocal list drift:
  attr/_next_gen; Assign demoted to Expr: click/_termui_impl
- deeper bracket-depth structural drifts: attr/_cmp, attr/_funcs,
  click/exceptions, click/parser, click/testing, click/utils, six,
  packaging/markers, packaging/dependency_groups, packaging/specifiers,
  packaging/metadata, packaging/ranges, pluggy/_callers, pluggy/_warnings
- incomplete-warning shapes: attr/_make (2100-line metaclass machinery),
  packaging/pylock (CALL-chain underflow in `select`: three stacked CALLs
  after an arg-position ternary)

## Remaining non-parsing shapes (2 files of the full-stdlib corpora)

Full-stdlib benchmarks (1017 modules of 3.12.14, 1251 of 3.8.20) leave
exactly two modules whose decompiled output does not parse. Both are
marked incomplete (never a crash, never silent corruption) and both are
structural reconstruction gaps in the loop-guard machinery rather than
rendering bugs:

- `multiprocessing/connection.pyc` 3.12 — `try: ... except OSError: ...
  else: <nested try/except/finally>` : the else body is emitted as a
  sibling statement and the outer `else:`/`finally:` labels then land
  after it, so the file dies with `expected 'except' or 'finally'
  block`. Reproduces in `PipeListener.accept` (win32 branch).
- `random.pyc` 3.8 — `while True: if not 1e-7 < u1 < 0.9999999:
  continue` : a negated multi-link guard at a loop top loses the
  enclosing `while True` entirely and degrades into
  `if <A>: pass` + `while not <B>: pass` with the tail statement
  ejected from the loop. Minimal repro (3.8, also 2.7–3.13):

  ```python
  def w2(a, b):
      while True:
          if not (a < b and b < 10):
              continue
          return 2
  ```

  Single-link guards and negated *or* guards are handled correctly
  (`while not <C>: pass` normalization); only the negated two-link
  *and* form falls into the unmerged path, and the De Morgan refold
  (`refold_demorgan`) cannot see it because the or-chain never gets
  assembled into one expression. Fixing this needs the loop-top guard
  chain (handle_cond_jump / try_or_and_chain / try_fwd_or_continue
  family) to merge the operand run into `And[A, B]` before the
  while-ification — the most heavily tuned subsystem in the codebase
  (300+ regression-driven special cases), so it is left documented
  rather than patched blind.

### Nested comprehension inside a genexp (3 modules, deliberately not patched)

`({c: v for c, v in zip(cols, row) if c} for row in rows)` — a genexp whose
*element* (or a call argument inside it) is an inlined (PEP 709) dict
comprehension. The genexp keeps its own code object and is decompiled by
the comprehension walker, which has no notion of a nested level: the
inner `BUILD_MAP 0` accumulator lands on the walker's stack, `SWAP` is
not modeled, and the following `FOR_ITER` treats it as a second `for`
clause (`... for c, v in {}`), so the output does not parse.

A frame-stack prototype (one frame per comprehension level, `SWAP`
modeled, the accumulator placeholder replaced by Rc identity when a level
ends, `pending_or_filter` flushed per level) was implemented **twice** and
reverted both times. What it achieved, verified by runtime-equivalence
checks against the original sources: the whole-element shape and the
call-argument shapes *as minimal repros* became semantically correct
(`({c: v for c, v in zip(cols, t) if c} for t in rows)`,
`(f(**d) for x in xs)`, `(f(x, y=1) for x in xs)`; the last two were
fixed for real and are committed).

It still produced *plausible but semantically wrong* output for the three
real modules (`pandas/core/methods/to_dict.py`,
`sklearn/linear_model/_logistic.py`, `metrics/pairwise.py`), e.g.

    fd(func, ret, s, X, Y[s, ...], **{k: (v[s] if k == "Y" else v) for k, v in kwds.items()})
    ->  (fd if k == 'Y' else (func, ret, s, X, Y[s, ...])(*{}, **{**k}) for s in ...)

The blocker is not the nesting itself: the walker's stack model for
3.11+ calls (`PUSH_NULL`, the args/kwargs slots, `KW_NAMES`) is a
heuristic that happens to agree with the VM on the shapes the corpus
exercises, and a nested level exposes the disagreement. A correct fix
therefore starts with making that call model faithful (or by delegating
the enclosing expression to the main engine's `exec`), and only then
re-adding the nesting. Emitting a visible syntax error stays preferable
to silently wrong code, so the modules remain in the failing set.

### Multi-link ternary on the value path (1 module, ambiguous to repair)

`pandas/core/algorithms.py` — `lambda x: d[np.nan if isinstance(x, float)
and np.isnan(x) else x]`. The value path does not merge the two
same-target `POP_JUMP_IF_FALSE` links into one `And`, so the walker keeps
the first link as an `If` and folds the rest into a ternary:
`[If { cond: c, body: [Return(d[Ternary { cond: e, ... }])] }]`.

A local repair (fold the `If`'s condition into the inner ternary) is NOT
sound: after `postprocess_body` strips a trailing `return None`, the
*same* shape is produced by the legitimate source
`lambda: d[a if e else b] if c else None`, which must stay as it is. The
sound fix is upstream — merge same-target cond jumps in the value path
the way the statement path already does — which belongs to the
`handle_cond_jump` link-merge machinery.

## Fixed recently (no longer limitations) / 近期已修复

- Syntax-family fuzz battery (25 shapes × 10 interpreters) driven fixes:
  comprehension-element ternaries kept their else arm on all versions;
  negated genexpr filters (`if not C`) survive the 3.12+ PJIF-to-emit and
  py2.6 jump-trampoline polarity encodings; py2 nested inline
  comprehensions keep their nesting (accumulator prologue/teardown
  tolerance); lambda elements work in 3.12+ inline comprehensions
  (MAKE_CELL prologue); assert messages restored on 3.11–3.14
  (LOAD_ASSERTION_ERROR/LOAD_COMMON_CONSTANT + CALL-0 self-slot shape and
  f-string-folded messages); try/except/finally with a body-tail return no
  longer collapses on 3.8–3.10 (stashed-chain fold + as-cleanup-aware
  chain-end scan); in-handler `return <expr>` inside loops no longer splits
  into an expression statement plus a bare return (handler-return unwind
  protocol POP_TOP phantom-consume).
- PEP 695/696 type parameters (3.12+): full support incl. bounds,
  constraints, `*Ts`/`**P`, defaults.
- PEP 750 t-strings (3.14+): interpolation, conversions, format specs.
- 2.7–3.9 elif-nested-if arm loss: re-verified fixed (b28_elifnest green on
  all 13 interpreters).
- Module/class-level conditional annotations: restored to statements.
- Empty-finally chains and `finally: return X` swallow shapes.

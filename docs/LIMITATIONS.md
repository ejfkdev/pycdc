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

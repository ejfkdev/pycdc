# Benchmarks / 基准测试

Cross-tool comparison of `.pyc` decompilers: speed, memory and output
quality on real stdlib corpora. Host: macOS (Darwin 25.6.0) Apple
Silicon, 2026-09-14. Raw data: [`bench-312.json`](bench-312.json),
[`bench-38.json`](bench-38.json); harness: [`tools/bench_compare.py`](../tools/bench_compare.py).

## Tools surveyed / 工具调研

| Tool | Repo | Stars | Impl | Python support | Note |
|---|---|---|---|---|---|
| **pycdc-rs (this project)** | ejfkdev/pycdc | — | Rust | 2.0 – 3.15 | deterministic, parallel batch mode |
| Decompyle++ | zrax/pycdc | 4.6k | C++ | 2.x – 3.13 (partial) | the classic native decompiler |
| uncompyle6 | rocky/python-uncompyle6 | 4.3k | Python | 1.0 – 3.8 | last release supports ≤3.8 |
| decompyle3 | rocky/python-decompyle3 | — | Python | 3.7 – 3.8 | uncompyle6 successor fragment |
| xdis (pydisasm) | rocky/python-xdis | 0.4k | Python | many | disassembler only, not compared |
| PyLingual | syssec-utd/pylingual | 1.4k | Python+torch | 3.6 – 3.14 | **excluded**: neural pipeline, needs HuggingFace model weights; huggingface.co unreachable from the benchmark host |
| pychd | diohabara/pychd | 54 | Python | 3.0 – 3.14 | **excluded**: `decompile()` requires an external LLM API (GPT/Claude) — out of scope for a local, deterministic benchmark |

Emerging tools (PyLingual — IEEE S&P'25, PLDI'25 tutorial; pychd) are
the interesting new direction but cannot be benchmarked locally: one
phones out to an LLM API per file, the other needs multi-hundred-MB
model downloads that the benchmark network blocks. Everything below is
therefore restricted to deterministic, offline, local tools.

## Method / 方法

- Corpora: the CPython standard library compiled with `compileall -b`
  — **3.12.14: 1017 modules**, **3.8.20: 1251 modules**; the original
  `.py` stays next to each `.pyc`, which provides ground truth.
- Per file, serially: one CLI process per `.pyc` (how the tools are
  actually used). Wall time = harness monotonic clock; peak RSS via
  `/usr/bin/time -l`.
- `success` = exit 0 + non-empty stdout. `compiles` = the decompiled
  output parses under the same interpreter that produced the corpus.
  `ast-exact` = docstring-stripped `ast.dump(output)` equals
  `ast.dump(original source)` — a strict semantic-equivalence check.
- uncompyle6/decompyle3 cannot read >3.8 bytecode, so they only appear
  in the 3.8 table.

## Results, Python 3.12 corpus (1017 files)

| Tool | success | compiles | ast-exact | wall total | per file | peak RSS | median RSS |
|---|---|---|---|---|---|---|---|
| **pycdc-rs v0.6.0** | 1003 (98.6%) | **993 (97.6%)** | **273** | 6.1 s | 6.0 ms | 30.0 MB | 2.8 MB |
| pycdc C++ (b428976, 2026-04) | 989 (97.2%) | 570 (56.0%) | 46 | 5.2 s | 5.1 ms | 2.8 MB | 1.8 MB |

## Results, Python 3.8 corpus (1251 files)

| Tool | success | compiles | ast-exact | wall total | per file | peak RSS | median RSS |
|---|---|---|---|---|---|---|---|
| **pycdc-rs v0.6.0** | 1229 (98.2%) | **1219 (97.4%)** | **494** | **7.6 s** | **6.0 ms** | 7.0 MB | **2.8 MB** |
| pycdc C++ | 890 (71.1%) | 524 (41.9%) | 98 | 8.1 s | 6.5 ms | **3.4 MB** | 1.9 MB |
| uncompyle6 3.9.3 | 1176 (94.0%) | 706 (56.4%) | 134 | 1133.8 s | 906.3 ms | 186.3 MB | 26.3 MB |
| decompyle3 3.9.3 | 1251 (100%)* | 22 (1.8%) | 0 | 2279.2 s | 1821.9 ms | 168.4 MB | 27.0 MB |

\* decompyle3 exits 0 while emitting commented disassembly fragments
(`# not in loop: # break …`) for most modules — non-empty but not
Python. Its `compiles` column is the meaningful quality signal.

## Batch mode (single process, whole 3.12 corpus, pycdc-rs)

| Mode | wall | peak RSS |
|---|---|---|
| `pycdc -q -j 1 src/ -o out/` (serial) | 0.44 s | 44.8 MB |
| `pycdc -q src/ -o out/` (parallel, 8 threads) | 0.08 s | 43.7 MB |

1017 modules decompiled in 80 ms wall / 0.44 s serial CPU-time in one
process; the per-file table above includes ~1 ms/process fork overhead.

## Findings / 结论

- **Speed**: the two native tools are in the same league (~5–6 ms per
  module, process spawn included). The Python tools are 150×
  (uncompyle6) and 300× (decompyle3) slower per file — minutes vs
  seconds on a full stdlib.
- **Memory**: native median RSS 2–3 MB; the Python decompilers sit at
  ~27 MB median and 170–190 MB peak.
- **Quality on modern bytecode (3.12)**: pycdc-rs keeps 97.6% of the
  stdlib recompilable vs 56.0% for Decompyle++; strict AST equality
  273 vs 46 modules.
- **Quality on 3.8**: pycdc-rs 97.4% recompilable / 494 AST-exact,
  ahead of uncompyle6 (56.4% / 134), Decompyle++ (41.9% / 98) and
  decompyle3 (1.8% / 0).
- **Coverage**: only the native tools handle Python ≥3.9 at all;
  uncompyle6/decompyle3 stop at 3.8, decompyle3 effectively fails on
  most of it.
- Decompyle++ remains the leanest binary (peak 2.8–3.4 MB); pycdc-rs
  trades a few MB for far higher fidelity and a parallel batch mode.

## Reproduce / 复现

```sh
# build corpora (stdlib of the interpreter that will also validate)
python3 -m compileall -q -b /path/to/srcdir

# run the harness (tool binaries via BENCH_* env vars or defaults)
python3 tools/bench_compare.py --corpus /tmp/bench312/src \
    --interp /path/to/python3.12 \
    --tools pycdc-rs,pycdc-cpp --out benchmarks/bench-312.json
```

---

# 中文摘要

- **语料**：CPython 标准库 `compileall -b` 编译：3.12.14 共 1017 模块、
  3.8.20 共 1251 模块；源码与 pyc 同目录，可作语义真值。
- **方法**：逐文件串行调用 CLI（真实使用方式）；墙钟为 harness 单调
  时钟，峰值 RSS 取 `/usr/bin/time -l`；`compiles` = 产物能被同版本解
  释器解析；`ast-exact` = 去 docstring 后 AST 与原源码完全一致。
- **未纳入**：PyLingual（S&P'25 神经方案，需 HuggingFace 模型权重，
  基准网络不可达）；pychd（`decompile()` 强制外部 LLM API，不做本地
  确定性对比）。
- **速度**：两个原生工具同量级（约 5–6 ms/模块，含进程启动）；
  uncompyle6 慢约 150 倍、decompyle3 约 300 倍（全标准库分钟级 vs 秒级）。
- **内存**：原生中位 RSS 2–3 MB；Python 系中位 ~27 MB、峰值 170–190 MB。
- **质量**：3.12 语料 pycdc-rs 97.6% 可重编译 / 273 个 AST 完全一致，
  Decompyle++ 为 56.0% / 46；3.8 语料 pycdc-rs 97.4% / 494，优于
  uncompyle6（56.4% / 134）、Decompyle++（41.9% / 98）、decompyle3
  （1.8% / 0，多数文件输出注释化反汇编残片）。
- **覆盖**：仅原生工具支持 3.9+；uncompyle6/decompyle3 止于 3.8。
- **批量**：pycdc-rs 单进程串行 0.44 s、默认并行 0.08 s 跑完 1017 模块，
  峰值 RSS ~44 MB。

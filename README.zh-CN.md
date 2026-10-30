# pycdc-rs

[English](README.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-2.0--3.15-yellow.svg)](#)
[![Corpus](https://img.shields.io/badge/corpus-622%2F622%20semantic-brightgreen.svg)](#验证)
[![Behavior](https://img.shields.io/badge/behavior-754%2F754-brightgreen.svg)](#验证)
[![Built with ZCode](https://img.shields.io/badge/Built%20with%20ZCode-000000.svg?style=flat&logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMTgiIGhlaWdodD0iMTAwIiB2aWV3Qm94PSIwIDAgMjU2IDIxOCI+PHBhdGggZmlsbD0iI2ZmZmZmZiIgZD0iTTEzNC40IDAuMTMwMTUyTDExNi40OCAyNS42MDIyQzExMy42NjUgMjkuNTY5OSAxMDkuMDU0IDMyLjAwMTkgMTA0LjA2NCAzMi4wMDE5SDYuMzk5OVYwQzYuMzk5OSAwLjEzMDE0OSAxMzQuNCAwLjEzMDE1MiAxMzQuNCAwLjEzMDE1MloiLz48cGF0aCBmaWxsPSIjZmZmZmZmIiBkPSJNMjU2IDAuMTMwMTI3TDEwMi40MDEgMjE3LjczMkgwTDE1My41OTkgMC4xMzAxMjdIMjU2WiIvPjxwYXRoIGZpbGw9IiNmZmZmZmYiIGQ9Ik0xMjEuNjAxIDIxNy43MzJMMTM5LjY1IDE5Mi4xMzRDMTQyLjQ2NSAxODguMTY2IDE0Ny4wNzYgMTg1LjczNCAxNTIuMDY3IDE4NS43MzRIMjQ5LjYwNFYyMTcuNzM2SDEyMS42MDFWMjE3LjczMloiLz48L3N2Zz4=)](https://zcode.z.ai/)

用 Rust 编写的 Python 字节码反编译器与反汇编器：把 **Python 2.0 – 3.15** 的 `.pyc` 还原为可读源码。运行不需要 Python，另可选内置的 [`cure`](https://github.com/ejfkdev/cure) 简化器。

```sh
pycdc program.pyc          # 反编译到标准输出
pycdc dis program.pyc      # 反汇编（异常表、行号、嵌套 code object）
```

## 亮点

- 14 个解释器（2.6–3.15）、622 个真实标准库模块语料上**语义等价 100%**，其中 80.2% 达到字节码签名级完全一致
- **行为矩阵 754/754 = 100%**：2.6–3.15 全部通过（含 3.15 新字节码编码）
- 现代语法：PEP 695/696 类型参数、PEP 750 t-string、PEP 649 延迟注解、match/case、海象运算符、async、f-string
- 可选 `--cure`：在进程内调用 `cure` 简化器/格式化器（无需外部二进制、不依赖 Python），把 `if cond: return a` / `return b` 折成 `return a if cond else b`，行数约减少 10%
- 版本差异全部数据化：每版本一张内嵌 opcode 表，`--opcodes` 可外部覆盖
- 优雅降级：无法识别的构造输出注释占位，绝不崩溃

## 安装

**Homebrew（macOS 与 Linux）：**

```sh
brew install ejfkdev/tap/pycdc
```

**Scoop（Windows）：**

```powershell
scoop install https://raw.githubusercontent.com/ejfkdev/scoop-bucket/main/bucket/pycdc.json
```

清单会按 x64 / arm64 自动选择，并同时安装 `pycdc` 与 `pycdas`。若想按名称安装，先添加一次 bucket：

```powershell
scoop bucket add ejfkdev https://github.com/ejfkdev/scoop-bucket
scoop install pycdc
```

**cargo，来自 [crates.io](https://crates.io/crates/pycdc)：**

```sh
cargo install pycdc
```

**预编译二进制：** [Releases](https://github.com/ejfkdev/pycdc/releases)
页面提供裸可执行文件（无压缩包外壳）——Linux / Windows 的 x86_64 与
arm64、macOS 的 arm64 与 x86_64；Linux 与 Windows 产物经 UPX 压缩，
macOS 不压缩。

**源码构建：**

```sh
cargo build --release      # 产物: target/release/pycdc 与 pycdas
cargo install --path .     # 或从检出目录安装两个二进制
```

以上任一方式均同时提供 `pycdc` 与 `pycdas`。

## 使用

```sh
# 单文件：标准输出 / 指定文件 / 指定目录
pycdc program.pyc > program.py
pycdc program.pyc -o program.py
pycdc program.pyc -o ./outdir/

# 批量：镜像目录结构（默认按 CPU 核数并行，-j N 控制线程数）
pycdc ./pyc-corpus -o ./src-out
pycdc ./pyc-corpus               # 生成 ./pyc-corpus-decompiled/
pycdc a.pyc b.pyc                # 在输入旁生成 a.py、b.py
pycdc ./pyc-corpus -o ./src-out -q -j 8

# 标准输入（管道场景）：- 表示从 stdin 读取 pyc
cat program.pyc | pycdc -

# 无 pyc 头的裸 marshal 数据，显式指定版本
pycdc -v 3.8 payload.marshal

# 反汇编——与 pycdc 相同的 CLI 能力（文件/目录/stdin、-o/-j/-q）
pycdc dis program.pyc
pycdc dis ./pyc-corpus -o ./dis-out # 镜像生成 .dis 文件
# 独立的 `pycdas` 二进制保留为兼容别名，输出逐字节一致
pycdas program.pyc

# 可选的简化/格式化（进程内链接 cure）
pycdc --cure program.pyc
```

`--cure` 是可选的美化步骤：pycdc 的默认输出本身已通过验证，因此默认
行为不变。开启后条件分支会折叠为三元表达式、引号统一为单引号、版式重排：

```python
# 默认                                      # --cure
def classify(v):                            def classify(v):
    if v is True:                               return 1 if v is True else 0
        return 1
    return 0
```

若输入无法被 `cure` 解析，或含有编译器内省元数据（`__annotate__`、
`co_freevars`、`__conditional_annotations__`、`__classdict__`）——简化这些
内容可能改变运行语义——该文件会原样输出，并在 stderr 给出提示。行为矩阵
在开启/关闭 `--cure` 两种情况下均为 754/754；622 个语料模块在开启后也全部
仍能在各自解释器下编译。由于该步骤会刻意改写语句形态（if/else → 三元），
语料的字节码签名指标对 `--cure` 输出不具参考意义，请以行为矩阵为准。

全部参数见 `pycdc --help`、`pycdc dis --help`、`pycdas --help`。退出码：`0` 成功，
`1` 存在处理失败的文件，`2` 用法错误。

## 性能

Apple Silicon 实测，526 个真实 `.pyc`（约 9.5MB，2.6–3.14 标准库语料）：

| 场景 | 耗时 | 峰值内存 |
|---|---|---|
| 批量（默认并行） | **≈0.05s** | ≈25MB |
| 批量（`-j 1` 串行） | ≈0.34s | ≈13MB |
| 最大单文件（74KB，含进程启动） | ≈5.5ms | ≈4.4MB |
| 进程启动开销 | ≈2ms | — |

### 真实项目语料（7 个大型项目，最新 release tag）

`tools/fetch_realworld.sh` 会按**各仓库最新 release tag** 稀疏检出指定目录、
用 `compileall -b` 把每个 `.py` 编译成 `.pyc`，落到 `tests/realworld/`
（已加入 gitignore——该脚本是重建语料的唯一方式）：

| 项目（tag） | 模块数 | 串行 `-j 1` | 并行（默认） | 可重编译 | AST 完全一致¹ |
|---|---|---|---|---|---|
| yt-dlp (2026.08.19) | 1045 | 0.38 s | 0.08 s | **1045/1045** | 502/1045 |
| matplotlib (v3.11.2) | 253 | 0.28 s | 0.07 s | **253/253** | 60/253 |
| pandas (v3.0.5) | 1420 | 0.87 s | 0.16 s | **1420/1420** | 586/1420 |
| django (6.1.1) | 907 | 0.33 s | 0.12 s | **907/907** | 470/907 |
| sympy (1.14.0) | 1532 | 3.08 s | 1.62 s | **1532/1532** | 482/1532 |
| scikit-learn (1.9.1) | 671 | 0.42 s | 0.07 s | **671/671** | 216/671 |
| ansible (v2.21.4) | 583 | 0.24 s | 0.05 s | **583/583** | 186/583 |
| **合计** | **6411** | **5.60 s** | **2.17 s** | **6411/6411（100%）** | 2502/6411 |

¹ 严格口径：去掉 docstring 后 AST 与原源码完全一致。等价归一化
（if/else 代替三元、解包外多余的 `*()`/`**{}`、关键字参数顺序调整）也
会被计为差异，因此它是「形状保真度下限」而非错误率；验收口径是左侧的
可重编译列。

每个项目一个 pycdc 进程：串行约 0.87 ms/模块，整批 6.4k 模块峰值
RSS ≈78 MB。**6411 个模块全部可重编译**；最后一族（生成器表达式元素 /
调用参数里的 dict 推导式）已由社区 PR 批次修复。
[`benchmarks/realworld.json`](benchmarks/realworld.json)，
脚本见 [`tools/bench_realworld.py`](tools/bench_realworld.py)。


## 验证

三套可本地复跑的验证设施（需 pyenv/uv 安装 2.6–3.15 解释器）：

| 设施 | 验证内容 | 当前结果 |
|---|---|---|
| [`tools/verify_corpus.py`](tools/verify_corpus.py) | 622 个标准库模块：反编译 → **同版本解释器**重编译 → 结构化字节码签名对比，不一致再做归一化 AST 语义对比 | **622/622 语义等价**（499 签名级一致，零语法错误、零占位符） |
| [`tools/run_behavior.py`](tools/run_behavior.py) | 96 用例 × 14 解释器：原始与反编译代码同解释器运行，对比 stdout+返回码 | **754/754 = 100%**（2.6–3.15） |
| [`tests/roundtrip.py`](tests/roundtrip.py) | fixture 矩阵：编译 → 反编译 → 重编译 → 严格字节码对比 | 49/54 严格一致（exceptions fixture 仅结构差，语义等价） |

3.15 的结果对应 CPython 3.15.0/3.15.1：内联推导式、调用与 import 的编码
有变化，opcode 表由本机解释器直接生成。行为用例已全部通过，pandas+scikit-learn
在 3.15 下 2091/2091 可重编译；剩余的 with 体 return 边角见
[docs/LIMITATIONS.md](docs/LIMITATIONS.md)。

分版本结果见 `tests/corpus/<version>/report.json`。
跨工具对比（与 Decompyle++、uncompyle6、decompyle3 的速度、内存、
输出质量）见 [benchmarks/](benchmarks/README.md)。除上述设施外，发布前还经
三类专项质量电池把关：25 语法族模糊矩阵（×10 解释器）、恶意输入鲁棒性套件
（截断/损坏/OOM 炸弹 pyc——零崩溃）、第三方包 venv 实战冒烟（six/packaging/
click/attrs/pluggy）。详细已知缺口与第三方长尾队列见
[docs/LIMITATIONS.md](docs/LIMITATIONS.md)。

## 项目结构

```
src/    loader → marshal → bytecode → decompiler → codegen（version.rs/opcode.rs 承载版本数据；simplify.rs 封装 cure）
configs/ 内嵌 opcode 表与 magic 表（重生成: tools/gen_configs.py）
tools/   配置生成、语料构建、验证设施
tests/   Rust 测试、fixture、622 模块语料、96 行为用例
```

## 致谢

设计参考 [Decompyle++ (pycdc)](https://github.com/zrax/pycdc)、[uncompyle6/decompyle3](https://github.com/rocky/python-decompyle3) 与 [xdis](https://github.com/rocky/python-xdis)；可选的 `--cure` 后处理由 [cure](https://github.com/ejfkdev/cure) 提供。

## License

[MIT](LICENSE)

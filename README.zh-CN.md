# pycdc-rs

[English](README.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-2.0--3.15-yellow.svg)](#)
[![Corpus](https://img.shields.io/badge/corpus-520%2F520%20semantic-brightgreen.svg)](#验证)
[![Behavior](https://img.shields.io/badge/behavior-516%2F516-brightgreen.svg)](#验证)

用 Rust 编写的 Python 字节码反编译器与反汇编器：把 **Python 2.0 – 3.15（dev）** 的 `.pyc` 还原为可读源码。仅三个依赖，运行不需要 Python。

```sh
pycdc program.pyc          # 反编译到标准输出
pycdas program.pyc         # 反汇编（异常表、行号、嵌套 code object）
```

## 亮点

- 13 个解释器（2.6–3.14）、520 个真实标准库模块语料上**语义等价 100%**，其中 76.5% 达到字节码签名级完全一致
- **行为矩阵 516/516**：反编译产物与原码在同一解释器下运行结果一致
- 现代语法：PEP 695/696 类型参数、PEP 750 t-string、PEP 649 延迟注解、match/case、海象运算符、async、f-string
- 版本差异全部数据化：每版本一张内嵌 opcode 表，`--opcodes` 可外部覆盖
- 优雅降级：无法识别的构造输出注释占位，绝不崩溃

## 安装

**Homebrew（macOS 与 Linux）：**

```sh
brew install ejfkdev/tap/pycdc
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
pycdas program.pyc
pycdc dis program.pyc            # 与 pycdas 输出完全一致
pycdas ./pyc-corpus -o ./dis-out # 镜像生成 .dis 文件
```

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
| yt-dlp（2026.08.19） | 1045 | 0.98 s | 0.12 s | **1045/1045** | 500/1045 |
| matplotlib（v3.11.2） | 253 | 0.53 s | 0.08 s | **253/253** | 59/253 |
| pandas（v3.0.5） | 1420 | 1.65 s | 0.18 s | 1418/1420 | 582/1420 |
| django（6.1.1） | 907 | 0.47 s | 0.12 s | **907/907** | 467/907 |
| sympy（1.14.0） | 1532 | 3.63 s | 1.80 s | **1532/1532** | 479/1532 |
| scikit-learn（1.9.1） | 671 | 0.76 s | 0.09 s | 669/671 | 216/671 |
| ansible（v2.21.4） | 583 | 0.34 s | 0.06 s | **583/583** | 185/583 |
| **合计** | **6411** | **8.36 s** | **2.45 s** | **6407/6411（99.9%）** | 2488/6411 |

¹ 严格口径：去掉 docstring 后 AST 与原源码完全一致。等价归一化
（if/else 代替三元、解包外多余的 `*()`/`**{}`、关键字参数顺序调整）也
会被计为差异，因此它是「形状保真度下限」而非错误率；验收口径是左侧的
可重编译列。

每个项目一个 pycdc 进程：串行约 1.0 ms/模块，整批 6.4k 模块峰值
RSS ≈98 MB。剩余 4 个模块属两种形态：值路径上的多链三元条件
（`lambda x: d[a if c and e else b]`）与「生成器表达式元素内嵌 dict
推导式」——均标记为不完整，不崩溃。原始数据见
[`benchmarks/realworld.json`](benchmarks/realworld.json)，
脚本见 [`tools/bench_realworld.py`](tools/bench_realworld.py)。


## 验证

三套可本地复跑的验证设施（需 pyenv/uv 安装 2.6–3.14 解释器）：

| 设施 | 验证内容 | 当前结果 |
|---|---|---|
| [`tools/verify_corpus.py`](tools/verify_corpus.py) | 520 个标准库模块：反编译 → **同版本解释器**重编译 → 结构化字节码签名对比，不一致再做归一化 AST 语义对比 | **520/520 语义等价**（398 签名级一致，零语法错误、零占位符） |
| [`tools/run_behavior.py`](tools/run_behavior.py) | 50 用例 × 13 解释器：原始与反编译代码同解释器运行，对比 stdout+返回码 | **516/516 = 100%** |
| [`tests/roundtrip.py`](tests/roundtrip.py) | fixture 矩阵：编译 → 反编译 → 重编译 → 严格字节码对比 | 49/54 严格一致（exceptions fixture 仅结构差，语义等价） |

分版本结果见 `tests/corpus/<version>/report.json`。
跨工具对比（与 Decompyle++、uncompyle6、decompyle3 的速度、内存、
输出质量）见 [benchmarks/](benchmarks/README.md)。除上述设施外，发布前还经
三类专项质量电池把关：25 语法族模糊矩阵（×10 解释器）、恶意输入鲁棒性套件
（截断/损坏/OOM 炸弹 pyc——零崩溃）、第三方包 venv 实战冒烟（six/packaging/
click/attrs/pluggy）。详细已知缺口与第三方长尾队列见
[docs/LIMITATIONS.md](docs/LIMITATIONS.md)。

## 项目结构

```
src/    loader → marshal → bytecode → decompiler → codegen（version.rs/opcode.rs 承载版本数据）
configs/ 内嵌 opcode 表与 magic 表（重生成: tools/gen_configs.py）
tools/   配置生成、语料构建、验证设施
tests/   Rust 测试、fixture、520 模块语料、48 行为用例
```

## 致谢

设计参考 [Decompyle++ (pycdc)](https://github.com/zrax/pycdc)、[uncompyle6/decompyle3](https://github.com/rocky/python-decompyle3) 与 [xdis](https://github.com/rocky/python-xdis)。

## License

[MIT](LICENSE)

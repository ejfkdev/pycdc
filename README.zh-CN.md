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

## 构建

```sh
cargo build --release      # 产物: target/release/pycdc 与 pycdas
cargo install --path .     # 可选：安装两个二进制
```

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
pycdas ./pyc-corpus -o ./dis-out # 镜像生成 .dis 文件
```

全部参数见 `pycdc --help` / `pycdas --help`。退出码：`0` 成功，
`1` 存在处理失败的文件，`2` 用法错误。

## 性能

Apple Silicon 实测，526 个真实 `.pyc`（约 9.5MB，2.6–3.14 标准库语料）：

| 场景 | 耗时 | 峰值内存 |
|---|---|---|
| 批量（默认并行） | **≈0.05s** | ≈25MB |
| 批量（`-j 1` 串行） | ≈0.34s | ≈13MB |
| 最大单文件（74KB，含进程启动） | ≈5.5ms | ≈4.4MB |
| 进程启动开销 | ≈2ms | — |

## 验证

三套可本地复跑的验证设施（需 pyenv/uv 安装 2.6–3.14 解释器）：

| 设施 | 验证内容 | 当前结果 |
|---|---|---|
| [`tools/verify_corpus.py`](tools/verify_corpus.py) | 520 个标准库模块：反编译 → **同版本解释器**重编译 → 结构化字节码签名对比，不一致再做归一化 AST 语义对比 | **520/520 语义等价**（398 签名级一致，零语法错误、零占位符） |
| [`tools/run_behavior.py`](tools/run_behavior.py) | 50 用例 × 13 解释器：原始与反编译代码同解释器运行，对比 stdout+返回码 | **516/516 = 100%** |
| [`tests/roundtrip.py`](tests/roundtrip.py) | fixture 矩阵：编译 → 反编译 → 重编译 → 严格字节码对比 | 49/54 严格一致（exceptions fixture 仅结构差，语义等价） |

分版本结果见 `tests/corpus/<version>/report.json`。除上述设施外，发布前还经
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

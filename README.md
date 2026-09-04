# pycdc-rs

用 Rust 编写的 Python 字节码反汇编器与反编译器，支持 **Python 2.0 – 3.15（dev）** 的 `.pyc` 文件，将其还原为可读的 `.py` 源码。

设计参考了 [Decompyle++ (pycdc)](https://github.com/zrax/pycdc)、[uncompyle6/decompyle3](https://github.com/rocky/python-decompyle3) 与 [xdis](https://github.com/rocky/python-xdis)，核心思想是：

- **版本差异全部数据化**：每个 Python 版本一张 opcode 配置表（JSON，由 `tools/gen_configs.py` 从 xdis 和 CPython `opcode` 模块生成，编译期嵌入二进制，也可用 `--opcodes` 从外部目录覆盖/扩展）。
- **解码层归一化**：指令宽度（变长 vs wordcode）、EXTENDED_ARG 链、CACHE 内联缓存、绝对/相对跳转、字节/指令字跳转单位等全部在 `bytecode.rs` 统一处理，上层反编译逻辑完全跨版本共享。
- **栈模拟 + 块栈** 反编译模型（pycdc 风格）：值栈构建表达式，块栈配合跳转目标区间恢复 if/elif/else、while、for、try、with 等控制流；针对 3.8+ 的旋转 while、3.12+ 的 COPY+条件跳转布尔链、3.12+ PEP 709 内联推导式、3.11+ 异常表驱动的 try/except、3.13+ SET_FUNCTION_ATTRIBUTE、3.14 的 CALL 槽位变化等新形态均有专门处理。
- **优雅降级**：无法识别的构造输出注释占位并在 stderr 提示 `WARNING: Decompyle incomplete`，绝不崩溃。

## 构建

```sh
cargo build --release
# 产物: target/release/pycdc (反编译) 与 target/release/pycdas (反汇编)
```

依赖仅 `serde` / `serde_json` / `thiserror`；`build.rs` 从 `configs/opcodes/*.json` 生成规范 opcode 枚举。

## 使用

```sh
# 反编译为源码
pycdc program.pyc > program.py

# 反汇编（含异常表、行号、嵌套 code object）
pycdas program.pyc

# 直接处理 marshal 数据（无 pyc 头），指定版本
pycdc -c -v 3.8 payload.marshal

# 使用外部 opcode 配置（如为新出的 Python 版本添加支持）
pycdc --opcodes ./my-configs program.pyc
```

## 测试

```sh
cargo test                    # 单元测试 + 集成测试（tests/pyc/ 内置 2.7–3.14 fixture）
python3 tests/roundtrip.py    # 多版本回归矩阵：编译 fixture -> 反编译 -> 重编译 -> 结构化字节码对比
```

`roundtrip.py` 需要本机存在多个 Python 解释器（默认探测 3.9–3.14，可用 uv 安装）。

## 更新版本配置

新版本 Python 发布后：

```sh
python3 tools/gen_configs.py --xdis /path/to/python-xdis   # 重新生成 configs/
cargo build                                                 # 重新嵌入
```

- 2.0–3.10、3.15 的表来自 xdis；3.11–3.14 由 `tools/dump_native.py` 在对应版本解释器中直接导出（含 CACHE 表）。
- `configs/magics.json` 为 magic number → 版本映射（约 380 项，含 alpha/beta 与 PyPy/GraalPy 等变体）。

## 支持状态（tests/roundtrip.py 矩阵，字节码级一致）

| fixture | 3.9 | 3.10 | 3.11 | 3.12 | 3.13 | 3.14 |
|---|---|---|---|---|---|---|
| basics（赋值/解包/控制流/切片/布尔链） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| comprehensions（列表/集合/字典/生成器/嵌套/多生成器） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| functions（默认值/kwonly/注解/lambda/装饰器/global/yield） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| fstrings（转换符/格式规格/嵌套） | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| classes | 部分 | 部分 | ✅ | ✅ | ✅ | 部分 |
| hello | 部分 | 部分 | ✅ | ✅ | ✅ | ✅ |
| exceptions / with / async | 可编译输出，结构部分还原 | | | | | |

在 pycdc 官方测试集（166 个 2.x/3.x `.pyc`）上：**0 个加载/反编译错误**，约 78% 输出无 incomplete 警告。

## 真实语料库验证（tests/corpus/）

用 pyenv/uv 安装的 **13 个历史版本解释器**（2.6.9、2.7.18、3.3.7、3.5.10、3.6.15、3.7.17、3.8.20、3.9.25、3.10.21、3.11.16、3.12.14、3.13.15、3.14.7）把各版本**自带标准库源码**编译成 `.pyc`，源码与 pyc 按版本目录存放，共 **520 个模块**。验证流程（`tools/verify_corpus.py`）：

1. `pycdc` 反编译每个 `.pyc`；
2. 用**同版本解释器**重新编译反编译输出；
3. 对比原始 pyc 与重编译 pyc 的**结构化字节码签名**（opname + argrepr，跳转目标归一为标签）；
4. 签名不一致时再用 `tools/ast_compare.py` 做**归一化 AST 语义对比**（同版本解释器执行；归一化：相邻 import 合并、global/nonlocal 提升、`while 1`≡`while True`、终结分支 else 展平、set/list(genexpr)≡推导式、数值常量折叠）。

判级：`PASS`（字节码签名一致）＞ `AST-PASS`（AST 语义等价，即用户验收标准"执行逻辑语义相等"）＞ `INCOMPLETE`（含占位标记）＞ `SIG-DIFF`（可编译但结构有差）＞ `SYNTAX-ERR`。

当前结果（520 模块）：

| 指标 | 数量 |
|---|---|
| PASS（字节码级一致） | 72（13.8%） |
| AST-PASS（语义等价） | 27 |
| **语义等价合计** | **99（19.0%）** |
| INCOMPLETE（可编译、含占位） | 13 |
| SIG-DIFF（可编译、结构有差） | 408 |
| SYNTAX-ERR | **0（所有输出都能在对应版本编译）** |

每个版本目录下的 `report.json` 保存逐模块判级与首个差异位置，便于聚类修复。

### 行为等价矩阵（`tools/run_behavior.py`，18 用例 × 13 解释器）

用例编译为 pyc → 反编译 → **用同一解释器分别运行原始与反编译代码**，比较 stdout+返回码：

| 版本 | 通过率 | 版本 | 通过率 |
|---|---|---|---|
| 2.6 | 12/12 | 3.9 | 16/16 |
| 2.7 | 13/13 | 3.10 | 17/17 |
| 3.3 | 13/13 | 3.11 | 17/17 |
| 3.5 | 13/13 | 3.12 | 17/17 |
| 3.6 | 14/14 | 3.13 | 17/17 |
| 3.7 | 14/14 | 3.14 | 17/17 |
| 3.8 | 16/16 | **合计** | **196/196 = 100%** |

（带 MIN/MAX_VERSION 门控的用例只在适用版本运行；用例源文件本身无法在
某解释器编译时记 N/A 并排除出分母。）

## 已知限制

- try/except：3.11+ 基于异常表重建；3.8–3.10 SETUP_* 时代链式结构（含 handler 内嵌套 try、函数尾 try/finally、成功路径语句排序）已按链式状态机还原，行为等价矩阵全绿，但罕见形态（多层嵌套 + else + finally 组合）仍可能退化为占位注释。
- `with a, b:` 多上下文输出为嵌套 with（语义等价）。
- match/case（3.10–3.14）：字面量/捕获/通配/or/序列（含 `*rest`）/映射（含 `**rest`）/类模式（位置+关键字）与 guard 均支持；or 臂在部分版本渲染为共享 body 的多个 case（语义等价）。
- Python 1.x 可加载 marshal，但未附带 opcode 表。
- PyPy/Jython/GraalPy 变体按对应 CPython 版本表尽力处理。

## 代码结构

```
src/
  version.rs    magic 表、版本模型、pyc 头布局规则
  pyc.rs        pyc 头解析（8/12/16 字节、PEP 552 hash-based）
  marshal.rs    全版本 marshal 反序列化（v0–v5、FLAG_REF、interned 表、各版本 code 布局）
  object.rs     PyObject 模型（含任意精度 Long）
  code.rs       归一化 CodeObject + 3.11+ 异常表解析
  linetable.rs  lnotab / 3.10 linetable / 3.11+ 位置表解码
  opcode.rs     配置加载（嵌入 + 外部覆盖）、规范 Op 枚举
  bytecode.rs   指令解码与跳转归一化、反汇编渲染
  disasm.rs     递归反汇编输出
  ast.rs        版本无关 AST
  decompiler.rs 栈模拟 + 块栈控制流恢复（核心）
  codegen.rs    AST → 源码（优先级/缩进/版本语法差异）
  loader.rs     CLI 共享加载逻辑
  bin/pycdas.rs 反汇编器入口
  main.rs       反编译器入口
configs/
  magics.json           magic → 版本
  opcodes/python_*.json 每版本 opcode/跳转/参数类别/CACHE 表
tools/
  gen_configs.py        配置生成器（xdis + 原生解释器导出）
  dump_native.py        3.11+ 原生导出脚本
  build_corpus.py       单版本语料构建（2.6 兼容）
  build_corpus_all.py   全版本语料构建驱动
  verify_corpus.py      语料验证（反编译→重编译→签名/AST 对比）
  sig_dump.py           结构化字节码签名导出（目标版本解释器执行）
  ast_compare.py        归一化 AST 语义对比（2.6+ 兼容）
tests/
  roundtrip.py          多版本编译-反编译-重编译对比矩阵
  integration.rs        Rust 集成测试（内置 fixture）
  pyc/                  提交的 2.7–3.14 测试 pyc
  fixtures/             测试源码
```

## License

GPL-3.0-or-later（与所参考的 pycdc/xdis/uncompyle6 许可兼容）。

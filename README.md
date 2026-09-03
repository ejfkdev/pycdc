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

## 已知限制

- try/except 的 3.8–3.10 SETUP_* 时代结构与 bare `except:` 还原不完整；3.11+ 基于异常表重建，主体正确。
- `with a, b:` 多上下文输出为嵌套 with（语义等价）。
- match/case（3.10+）暂不支持（输出占位注释）。
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
tests/
  roundtrip.py          多版本编译-反编译-重编译对比矩阵
  integration.rs        Rust 集成测试（内置 fixture）
  pyc/                  提交的 2.7–3.14 测试 pyc
  fixtures/             测试源码
```

## License

GPL-3.0-or-later（与所参考的 pycdc/xdis/uncompyle6 许可兼容）。

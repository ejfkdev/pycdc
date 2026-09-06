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

判级：`PASS`（字节码签名一致）＞ `AST-PASS`（AST 语义等价，即用户验收标准"执行逻辑语义相等"）＞ `INCOMPLETE`（可编译，但含占位标记或 decompilation-incomplete 警告）＞ `SIG-DIFF`（可编译、结构有差）＞ `SYNTAX-ERR`。

当前结果（520 模块）：

| 指标 | 数量 |
|---|---|
| PASS（字节码级一致） | 162（31.2%） |
| AST-PASS（语义等价） | 37 |
| **语义等价合计** | **199（38.3%）** |
| INCOMPLETE（可编译、含占位/警告） | 101 |
| SIG-DIFF（可编译、结构有差） | 220 |
| SYNTAX-ERR | **0（所有 520 个输出都能在对应版本编译）** |

> 注 1：`INCOMPLETE` 此前长期显示为 0 是 verify_corpus 的检测 bug——warned
> 判定在 stderr 里找的是源码内注释标记的文案（`Decompyle incomplete`），
> 而 CLI 的 stderr 文案是 `decompilation incomplete`，从未命中；带警告的
> 模块被静默判成 SIG-DIFF/AST-PASS。修复后为诚实重基线（INCOMPLETE 集中在
> 3.8–3.14 的 try/finally 与 match 族；2.6–3.7 全部干净）。
>
> 注 2：sig_dump 的 py2/3.0–3.3 路径此前对 code-object 常量输出原始 repr
> （含内存地址与构建路径），原 pyc 与重编译 pyc 该行**永不相等**——任何带
> 嵌套函数/类的 py2、3.3 模块被系统性挡在 PASS 之外。归一为 `<code 名>`
> （与 py3 路径一致，嵌套代码本就递归全量对比）后 14 个 AST-PASS 直升
> PASS（2.6 +4、2.7 +5、3.3 +5），零降级。

每个版本目录下的 `report.json` 保存逐模块判级与首个差异位置，便于聚类修复。

### 行为等价矩阵（`tools/run_behavior.py`，43 用例 × 13 解释器）

用例编译为 pyc → 反编译 → **用同一解释器分别运行原始与反编译代码**，比较 stdout+返回码：

| 版本 | 通过率 | 版本 | 通过率 |
|---|---|---|---|
| 2.6 | 26/26 | 3.9 | 36/36 |
| 2.7 | 27/27 | 3.10 | 38/38 |
| 3.3 | 28/28 | 3.11 | 41/41 |
| 3.5 | 30/30 | 3.12 | 42/42 |
| 3.6 | 31/31 | 3.13 | 42/42 |
| 3.7 | 31/31 | 3.14 | 42/42 |
| 3.8 | 36/36 | **合计** | **450/450 = 100%** |

（带 MIN/MAX_VERSION 门控的用例只在适用版本运行；用例源文件本身无法在
某解释器编译时记 N/A 并排除出分母。）

## 已知限制

- try/except：3.11+ 基于异常表重建（含 except*、嵌套链、handler 内 continue/return、
  循环内 inline finally 副本裁剪）；3.8–3.10 SETUP_* 时代链式结构（含 handler 内嵌套
  try、函数尾 try/finally、成功路径语句排序、循环体整体为链的延迟折叠）已按链式状态机
  还原。多 handler 链含尾随裸 `except:`（`except E: ... except: ...`）已正确归位（atexit/
  _dummy_thread 的裸 except 体不再被提升到外层）。3.11+ 裸 `except:` 不再误判为 `finally:`
  （PUSH_EXC_INFO→POP_TOP 形状分类 + 无类型子句解析；except* 链的失配跳转 POP_TOP 清理
  已用 eg_chain 门控区分）；3.9/3.10 以裸 `RAISE_VARARGS` 收尾的 handler（`except: ...
  raise`）经延迟折叠正确闭合，不再吞掉后续 else/finally 区（aifc.__init__ 修复）。生成器
  代码对象中 yield 被编译器死代码消除的空生成器惯用法（`while False: yield None`，如
  _collections_abc.__iter__）在后处理阶段合成还原。已知缺口：2.x/3.5–3.10 中「except 分支
  内 continue + 同 try 带 finally + 位于循环内」的组合可能丢失循环嵌套结构；裸 except 归位
  时循环内 handler 尾可能多出一个语义等价的 `continue`。3.11+ 模块级连续
  sibling try（import-guard 形状）已不再误嵌套/幻影 else 吞并（异常表覆盖判别 +
  backward-merge 限定在本链 [handler, chain_extent) 内）；已知残留：内联嵌套
  try（try 体或 handler 体内再套 try，contextlib.__exit__ 形状）仍可能平铺化
  并留下 `unrecovered try/except structure` 占位。3.11+ 函数尾 try/except/else
  的隐式 `return None` 下沉副本（成功路径+末子句各一份）已识别并还原为标准
  else 形（chunk.__init__ 族）；窄化保护区把 try 体尾 `return` 排在 body_end
  之外的形状已折回体内（chunk.skip 3.11/3.12 → PASS）；handler 出口以回跳恢复
  主流程不再误标 incomplete。残留：恒异常链（`except: ...; raise`）收尾的 then
  臂终结 return 保持在分支级（aifc 形，重编译形状忠实但 else 臂平铺）。
- `with a, b:` 多上下文输出为嵌套 with（语义等价）。
- match/case（3.10–3.14）：字面量/捕获/通配/or/序列（含 `*rest`、字面量元素）/映射
  （含值字面量模式与 `**rest`）/类模式（位置+关键字+字面量子模式，含唯一非通配 case 的
  无 subject-COPY 形状）/singleton（True/False/None）与 guard 均支持；循环内 match（case
  体以 JUMP_BACKWARD 回到循环顶、尾随 `case _:` 位于失败目标）已还原；or 臂在部分版本
  渲染为共享 body 的多个 case（语义等价）。已知缺口：3.10 的旧式逐属性提取
  （BINARY_SUBSCR+ROT 栈序）、模式槽位内递归嵌套（如 mapping 值内嵌序列/类模式）、
  非字面量模式间的 or 展开（序列|序列、类|类，含共享捕获绑定）、循环内「最后一个 case
  用 PJIF_TRUE 跳 body + 失败 JUMP_BACKWARD」的倒置形状（如 `case 2: return`）会漏判为
  通配/条件残桩（行为多数仍等价）。
- 3.14 PEP 649 注解：函数/方法级 `__annotate__` 经 LOAD_FROM_DICT_OR_GLOBALS 重建为签名
  注解（类作用域注解如 `Self`/`ast.AST` 已正确解析）。已知缺口：模块/类级**条件**注解
  （`if False:`/TYPE_CHECKING 块内的纯注解语句，经 `__conditional_annotations__` 门控）
  仍以 `__annotate__`/`__conditional_annotations__` 伪函数形式输出而非还原为注解语句。
- PEP 750 模板字符串（3.14+ t-string，`BUILD_TEMPLATE`）不支持（语料中仅 annotationlib
  的 `type(t"")` 一处）；该 opcode 处输出 `# UNIMPLEMENTED` 占位。
- else 子句：`try/except/else` 与 `if/else` 的 else 体被提升到外层（丢失 `else:` 关联）的
  一族根因已修复，覆盖三种布局：①3.11+ handler 内联（else 体以 JUMP_FORWARD 跳到 merge）；
  ②legacy（≤3.10）else 体含嵌套 try/def/class（块结构化 flush 顺序 + else 区边界路由）；
  ③3.12+ handler 外联（handler 排在 try 后代码之后、以 BACKWARD 跳回 merge，else 体直接
  流入 merge 无前跳定界——用 handler 回跳目标推断 merge，并以「最后一个异常表分片」排除
  3.12 内联推导式把 try 体拆成多分片时的误判）。_bootlocale/copy/_compat_pickle/abc 等
  已达 PASS 或正确嵌套。残留：少数模块（_weakrefset/copy/copyreg 3.3）仅剩嵌套空 orelse
  的层次差异（`orelse=[]` 位置不同），非 else 体丢失。
- PEP 695 类型参数语法（3.12+ `type X = ...`、`def f[T](...)`、`class C[T]`）不支持。
- 异步：async def/await/async for/async with（含嵌套与多上下文）支持；已知缺口：
  内联 async 推导式、async 生成器 asend/athrow 协议、3.7 SETUP_EXCEPT 守卫式
  async-for 的 break+else 组合。
- 推导式元素中的三元表达式（`[a if c else b for ...]`）在部分旧版本可能错位。
- 链式比较（`a == b == c`）：值位、if 条件的 and 形（3.8–3.14，3.12+ 经 SCC 回退）、
  or 形（`if 链 or x[ or y]:`）与 **链 or 链**（`(a==b==c) or (d==e==f)`，含 3.8–3.10
  小块复制布局与 py2 值形 JFOP/JTFOP 短路）、**否定形**（`if not (a<b<=c): raise/return`，
  两种编译器布局：3.10/3.12 尾部复制 body 进 else 路、3.8/3.9/3.11/3.13/3.14 清理蹦床
  共享 body）、elif 上下文、切片操作数（含 3.14 const-slice 的 marshal 引用序修复）
  均已支持（b23_boolchain 13/13 全绿）。
- py2：`raise T, I[, B]` 原生渲染（忠实可重编译，不再重写为调用形）；py2.6
  函数级内联列表推导（`_[N]` FAST 累加器）已支持；「if 内嵌 if + 同级 elif +
  尾部悬挂 return」的深嵌套形状可能丢失后续分支。
- 2.7–3.9 已知缺口：elif 臂内含无 else 的嵌套 if 且其后还有 elif 臂时
  （`elif A: (if B: X) elif C: Y`），编译器把嵌套 if 的假路径 jump-thread
  到下一 elif 标签，三个同标签条件跳被 and-链合并、第二臂体丢失（行为破坏；
  3.10+ 已修复，见 v310_elifnest 用例）。
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

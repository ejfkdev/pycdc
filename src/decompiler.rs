//! Bytecode -> AST decompiler.
//!
//! Strategy (pycdc-inspired, fully normalized):
//! * the instruction stream is pre-decoded by `bytecode::decode_instructions`,
//!   so this module never deals with wordcode/EXTENDED_ARG/CACHE/jump-unit
//!   differences — only canonical `Op` values and absolute byte targets
//! * a simulated value stack builds expressions; a block stack builds
//!   statements and control flow (if/while/for/try/with) from jump-target
//!   arithmetic
//! * anything unhandled degrades gracefully into `Stmt::Unimplemented` and
//!   sets `clean = false`, which the CLI reports as a warning comment

use std::collections::{HashMap, HashSet};
use std::rc::Rc;

use crate::ast::*;
use crate::bytecode::{binary_op_name, compare_op_index, Instruction};
use crate::code::CodeObject;
use crate::object::{ObjectRef, PyObject};
use crate::opcode::{table_for, OpcodeTable};
use crate::version::PythonVersion;

pub struct Decompiled {
    pub body: Vec<Stmt>,
    /// False when at least one construct could not be fully recovered.
    pub clean: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BlockType {
    Main,
    If,
    Else,
    Try,
    #[allow(dead_code)]
    TryElse,
    Except,
    Finally,
    While,
    WhileElse,
    For,
    ForElse,
    With,
    /// try/finally container (SETUP_FINALLY era and 3.11+ exception table)
    Container,
}

#[derive(Debug, Clone)]
struct Block {
    kind: BlockType,
    /// First byte offset covered by this block.
    #[allow(dead_code)]
    start: usize,
    /// Region end (exclusive); the block is closed when the stream reaches it.
    end: usize,
    stmts: Vec<Stmt>,
    cond: Option<ExprRef>,
    /// for loops
    target: Option<ExprRef>,
    iter: Option<ExprRef>,
    is_async: bool,
    /// except blocks
    handler_type: Option<ExprRef>,
    handler_name: Option<ExprRef>,
    /// if blocks: end of the else branch (set by the closing JUMP_FORWARD)
    else_end: Option<usize>,
    /// loops: end of the else branch
    loop_else_end: Option<usize>,
    /// try blocks: where the finally handler begins
    finally_target: Option<usize>,
    /// with blocks: the context item
    with_item: Option<WithItem>,
    /// whether the loop/if condition has been filled in
    cond_set: bool,
    /// for rotated 3.8+ while loops: end offset of the cond jump instr
    cond_end: usize,
    /// stack depth when the block was created (value-flow merge detection)
    stack_depth: usize,
    /// block opened by COPY + cond jump: closing merges stack values into
    /// BoolOp (and/or chains) or chained comparisons
    value_merge: Option<BoolOpKind>,
    /// SETUP_LOOP-era For with for-else: the original SETUP_LOOP target
    /// (loop pop). The block end is lowered to the FOR_ITER exhaustion
    /// exit so the else region [exit, setup_end) collects separately.
    for_setup_end: Option<usize>,
    /// the branch region ended with a backward jump fused into the
    /// enclosing loop's back edge: an elif/else boundary follows here
    folded_exit: bool,
    /// this Else block is an elif continuation
    is_elif: bool,
    /// conditional jump polarity that opened this If block
    jump_if_true: bool,
    /// Some(or_form) when the block merges a JUMP_IF_*_OR_POP short circuit
    short_circuit: Option<bool>,
    /// 3.12+ chained-comparison link (COPY + PJIF + SWAP/POP else arm)
    chain_link: bool,
}

impl Block {
    fn new(kind: BlockType, start: usize, end: usize) -> Block {
        Block {
            kind,
            start,
            end,
            stmts: Vec::new(),
            cond: None,
            target: None,
            iter: None,
            is_async: false,
            handler_type: None,
            handler_name: None,
            else_end: None,
            loop_else_end: None,
            finally_target: None,
            with_item: None,
            cond_set: true,
            cond_end: usize::MAX,
            stack_depth: 0,
            value_merge: None,
            for_setup_end: None,
            folded_exit: false,
            is_elif: false,
            jump_if_true: false,
            short_circuit: None,
            chain_link: false,
        }
    }
}

/// A value on the simulated stack.
#[derive(Debug, Clone)]
enum Sv {
    E(ExprRef),
    /// NULL marker pushed before callables (3.11+)
    Null,
    /// IMPORT_NAME result awaiting IMPORT_FROM / IMPORT_STAR / store
    ImportModule {
        level: u32,
        module: String,
        /// pending `from x import (a, b)` name list being built
        fromlist: Option<ExprRef>,
    },
    /// One name of a pending `from x import a, b` (IMPORT_FROM result)
    ImportFrom {
        level: u32,
        module: String,
        name: String,
    },
}

/// A PEP 709 inline comprehension being recognized (3.12+). The whole
/// instruction region is pre-scanned, so `end` (the END_FOR offset of the
/// outermost loop) and all FOR_ITER offsets are known up front.
#[derive(Debug, Clone)]
struct InlineComp {
    kind: CompKind,
    /// offset where the comprehension's prologue begins (py2 nesting)
    start: usize,
    #[allow(dead_code)]
    iter: ExprRef,
    /// offset just past the outermost END_FOR
    end: usize,
    for_iter_offsets: Vec<usize>,
    gens: Vec<Comprehension>,
    /// generator currently being filled by the main loop
    cur: Option<PartialGen>,
    elt: Option<ExprRef>,
    key: Option<ExprRef>,
    cleared_vars: Vec<String>,
    target_seen: bool,
}

/// Pre-3.11 try statement collected across its handler chain.
#[derive(Debug, Clone)]
struct LegacyTry {
    body: Vec<Stmt>,
    handlers: Vec<ExceptHandler>,
    orelse: Vec<Stmt>,
    finalbody: Vec<Stmt>,
    /// offset where the handler chain begins
    handler_start: usize,
    has_finally: bool,
    /// when the try body ends with a forward jump over the handler chain,
    /// the else region spans [else_start, else_stop)
    else_start: Option<usize>,
    else_stop: usize,
    /// handler chain fully parsed (END_FINALLY passed); emit on next jump
    chain_done: bool,
}

#[derive(Debug, Clone)]
struct LegacyHandler {
    type_: Option<ExprRef>,
    name: Option<ExprRef>,
    body: Vec<Stmt>,
    /// block-stack depth when the handler opened; statements only collect
    /// into `body` when no handler-internal block (If/While/...) is open
    block_depth: usize,
    /// 3.9 puts POP_EXCEPT before a terminating handler body; the fold is
    /// deferred until the body's RETURN/jump-out
    pop_seen: bool,
}

/// Saved outer legacy-chain state while a nested chain (a try inside an
/// except body, <=3.7) parses in the single legacy_try/legacy_handler slots
struct LegacyNest {
    outer_try: Option<LegacyTry>,
    outer_handler: Option<LegacyHandler>,
    outer_handler_end: Option<usize>,
    outer_prelude: bool,
    depth: usize,
    /// region [start, end) of the nested handler chain the body-end jump
    /// flew over (parsed by sub-walk): a handler-exit jump inside it that
    /// lands on the OUTER else_start retracts the outer else region
    skipped_chain: Option<(usize, usize)>,
}

/// Reconstructed try-statement region (3.11+ exception-table driven).
#[derive(Debug, Clone)]
struct TryCtx {
    /// first protected offset
    start: usize,
    /// end of the try body (first except/else boundary)
    body_end: usize,
    /// end of the whole protected region (else end / finally start)
    region_end: usize,
    except_handler: Option<usize>,
    finally_handler: Option<usize>,
}

impl TryCtx {
    fn cover_end(&self) -> usize {
        self.region_end
    }
}

#[derive(Debug, Clone)]
struct PartialGen {
    target: Option<ExprRef>,
    iter: ExprRef,
    ifs: Vec<ExprRef>,
}

/// Per-unpack-frame collected targets (inner Vec per open frame).
struct FrameTargets(Vec<Vec<(ExprRef, bool)>>);

struct Ctx<'a> {
    code: &'a CodeObject,
    table: &'a OpcodeTable,
    version: PythonVersion,
    instrs: Vec<Instruction>,
    idx_of: HashMap<usize, usize>,
    targets: HashSet<usize>,
    stack: Vec<Sv>,
    blocks: Vec<Block>,
    clean: bool,
    /// unpack frames (remaining, count, star_at, value)
    unpack_frames: Vec<(usize, usize, Option<usize>, ExprRef)>,
    /// next STORE_* is a comprehension loop target: consumes no stack value
    comp_target_store: bool,
    /// GET_AWAITABLE seen: the next YIELD_VALUE is an `await`
    await_mode: bool,
    /// context expression stashed by BEFORE_ASYNC_WITH (<=3.9)
    pending_async_with_ctx: Option<ExprRef>,
    /// the END_SEND after an await yield must not pop
    skip_end_send: bool,
    /// the with-exit recognizer just swallowed an async-with __aexit__
    /// call: the following GET_AWAITABLE..YIELD_VALUE protocol has no
    /// awaitable left and must be dropped without a stack underflow
    with_exit_await_drop: bool,
    /// <=3.10 SETUP_WITH/SETUP_ASYNC_WITH handler starts: the normal-exit
    /// JUMP_FORWARD right before one must skip the whole handler region
    with_handler_starts: std::collections::HashSet<usize>,
    /// 3.5-3.7 async-for: the per-iteration StopAsyncIteration guard
    /// (SETUP_EXCEPT handler start, unwind tail start, loop exit offset)
    async_for_guard: Option<(usize, usize, usize)>,
    /// <=3.7 nested try inside an open legacy handler body: saved outer
    /// chain states (innermost last) while nested chains parse in the
    /// single slots
    legacy_nest: Vec<LegacyNest>,
    /// >0 while a skipped nested chain parses in a region sub-walk: the
    /// py2 implicit-as store there binds an extra exception placeholder
    /// instead of capturing the clause name
    legacy_nest_depth: usize,
    /// 2.6 compiler synthetic temps (`_[N]`): with-as targets and inline
    /// comprehension accumulators stash/reload through them
    py26_temps: HashMap<String, Sv>,
    /// completed py2 inline comprehension regions [start, end]: a nested
    /// comprehension's iterable can be one, and the outer detection scan
    /// must hop over it
    completed_comp_regions: Vec<(usize, usize)>,
    last_py26_temp: Option<String>,
    /// 3.3-3.7 swallowed `as`-cleanup wrappers: (SETUP offset, cleanup
    /// END_FINALLY offset) — that END_FINALLY must not be mistaken for
    /// the chain end, and the setup's normal-exit POP_BLOCK belongs to
    /// the wrapper, not the enclosing try
    as_cleanup_wrappers: Vec<(usize, usize)>,
    /// a py2 sub-walk bound `sys.exc_info()[1]` — ensure `import sys`
    used_exc_info: bool,
    pending_gen_code: Option<std::rc::Rc<crate::code::CodeObject>>,
    recent_code_const: Option<std::rc::Rc<crate::code::CodeObject>>,
    /// pending kw names for the next CALL (3.11/3.12 KW_NAMES)
    last_kw_names: Vec<Option<String>>,
    /// `global`/`nonlocal` collection (emitted at top of function bodies)
    globals: Vec<String>,
    nonlocals: Vec<String>,
    exc_entries: Vec<crate::code::ExceptionEntry>,
    /// pre-retain exception table: chain-extent closure needs entries the
    /// cleanup filter dropped (chain-internal redirects)
    raw_exc_entries: Vec<crate::code::ExceptionEntry>,
    /// reconstructed try regions keyed by body start offset (3.11+)
    try_ctxs: HashMap<usize, TryCtx>,
    /// first offset of out-of-line handler code (main pass stops here)
    handler_zone: Option<usize>,
    chain_heads: std::collections::HashSet<usize>,
    /// with-body regions from the exception table (3.11+): start -> end
    with_regions: HashMap<usize, usize>,
    /// try context whose body block is currently open
    active_try: Option<TryCtx>,
    /// try context awaiting else/finally emission
    pending_try_ctx: Option<TryCtx>,
    /// finally body of the enclosing try in a nested-chain wrap, consumed
    /// by the next emit_try_tail
    pending_nested_finally: Option<Vec<Stmt>>,
    /// inner try's clauses in a nested-chain wrap, consumed by the next
    /// emit_try_tail (which nests the region body inside an inner Try)
    nested_inner_handlers: Option<Vec<ExceptHandler>>,
    /// pre-3.11 try awaiting its out-of-line handler chain
    legacy_try: Option<LegacyTry>,
    /// pre-3.11 except clause being collected
    legacy_handler: Option<LegacyHandler>,
    /// where the current legacy handler body ends (mismatch jump target)
    legacy_handler_end: Option<usize>,
    /// next STORE_* is the `except ... as name` binding (swallow it)
    legacy_handler_name_store: bool,
    /// next STORE_*/DELETE_* is the implicit handler-name cleanup
    legacy_handler_cleanup: bool,
    /// inside the exception-bookkeeping prelude of a legacy handler
    in_handler_prelude: bool,

    // side tables used while blocks are open
    pending_then: Vec<Vec<Stmt>>,
    pending_handlers: Vec<ExceptHandler>,
    pending_try_body: Vec<Vec<Stmt>>,
    pending_try_handlers: Vec<Vec<ExceptHandler>>,
    pending_loop: Vec<(Option<ExprRef>, Option<ExprRef>, Option<ExprRef>, Vec<Stmt>, bool)>,
    pending_with: Vec<Vec<WithItem>>,
    pending_try_orelse: Vec<Vec<Stmt>>,
    with_exits: usize,
    pending_print: Vec<ExprRef>,
    pending_print_dest: Option<ExprRef>,
    unpack_targets: FrameTargets,
    awaiting_for_target: bool,
    #[allow(dead_code)]
    pending_if_stmts: Vec<Vec<Stmt>>,
    cur_offset: usize,
    cur_next: usize,
    prev_op: Option<Op>,
    prev_op_at_exec: Option<Op>,
    /// instruction offsets to skip (false-path cleanup of value merges)
    skip_until: Option<usize>,
    /// loop top of a loop that saw BREAK_LOOP: dead back edges after the
    /// break (<=3.7 padding) must not mark the output unclean
    broken_loop_top: Option<usize>,
    /// py2 `if` statement: offset of the else-branch POP_TOP absorbed by
    /// the JUMP_IF_FALSE/TRUE rewrite (it must not pop a real value)
    py2_else_pop_at: Option<usize>,
    /// loop tops whose loop already closed via their back edge: later dead
    /// back edges to the same top are padding, not `continue`
    closed_loop_tops: Vec<usize>,
    /// 3.8+ unconditional `while True` loops found by the back-edge
    /// prescan: loop top -> back-edge instruction end (loop region end)
    while_true_loops: Vec<(usize, usize)>,
    /// `except E as name` cleanup (`name = None; del name`) that follows a
    /// folded handler: the None-store is held until the matching delete
    /// confirms it (a real `x = None` statement must not be swallowed)
    pending_as_cleanup: Option<String>,
    held_cleanup_store: Option<(ExprRef, ExprRef)>,
    /// enclosing class names for private-name (PEP 8 mangling) restoration
    class_scope: Vec<String>,
    /// PEP 709 inline comprehension state (3.12+ listcomp/setcomp/dictcomp)
    inline_comp: Option<InlineComp>,
    inline_comp_stack: Vec<InlineComp>,
    /// variables whose post-comprehension restore store must be swallowed
    pending_restore_vars: Vec<String>,
    cur_line: Option<u32>,
    pending_stores: Vec<(ExprRef, ExprRef)>,
    last_store_line: Option<u32>,
    /// offset where the current store group began
    group_start: usize,
    /// offset of the last statement flush (group scan window start)
    last_flush_offset: usize,
    flushing: bool,
    pending_aug: Option<(ExprRef, BinaryOp)>,
    pending_decorators: Vec<ExprRef>,
    pending_class_decorators: Vec<ExprRef>,
    pending_py2_class: Option<(ExprRef, ExprRef, ExprRef)>,
    /// collected `from ... import` names while building one statement
    import_names: Vec<(String, Option<String>)>,
    import_module: Option<(u32, String)>,
}

pub fn decompile(code: &CodeObject, version: PythonVersion) -> crate::Result<Decompiled> {
    decompile_in_scope(code, version, &[])
}

/// Decompile with an explicit enclosing-class scope stack (for private
/// name unmangling).
pub fn decompile_in_scope(
    code: &CodeObject,
    version: PythonVersion,
    class_scope: &[String],
) -> crate::Result<Decompiled> {
    let table = table_for(version)?;
    let instrs = crate::bytecode::decode_instructions(code, table, version);
    let mut idx_of = HashMap::new();
    let mut targets = HashSet::new();
    for (i, inst) in instrs.iter().enumerate() {
        idx_of.insert(inst.offset, i);
        idx_of.insert(inst.end(), i);
        if let Some(t) = inst.target {
            targets.insert(t);
        }
    }
    let mut exc_entries = code.exception_entries().to_vec();
    let raw_exc_entries = exc_entries.clone();
    // Filter out entries whose handler is pure interpreter cleanup
    // (generators, inline comprehensions, with statements): these do not
    // correspond to a source-level try/finally.
    {
        let cleanup_ops = |op: Op| {
            matches!(
                op,
                Op::SWAP
                    | Op::COPY
                    | Op::POP_TOP
                    | Op::RERAISE
                    | Op::CALL_INTRINSIC_1
                    | Op::CALL_INTRINSIC_2
                    | Op::END_ASYNC_FOR
                    | Op::CLEANUP_THROW
                    | Op::PREP_RERAISE_STAR
                    | Op::POP_EXCEPT
                    | Op::POP_BLOCK
                    | Op::NOP
                    | Op::CACHE
                    | Op::RETURN_VALUE
                    | Op::RETURN_CONST
                    | Op::LOAD_CONST
                    | Op::STORE_FAST
                    | Op::STORE_NAME
                    | Op::STORE_DEREF
            )
        };
        exc_entries.retain(|e| {
            let Some(&hi) = idx_of.get(&e.target) else {
                return true;
            };
            let mut saw_reraise = false;
            for ins in instrs.iter().skip(hi).take(14) {
                if matches!(ins.op, Op::RERAISE) {
                    saw_reraise = true;
                }
                if !cleanup_ops(ins.op) {
                    return true; // user code in handler -> real try
                }
                if ins.is_backward && ins.target.unwrap_or(0) <= e.start {
                    break;
                }
            }
            !saw_reraise
        });
    }

    // classify exception-table targets: handlers starting with PUSH_EXC_INFO
    // are out-of-line handler regions; CHECK_EXC_MATCH inside => except
    // dispatch, otherwise => finally handler.
    // target -> handler kind: true = except dispatch, false = finally.
    // `with` cleanup handlers (WITH_EXCEPT_START) are tracked separately.
    let mut handler_kind: HashMap<usize, bool> = HashMap::new();
    let mut with_regions: HashMap<usize, usize> = HashMap::new(); // body start -> end
    let mut all_handler_targets: Vec<usize> = Vec::new();
    for e in &exc_entries {
        if let Some(&hi) = idx_of.get(&e.target) {
            // anchor classification at the handler head: a 40-insn window
            // from a CLEANUP_THROW/END_ASYNC_FOR trampoline can run through
            // main flow into a LATER async-with's WITH_EXCEPT_START,
            // misclassifying the stub and dragging handler_zone forward
            // (truncating the walk). Real with-handlers always start with
            // PUSH_EXC_INFO.
            if instrs.get(hi).map(|x| x.op) != Some(Op::PUSH_EXC_INFO) {
                continue;
            }
            let window: Vec<_> = instrs.iter().skip(hi).take(40).collect();
            if window.iter().any(|x| x.op == Op::WITH_EXCEPT_START) {
                with_regions.insert(e.start, e.end);
                all_handler_targets.push(e.target);
                continue;
            }
            let is_except = window.iter().any(|x| x.op == Op::CHECK_EXC_MATCH);
            handler_kind.insert(e.target, is_except);
            all_handler_targets.push(e.target);
        }
    }
    // handler zone: everything from the first handler target that covers
    // MAIN-FLOW code to the end is out-of-line handler code. Chains that
    // protect only handler-zone code (nested tries inside an except body)
    // must NOT define the zone — the main walk has to reach the outer
    // chain's dispatch, and nested chains are folded by the handler-body
    // sub-walks instead.
    // handler zone: everything from the first classified handler target to
    // the end of the code is out-of-line handler/cleanup code
    let handler_zone = all_handler_targets.iter().min().copied();
    // chain heads: out-of-line dispatch regions are parsed on demand (by
    // emit_try_tail / nested wraps) — the main walk skips them wherever
    // they sit, since protected bodies may FOLLOW their chain (a whole-
    // function try whose handler was laid out before the body)
    let chain_heads: std::collections::HashSet<usize> =
        all_handler_targets.iter().copied().collect();
    let mut ctx = Ctx {
        code,
        table,
        version,
        instrs,
        idx_of,
        targets,
        stack: Vec::new(),
        blocks: vec![Block::new(BlockType::Main, 0, usize::MAX)],
        clean: true,
        unpack_frames: Vec::new(),
        comp_target_store: false,
        await_mode: false,
        pending_async_with_ctx: None,
        skip_end_send: false,
        with_exit_await_drop: false,
        with_handler_starts: std::collections::HashSet::new(),
        async_for_guard: None,
        legacy_nest: Vec::new(),
        legacy_nest_depth: 0,
        py26_temps: HashMap::new(),
        completed_comp_regions: Vec::new(),
        last_py26_temp: None,
        as_cleanup_wrappers: Vec::new(),
        used_exc_info: false,
        pending_gen_code: None,
        recent_code_const: None,
        last_kw_names: Vec::new(),
        globals: Vec::new(),
        nonlocals: Vec::new(),
        exc_entries: exc_entries.clone(),
        raw_exc_entries,
        try_ctxs: HashMap::new(),
        handler_zone,
        chain_heads,
        with_regions: with_regions.clone(),
        active_try: None,
        pending_try_ctx: None,
        pending_nested_finally: None,
        nested_inner_handlers: None,
        legacy_try: None,
        legacy_handler: None,
        legacy_handler_end: None,
        legacy_handler_name_store: false,
        legacy_handler_cleanup: false,
        in_handler_prelude: false,
        pending_then: Vec::new(),
        pending_handlers: Vec::new(),
        pending_try_body: Vec::new(),
        pending_try_handlers: Vec::new(),
        pending_loop: Vec::new(),
        pending_with: Vec::new(),
        pending_try_orelse: Vec::new(),
        with_exits: 0,
        pending_print: Vec::new(),
        pending_print_dest: None,
        unpack_targets: FrameTargets(Vec::new()),
        awaiting_for_target: false,
        pending_if_stmts: Vec::new(),
        cur_offset: 0,
        cur_next: 0,
        prev_op: None,
        prev_op_at_exec: None,
        skip_until: None,
        broken_loop_top: None,
        py2_else_pop_at: None,
        closed_loop_tops: Vec::new(),
        while_true_loops: Vec::new(),
        pending_as_cleanup: None,
        held_cleanup_store: None,
        class_scope: class_scope.to_vec(),
        inline_comp: None,
        inline_comp_stack: Vec::new(),
        pending_restore_vars: Vec::new(),
        cur_line: None,
        pending_stores: Vec::new(),
        last_store_line: None,
        group_start: 0,
        last_flush_offset: 0,
        flushing: false,
        pending_aug: None,
        pending_decorators: Vec::new(),
        pending_class_decorators: Vec::new(),
        pending_py2_class: None,
        import_names: Vec::new(),
        import_module: None,
    };

    // chained try-region grouping (3.11+): entries in the main flow, ordered
    // by start; an entry starting where the current region ends extends it
    if version.at_least(3, 11) {
        // entries inside the handler zone belong to NESTED tries living in
        // out-of-line handler bodies — the region sub-walks consult the
        // same ctx map, so include them (the main walk never reaches the
        // zone; pure-cleanup handlers were already dropped by the retain)
        let _ = handler_zone;
        let mut main_entries: Vec<_> = exc_entries
            .iter()
            .filter(|e| handler_kind.contains_key(&e.target))
            .collect();
        main_entries.sort_by_key(|e| e.start);
        let mut regions: Vec<TryCtx> = Vec::new();
        // 3.12+ resume protocols split a protected range in two: the
        // YIELD_VALUE suspension point is covered by an entry targeting a
        // CLEANUP_THROW trampoline (dropped from classification), so the
        // two halves of ONE source-level try arrive as separate entries
        // with the same handler — bridge the protocol-only gap instead of
        // opening a duplicate try
        let protocol_only = |from: usize, to: usize| -> bool {
            match (ctx.idx_of.get(&from), ctx.idx_of.get(&to)) {
                (Some(&fi), Some(&ti)) => ctx.instrs[fi..ti].iter().all(|x| {
                    matches!(
                        x.op,
                        Op::YIELD_VALUE
                            | Op::RESUME
                            | Op::RESUME_CHECK
                            | Op::SEND
                            | Op::END_SEND
                            | Op::CLEANUP_THROW
                            | Op::JUMP_BACKWARD_NO_INTERRUPT
                            | Op::LOAD_CONST
                            | Op::NOP
                            | Op::NOT_TAKEN
                    )
                }),
                _ => false,
            }
        };
        for e in main_entries {
            let is_exc = handler_kind[&e.target];
            let mut bridged = false;
            let extends = regions
                .last()
                .map(|r| {
                    if r.cover_end() == e.start {
                        return true;
                    }
                    let same_handler = if is_exc {
                        r.except_handler == Some(e.target)
                    } else {
                        r.finally_handler == Some(e.target)
                    };
                    let b = same_handler
                        && e.start > r.cover_end()
                        && protocol_only(r.cover_end(), e.start);
                    if b {
                        bridged = true;
                    }
                    b
                })
                .unwrap_or(false);
            if extends {
                let r = regions.last_mut().unwrap();
                if is_exc {
                    r.except_handler.get_or_insert(e.target);
                    if bridged {
                        // the protocol gap is part of the try body (the
                        // await statement finishes after the suspension
                        // point) — extend the body, not an else region
                        r.body_end = e.end;
                        r.region_end = e.end;
                    }
                } else {
                    r.finally_handler.get_or_insert(e.target);
                    r.region_end = e.end;
                }
            } else {
                let mut r = TryCtx {
                    start: e.start,
                    body_end: e.end,
                    region_end: e.end,
                    except_handler: None,
                    finally_handler: None,
                };
                if is_exc {
                    r.except_handler = Some(e.target);
                } else {
                    r.finally_handler = Some(e.target);
                }
                regions.push(r);
            }
        }
        // dedupe: keep regions with at least a body
        for r in regions {
            ctx.try_ctxs.insert(r.start, r);
        }
    }

    ctx.run();

    // a legacy try whose emission stayed deferred for the else region:
    // the walk can end (function-tail return inside the else region)
    // before the emission point — flush it now
    while !ctx.legacy_nest.is_empty() {
        // fold a nested handler still open at walk end (terminating return)
        if let Some(h) = ctx.legacy_handler.take() {
            if let Some(lt) = ctx.legacy_try.as_mut() {
                lt.handlers.push(crate::ast::ExceptHandler {
                    type_: h.type_,
                    name: h.name,
                    body: h.body,
                });
            }
        }
        let nested = ctx.legacy_try.take();
        ctx.restore_legacy_nest();
        if let Some(l) = nested {
            if !l.handlers.is_empty() {
                let mut orelse = l.orelse;
                if matches!(orelse.last(), Some(Stmt::Return(None))) {
                    orelse.pop();
                }
                ctx.push_stmt(Stmt::Try {
                    body: l.body,
                    handlers: l.handlers,
                    orelse,
                    finalbody: l.finalbody,
                });
            }
        }
        // the restored outer handler was open when the nest began: if the
        // walk ended before its chain closed, fold it now
        if let Some(h) = ctx.legacy_handler.take() {
            if let Some(lt) = ctx.legacy_try.as_mut() {
                lt.handlers.push(crate::ast::ExceptHandler {
                    type_: h.type_,
                    name: h.name,
                    body: h.body,
                });
            }
        }
    }
    if ctx.used_exc_info {
        let has_sys = ctx.blocks.first().map_or(false, |b| {
            b.stmts.iter().any(|st| match st {
                Stmt::Import { names } => names.iter().any(|(m, _)| m == "sys"),
                _ => false,
            })
        });
        if !has_sys {
            if let Some(root) = ctx.blocks.first_mut() {
                root.stmts.insert(0, Stmt::Import { names: vec![("sys".to_string(), None)] });
            }
        }
    }
    if let Some(l) = ctx.legacy_try.take() {
        if !l.handlers.is_empty() || l.has_finally {
            let mut orelse = l.orelse;
            let mut finalbody = l.finalbody;
            // the implicit function epilogue `return None` is not an
            // else/finally clause
            if matches!(orelse.last(), Some(Stmt::Return(None))) {
                orelse.pop();
            }
            if matches!(finalbody.last(), Some(Stmt::Return(None))) {
                finalbody.pop();
            }
            ctx.flush_pending_stores();
            let try_stmt = Stmt::Try {
                body: l.body,
                handlers: l.handlers,
                orelse,
                finalbody,
            };
            // statements the walk pushed after the chain (the function
            // epilogue / trailing returns) chronologically FOLLOW the try
            // — insert it before them
            let top = ctx.blocks.last_mut().unwrap();
            let mut at = top.stmts.len();
            while at > 0 && matches!(top.stmts[at - 1], Stmt::Return(_)) {
                at -= 1;
            }
            top.stmts.insert(at, try_stmt);
        }
    }

    // Fold any blocks still open at EOF into statements.
    while ctx.blocks.len() > 1 {
        let pos = ctx.instrs.last().map(|i| i.end()).unwrap_or(0);
        // an open chained-comparison link at EOF: its else arm (the last
        // real execution path) yields the link's own condition value
        if let Some(top) = ctx.blocks.last() {
            if top.chain_link && top.stmts.is_empty() {
                if let Some(c) = top.cond.clone() {
                    ctx.blocks.pop();
                    ctx.push(c);
                    continue;
                }
            }
        }
        ctx.force_close_top(pos);
    }
    ctx.flush_stack();

    let mut root = ctx.blocks.remove(0);
    let mut body = std::mem::take(&mut root.stmts);

    // `global`/`nonlocal` declarations first (only meaningful in functions)
    if code.name != "<module>" {
        if !ctx.globals.is_empty() {
            body.insert(0, Stmt::Global(std::mem::take(&mut ctx.globals)));
        }
        if !ctx.nonlocals.is_empty() {
            body.insert(0, Stmt::Nonlocal(std::mem::take(&mut ctx.nonlocals)));
        }
    }

    Ok(Decompiled {
        body: postprocess_body(body, code),
        clean: ctx.clean,
    })
}

impl<'a> Ctx<'a> {
    fn run(&mut self) {
        self.prescan_while_true();
        let mut pc = 0usize;
        let mut past_chains = false;
        while pc < self.instrs.len() {
            let inst = self.instrs[pc];
            let pos = inst.offset;
            if self.chain_heads.contains(&pos) && inst.op == Op::PUSH_EXC_INFO {
                // out-of-line handler chain head: fold any Try block
                // ending here FIRST (its tail parses the chain), then
                // skip the whole chain region — the walk resumes after
                // it (protected body continuation, another chain, or
                // sunk post-try main flow)
                self.close_blocks_at(pos);
                let after = self.chain_extent(pos);
                self.skip_until = Some(after);
                past_chains = true;
            } else if let Some(zone) = self.handler_zone {
                // a protected body may legitimately START inside the zone
                // (its handler chain was laid out before it) — the main
                // walk must open the try there instead of breaking
                if pos >= zone && !past_chains && !self.try_ctxs.contains_key(&pos) {
                    break;
                }
            }
            if let Some(skip) = self.skip_until {
                if pos < skip {
                    pc += 1;
                    continue;
                }
                self.skip_until = None;
            }
            self.cur_offset = pos;
            self.cur_next = inst.end();
            if let Some(l) = inst.line {
                self.cur_line = Some(l);
            }
            if std::env::var("PYCDC_TRACE2").is_ok() {
                eprintln!("T2 {:>4} {:?} blocks={:?} skip={:?} lh={:?} lt={:?}", pos, inst.op,
                    self.blocks.iter().map(|b| format!("{:?}[{},{}]", b.kind, b.start, b.end)).collect::<Vec<_>>(),
                    self.skip_until,
                    self.legacy_handler.is_some(),
                    self.legacy_try.as_ref().map(|l| (l.handler_start, l.handlers.len(), l.else_start, l.chain_done)));
            }

            // py2 inline comprehension: region ends at the FOR_ITER exit
            if self.version.major == 2 {
                let end_hit = self
                    .inline_comp
                    .as_ref()
                    .map(|c| pos >= c.end && c.end != usize::MAX)
                    .unwrap_or(false);
                if end_hit {
                    // py2 FOR_ITER leaves the iterator on the stack at
                    // exit — one leftover per generator for multi-for
                    // comprehensions
                    let npops = self
                        .inline_comp
                        .as_ref()
                        .map(|c| {
                            if self.version.major == 2 {
                                c.for_iter_offsets.len().max(1)
                            } else {
                                1
                            }
                        })
                        .unwrap_or(1);
                    for _ in 0..npops {
                        self.pop();
                    }
                    self.finish_inline_comp();
                }
            }

            // 3.5-3.7 async-for: the per-iteration StopAsyncIteration
            // guard handler is loop machinery — never walk it; skip from
            // its head past the END_FINALLY into the loop body
            if self
                .async_for_guard
                .map_or(false, |(h, _, _)| h == pos && inst.op == Op::DUP_TOP)
            {
                if let Some(&hi) = self.idx_of.get(&pos) {
                    for ins in self.instrs[hi..].iter().take(10) {
                        if ins.op == Op::END_FINALLY {
                            self.skip_until = Some(ins.end());
                            break;
                        }
                    }
                }
            }
            // pre-3.11 handler-chain bookkeeping
            self.legacy_chain_step(&inst);
            // an if/else branch may have closed exactly at this offset
            // while the chain step ran (the fused or-continue chain skips
            // ahead into its body); close it before executing here
            if matches!(
                inst.op,
                Op::JUMP_ABSOLUTE | Op::JUMP_FORWARD | Op::JUMP | Op::POP_TOP
                    | Op::ROT_TWO | Op::ROT_THREE | Op::SWAP
            ) {
                self.close_blocks_at(pos);
                // py2.6 chained comparison: the close merged the chain
                // value and armed a skip covering this else-arm cleanup
                // instruction — honor it instead of letting the shuffle
                // corrupt the merged value on the live stack.
                if let Some(skip) = self.skip_until {
                    if pos < skip {
                        pc += 1;
                        continue;
                    }
                }
            }
            // chain fully parsed (END_FINALLY passed) but no jump emitted it
            // yet: flush before the continuation executes so statement order
            // and block targeting stay correct
            // a body-end jump that flew over an unparsed chain: parse it
            // now so the deferred emission below sees the handlers
            if !self.legacy_nest.is_empty()
                && self.legacy_handler.is_none()
                && self.legacy_try.as_ref().map_or(false, |l| {
                    !l.chain_done && l.handlers.is_empty() && pos > l.handler_start
                })
                && self.blocks.last().map_or(false, |b| b.kind == BlockType::Main)
            {
                self.parse_skipped_nested_chain(pos);
            }
            if self.legacy_handler.is_none()
                && self.legacy_try.as_ref().map_or(false, |l| {
                    l.chain_done
                        && !l.handlers.is_empty()
                        && !l.has_finally
                        && l.else_start.map_or(true, |_| {
                            inst.offset >= l.else_stop
                        })
                })
            {
                let l = self.legacy_try.take().unwrap();
                self.flush_pending_stores();
                if let Some(depth) = self.finish_legacy_nest() {
                    while self.blocks.len() > depth.max(1) {
                        let p = self.blocks.last().map(|b| b.start).unwrap_or(pos);
                        self.force_close_top(p);
                    }
                }
                self.push_stmt(Stmt::Try {
                    body: l.body,
                    handlers: l.handlers,
                    orelse: l.orelse,
                    finalbody: l.finalbody,
                });
            }
            if self.in_handler_prelude
                && !matches!(
                    inst.op,
                    Op::POP_TOP
                        | Op::SETUP_FINALLY
                        | Op::SETUP_EXCEPT
                        | Op::SETUP_CLEANUP
                        | Op::DUP_TOP
                        | Op::ROT_THREE
                        | Op::ROT_FOUR
                        | Op::ROT_TWO
                        | Op::SWAP
                        | Op::STORE_FAST
                        | Op::STORE_NAME
                        | Op::STORE_DEREF
                        | Op::LOAD_CONST
                        | Op::NOP
                        | Op::POP_BLOCK
                        | Op::COPY
                )
            {
                self.in_handler_prelude = false;
            }

            // 3.11+: open try blocks driven by the exception table
            self.open_exception_blocks(pos);

            // a prescanned unconditional `while True` loop starts here
            if self.while_true_loops.iter().any(|(t, _)| *t == pos)
                && !self.blocks.iter().any(|b| {
                    matches!(b.kind, BlockType::While | BlockType::For) && b.start == pos
                })
            {
                let end = self
                    .while_true_loops
                    .iter()
                    .find(|(t, _)| *t == pos)
                    .map(|(_, e)| *e)
                    .unwrap_or(usize::MAX);
                // statements before the loop top must not flow into it
                if !self.pending_stores.is_empty() {
                    self.flushing = true;
                    self.flush_pending_stores();
                    self.flushing = false;
                }
                let mut blk = Block::new(BlockType::While, pos, end);
                blk.cond = Some(self.name_expr("True"));
                blk.cond_set = true;
                self.blocks.push(blk);
            }

            // Close finished blocks before handling this instruction —
            // except when a backward jump lands exactly at an open If/Else
            // boundary: that jump is either a fused elif-chain exit or a
            // trailing `continue`, and the exec-time folded machinery must
            // see the branch block still open.
            let defer_close = matches!(
                inst.op,
                Op::JUMP_ABSOLUTE | Op::JUMP_BACKWARD | Op::JUMP_BACKWARD_NO_INTERRUPT
            ) && inst.target.map_or(false, |t| t < inst.offset)
                && self.blocks.last().map_or(false, |b| {
                    matches!(b.kind, BlockType::If | BlockType::Else) && b.end == pos
                });
            if !defer_close {
                self.close_blocks_at(pos);
            }

            // comprehension loop-target stores consume no stack value —
            // only while the comprehension is live and its target unset
            // (an unpacked `for k, v in` target arrives via the frame
            // machinery; post-loop restore stores must pop normally)
            if self.comp_target_store
                && self.unpack_frames.is_empty()
                && self
                    .inline_comp
                    .as_ref()
                    .map_or(false, |c| !c.target_seen)
                && matches!(
                    inst.op,
                    Op::STORE_FAST
                        | Op::STORE_NAME
                        | Op::STORE_DEREF
                        | Op::STORE_FAST_LOAD_FAST
                )
            {
                self.comp_target_store = false;
                let name = match inst.op {
                    Op::STORE_NAME => self.const_name(inst.arg as usize),
                    Op::STORE_FAST_LOAD_FAST => {
                        self.local_name(((inst.arg >> 4) & 0xF) as usize)
                    }
                    _ => self.local_name(inst.arg as usize),
                };
                let target_e = self.name_expr(name.clone());
                if let Some(comp) = &mut self.inline_comp {
                    if let Some(cur) = &mut comp.cur {
                        cur.target = Some(target_e);
                    }
                    comp.target_seen = true;
                }
                if inst.op == Op::STORE_FAST_LOAD_FAST {
                    let load = self.local_name((inst.arg & 0xF) as usize);
                    self.push(self.name_expr(load));
                }
                self.prev_op = Some(inst.op);
                pc += 1;
                continue;
            }
            let prev = self.prev_op;
            self.prev_op_at_exec = prev;
            if !self.exec(&inst) {
                if std::env::var("PYCDC_TRACE").is_ok() {
                    eprintln!("AW BREAK at {} {:?}", pos, inst.op);
                }
                break;
            }
            // keep prev_op meaningful across transparent ops
            if !matches!(inst.op, Op::NOT_TAKEN | Op::NOP | Op::CACHE) {
                self.prev_op = Some(inst.op);
            }
            pc += 1;
        }
    }

    fn open_exception_blocks(&mut self, pos: usize) {
        if !self.version.at_least(3, 11) || self.inline_comp.is_some() {
            return;
        }
        let tail_work = matches!(&self.pending_try_ctx,
            Some(tc) if tc.region_end == pos && tc.region_end > tc.body_end);
        let open_work = self.try_ctxs.contains_key(&pos);
        if !tail_work && !open_work {
            return;
        }
        // stores before a try boundary must land in source order
        if !self.pending_stores.is_empty() {
            self.flushing = true;
            self.flush_pending_stores();
            self.flushing = false;
        }
        // a pending try's protected region ends here: emit else/finally parts
        if tail_work {
            let tc = self.pending_try_ctx.take().unwrap();
            self.emit_try_tail(tc, pos);
        }
        if let Some(tc) = self.try_ctxs.get(&pos).cloned() {
            // a protocol-continuation shadow (3.12+ await inside try: the
            // exception table splits the protected range around the
            // YIELD_VALUE suspension point) only extends the previous
            // body — its statements flow into the pending body and the
            // tail already emitted at the first fragment must not repeat
            if self.active_try.is_none() || tc.body_end <= pos {
                let mut blk = Block::new(BlockType::Try, pos, tc.body_end);
                blk.finally_target = tc.except_handler.or(tc.finally_handler);
                self.active_try = Some(tc);
                self.blocks.push(blk);
            }
        }
    }

    /// Emit the else/finally structure of a completed try region and
    /// decompile the out-of-line handlers.
    fn emit_try_tail(&mut self, tc: TryCtx, pos: usize) {
        // `else:` clause exists only when the protected region extends past
        // the try body (finally covers body+else)
        let mut orelse = Vec::new();
        if tc.region_end > tc.body_end {
            if let Some(top) = self.blocks.last_mut() {
                orelse = std::mem::take(&mut top.stmts);
            }
        }
        // inline finally body (main flow): from pos until the flow's RETURN
        let stop = self
            .instrs
            .iter()
            .skip_while(|i| i.offset < pos)
            .find(|i| matches!(i.op, Op::RETURN_VALUE | Op::RETURN_CONST))
            .map(|i| i.offset)
            .unwrap_or(self.code.code.len());
        let mut finalbody = if tc.finally_handler.is_some() && stop > pos {
            let body = self.decompile_region(pos, stop);
            // main pass must not re-execute the inline finally body
            self.skip_until = Some(stop);
            body
        } else {
            Vec::new()
        };
        // except handlers (out-of-line)
        let handlers = match tc.except_handler {
            Some(h) => self.parse_except_dispatch(h),
            None => Vec::new(),
        };
        // finally handler body (exception path duplicate) — only use it when
        // there was no inline finally body
        if finalbody.is_empty() {
            if let Some(fh) = tc.finally_handler {
                let body = self.decompile_region(fh, self.handler_region_end(fh));
                finalbody = body;
            }
        }
        let mut body = self.pending_try_body.pop().unwrap_or_default();
        // nested-chain wrap: this region's body IS the inner try's body —
        // nest it, and adopt the enclosing finally parsed alongside
        if let Some(ih) = self.nested_inner_handlers.take() {
            let inner = Stmt::Try {
                body: std::mem::take(&mut body),
                handlers: ih,
                orelse: Vec::new(),
                finalbody: Vec::new(),
            };
            body = vec![inner];
            if let Some(fin) = self.pending_nested_finally.take() {
                if finalbody.is_empty() {
                    finalbody = fin;
                }
            }
        }
        self.pending_nested_finally = None;
        if handlers.is_empty() && finalbody.is_empty() && orelse.is_empty() && body.is_empty()
        {
            return;
        }
        self.push_stmt(Stmt::Try {
            body,
            handlers,
            orelse,
            finalbody,
        });
    }

    /// Linearly decompile the instruction range [from, to), returning its
    /// statements. Used for out-of-line handler regions (finally bodies).
    fn decompile_region(&mut self, from: usize, to: usize) -> Vec<Stmt> {
        let Some(&fi) = self.idx_of.get(&from) else {
            return Vec::new();
        };
        let saved_blocks = std::mem::replace(
            &mut self.blocks,
            vec![Block::new(BlockType::Main, from, to)],
        );
        let saved_stack = std::mem::take(&mut self.stack);
        let saved_skip = self.skip_until;
        let saved_line = self.cur_line;
        let saved_stores = std::mem::take(&mut self.pending_stores);

        let mut pc = fi;
        while pc < self.instrs.len() {
            let inst = self.instrs[pc];
            if inst.offset >= to {
                break;
            }
            let pos = inst.offset;
            if let Some(skip) = self.skip_until {
                if pos < skip {
                    pc += 1;
                    continue;
                }
                self.skip_until = None;
            }
            self.cur_offset = pos;
            self.cur_next = inst.end();
            if let Some(l) = inst.line {
                self.cur_line = Some(l);
            }
            // nested tries inside a handler body open from the same table
            self.open_exception_blocks(pos);
            // pre-3.11: a skipped NESTED handler chain parses with the same
            // state machine as the main walk (finally-body and 3.11+ handler
            // regions must NOT drive it — the outer chain state is live)
            if self.legacy_nest_depth > 0 {
                self.legacy_chain_step(&inst);
            }
            self.close_blocks_at(pos);
            if !self.exec(&inst) {
                if std::env::var("PYCDC_TRACE").is_ok() {
                    eprintln!("AW BREAK at {} {:?}", pos, inst.op);
                }
                break;
            }
            if !matches!(inst.op, Op::NOT_TAKEN | Op::NOP | Op::CACHE) {
                self.prev_op = Some(inst.op);
            }
            pc += 1;
        }
        self.flush_pending_stores();
        while self.blocks.len() > 1 {
            let p = self.blocks.last().map(|b| b.start).unwrap_or(to);
            self.force_close_top(p);
        }
        // a nested try whose protected region ends at/after the sub-walk
        // limit defers its tail forever — emit it now while the parsed
        // handler bodies still belong to it
        while let Some(tc) = self.pending_try_ctx.take() {
            self.emit_try_tail(tc, to);
        }
        let mut root = self.blocks.pop().unwrap();
        let stmts = std::mem::take(&mut root.stmts);

        self.blocks = saved_blocks;
        self.stack = saved_stack;
        self.skip_until = saved_skip;
        self.cur_line = saved_line;
        self.pending_stores = saved_stores;
        stmts
    }

    /// Parse an out-of-line except-dispatch handler region (3.11+):
    /// PUSH_EXC_INFO followed by `[pattern; CHECK_EXC_MATCH; PJIF next]*`
    /// clause bodies, ending in RERAISE.
    fn parse_except_dispatch(&mut self, from: usize) -> Vec<ExceptHandler> {
        let mut handlers = Vec::new();
        let mut clause_offsets: Vec<usize> = Vec::new();
        let end = self.dispatch_region_end(from);
        let region_end = self.handler_region_end(from);
        // nesting: this chain's own cleanup region ends exactly where the
        // next chain begins — that chain handles re-raises FROM this one,
        // i.e. it is the ENCLOSING try's dispatch. Adjacency must be exact
        // (a chain followed by its try's sunk post-flow, then a finally
        // handler chain, is NOT nested inside that finally).
        let nested = region_end > from
            && self
                .idx_of
                .get(&region_end)
                .and_then(|&ri| self.instrs.get(ri.wrapping_sub(1)))
                .map(|p| p.op == Op::RERAISE)
                .unwrap_or(false)
            && self.chain_extent(from) == region_end
            && self
                .idx_of
                .get(&region_end)
                .and_then(|&i| {
                    let is_dispatch = self.instrs.get(i).map(|x| x.op == Op::PUSH_EXC_INFO)
                        == Some(true)
                        // a finally/cleanup chain (no CHECK_EXC_MATCH) is
                        // not an enclosing except dispatch
                        && self.instrs[i..]
                            .iter()
                            .take(40)
                            .any(|x| x.op == Op::CHECK_EXC_MATCH);
                    Some(is_dispatch)
                })
                .unwrap_or(false);
        let mut pc = match self.idx_of.get(&from) {
            Some(&i) => i,
            None => return handlers,
        };
        // expect PUSH_EXC_INFO
        if self.instrs.get(pc).map(|i| i.op) != Some(Op::PUSH_EXC_INFO) {
            return handlers;
        }
        pc += 1;
        let mut pattern: Option<ExprRef> = None;
        while pc < self.instrs.len() {
            let inst = self.instrs[pc];
            if inst.offset >= end
                && !handlers.is_empty()
                && !(nested && inst.offset < self.chain_extent(from))
            {
                break;
            }
            match inst.op {
                Op::CHECK_EXC_MATCH => {
                    // stack: [exc, pattern] — pattern expression was built
                    // by preceding loads; simulate them minimally
                    pattern = self.sim_pattern(&mut pc, inst.offset);
                    pc += 1;
                    continue;
                }
                Op::POP_JUMP_IF_FALSE | Op::POP_JUMP_FORWARD_IF_FALSE => {
                    let next = inst.target.unwrap_or(end);
                    clause_offsets.push(inst.offset);
                    pc += 1;
                    // 3.14 pads the clause head with NOT_TAKEN
                    while matches!(
                        self.instrs.get(pc).map(|i| i.op),
                        Some(Op::NOT_TAKEN) | Some(Op::NOP)
                    ) {
                        pc += 1;
                    }
                    // optional `as name` store
                    let mut name = None;
                    if let Some(ninst) = self.instrs.get(pc) {
                        if matches!(
                            ninst.op,
                            Op::STORE_FAST | Op::STORE_NAME | Op::STORE_DEREF
                        ) {
                            name = Some(match ninst.op {
                                Op::STORE_NAME => self.const_name(ninst.arg as usize),
                                Op::STORE_DEREF => self
                                    .code
                                    .deref_name(ninst.arg as usize)
                                    .unwrap_or("?")
                                    .to_string(),
                                _ => self.local_name(ninst.arg as usize),
                            });
                            pc += 1;
                        }
                    }
                    // arm the `as` cleanup swallow for the body sub-walk:
                    // 3.11+ embeds `e = None; del e` between the body and
                    // its RETURN (and again on the exception path)
                    let saved_pac = self.pending_as_cleanup.take();
                    if let Some(n) = &name {
                        self.pending_as_cleanup = Some(n.clone());
                    }
                    let body = self.decompile_handler_body(&mut pc, next, region_end);
                    self.pending_as_cleanup = saved_pac;
                    handlers.push(ExceptHandler {
                        type_: pattern.take(),
                        name: name.map(|n| Rc::new(Expr::Name(n)) as ExprRef),
                        body,
                    });
                    // everything up to the next clause (body + exception-
                    // path cleanup + its RERAISE) is consumed
                    if let Some(&ni) = self.idx_of.get(&next) {
                        pc = ni;
                    }
                    continue;
                }
                Op::RERAISE => {
                    pc += 1;
                    // a clause's exception-path cleanup also ends in
                    // RERAISE — the chain only terminates when no new
                    // CHECK_EXC_MATCH clause follows
                    let mut m = pc;
                    let mut more = false;
                    while m < self.instrs.len() {
                        let nx = &self.instrs[m];
                        if nx.offset >= end {
                            break;
                        }
                        match nx.op {
                            Op::CHECK_EXC_MATCH => {
                                more = true;
                                break;
                            }
                            Op::LOAD_CONST | Op::LOAD_GLOBAL | Op::LOAD_NAME
                            | Op::STORE_FAST | Op::STORE_NAME
                            | Op::DELETE_FAST | Op::DELETE_NAME
                            | Op::STORE_DEREF | Op::DELETE_DEREF
                            | Op::COPY | Op::SWAP | Op::POP_TOP
                            | Op::POP_EXCEPT | Op::PUSH_EXC_INFO
                            | Op::NOP | Op::NOT_TAKEN
                            | Op::BUILD_TUPLE => {
                                m += 1;
                            }
                            _ => break,
                        }
                    }
                    if !more && (!handlers.is_empty() || pattern.is_none()) {
                        if nested && inst.end() == region_end {
                            // this cleanup RERAISE separates the two
                            // chains — keep scanning into the outer one
                            continue;
                        }
                        break;
                    }
                    continue;
                }
                Op::POP_EXCEPT => {
                    pc += 1;
                    continue;
                }
                Op::RETURN_VALUE | Op::RETURN_CONST | Op::END_FINALLY => {
                    // a stray terminator between clauses (a body ending
                    // without a closing jump): hop to the next clause
                    if inst.offset >= end
                        && !handlers.is_empty()
                        && !(nested && inst.offset < self.chain_extent(from))
                    {
                        break;
                    }
                    pc += 1;
                }
                _ => {
                    pc += 1;
                }
            }
        }
        if nested && !handlers.is_empty() {
            // clauses parsed past the chain boundary belong to the
            // enclosing try — split them off and wrap this try inside a
            // bare `except:` handler (the enclosing try catches re-raises
            // from this one, and any exception when no clause matched).
            // The enclosing chain's own clauses/finally come from a
            // recursive parse of its dispatch head.
            let outer_idx = clause_offsets
                .iter()
                .position(|o| *o >= region_end)
                .unwrap_or(handlers.len());
            let _ = handlers.split_off(outer_idx);
            // the clauses below the boundary are the INNER try's handlers;
            // emit_try_tail builds `Try { body: [inner try], .. }` from them
            self.nested_inner_handlers = Some(handlers);
            let outer = self.parse_except_dispatch(region_end);
            // enclosing finally: entries past the outer chain whose target
            // is a non-except (finally) handler
            let mut finalbody = Vec::new();
            let mut fin_target = None;
            for e in &self.exc_entries {
                if e.start > region_end && e.target > region_end {
                    if self
                        .idx_of
                        .get(&e.target)
                        .and_then(|&i| self.instrs.get(i))
                        .map(|x| x.op == Op::PUSH_EXC_INFO)
                        .unwrap_or(false)
                        && !self.instrs[self.idx_of[&e.target]..]
                            .iter()
                            .take(40)
                            .any(|x| x.op == Op::CHECK_EXC_MATCH)
                    {
                        fin_target = Some(e.target);
                        break;
                    }
                }
            }
            if let Some(fh) = fin_target {
                finalbody =
                    self.decompile_region(fh, self.chain_extent(fh).max(fh + 2));
            }
            self.pending_nested_finally = Some(finalbody);
            return outer;
        }
        handlers
    }

    /// Build the pattern expression for an except clause: forward-simulate
    /// the loads between the previous clause boundary and CHECK_EXC_MATCH.
    fn sim_pattern(&self, _pc: &mut usize, check_offset: usize) -> Option<ExprRef> {
        let ci = *self.idx_of.get(&check_offset)?;
        // find clause start: previous boundary instruction
        let mut start = ci;
        while start > 0 {
            let prev = &self.instrs[start - 1];
            if matches!(
                prev.op,
                Op::PUSH_EXC_INFO
                    | Op::POP_JUMP_IF_FALSE
                    | Op::POP_JUMP_FORWARD_IF_FALSE
                    | Op::RERAISE
                    | Op::JUMP_FORWARD
                    | Op::JUMP_BACKWARD
                    | Op::JUMP_ABSOLUTE
                    | Op::JUMP
                    | Op::POP_EXCEPT
                    | Op::CHECK_EXC_MATCH
            ) {
                break;
            }
            start -= 1;
        }
        let mut stack: Vec<ExprRef> = Vec::new();
        for ins in &self.instrs[start..ci] {
            match ins.op {
                Op::LOAD_GLOBAL => {
                    let idx = if self.version.at_least(3, 11) {
                        (ins.arg >> 1) as usize
                    } else {
                        ins.arg as usize
                    };
                    stack.push(self.name_expr(self.const_name(idx)));
                }
                Op::LOAD_NAME | Op::LOAD_DEREF | Op::LOAD_FAST => {
                    let n = match ins.op {
                        Op::LOAD_NAME => self.const_name(ins.arg as usize),
                        Op::LOAD_DEREF => self
                            .code
                            .deref_name(ins.arg as usize)
                            .unwrap_or("?")
                            .to_string(),
                        _ => self.local_name(ins.arg as usize),
                    };
                    stack.push(self.name_expr(n));
                }
                Op::LOAD_CONST => {
                    if let Some(o) = self.code.consts.get(ins.arg as usize) {
                        stack.push(Rc::new(Expr::Const(o.clone())));
                    }
                }
                Op::LOAD_ATTR => {
                    let attr = self.const_name(ins.arg as usize);
                    if let Some(v) = stack.pop() {
                        stack.push(Rc::new(Expr::Attribute { value: v, attr }));
                    }
                }
                Op::BUILD_TUPLE => {
                    let n = ins.arg as usize;
                    if stack.len() >= n {
                        let items: Vec<ExprRef> =
                            stack.split_off(stack.len() - n);
                        stack.push(Rc::new(Expr::Tuple(items)));
                    }
                }
                Op::DUP_TOP | Op::COPY => {
                    if let Some(t) = stack.last().cloned() {
                        stack.push(t);
                    }
                }
                _ => {}
            }
        }
        // CHECK_EXC_MATCH consumes [exc, pattern]; pattern is on top
        stack.pop()
    }

    /// Decompile one except-clause body: instructions from the current pc
    /// until POP_EXCEPT; then skip the implicit `name = None; del name`
    /// cleanup and the closing jump. Advances `pc`.
    fn decompile_handler_body(
        &mut self,
        pc: &mut usize,
        next_clause: usize,
        region_end: usize,
    ) -> Vec<Stmt> {
        // the clause body runs to the next clause start (the mismatch
        // jump target is exactly that boundary in every 3.11+ layout)
        let limit = next_clause;
        let _ = region_end;
        let body_start = match self.instrs.get(*pc) {
            Some(i) => i.offset,
            None => return Vec::new(),
        };
        // locate POP_EXCEPT within this clause
        let mut k = *pc;
        let mut pop_idx = None;
        while k < self.instrs.len() {
            let ins = &self.instrs[k];
            if ins.offset >= limit {
                break;
            }
            if ins.op == Op::POP_EXCEPT {
                pop_idx = Some(k);
                break;
            }
            if ins.op == Op::PUSH_EXC_INFO {
                // a nested handler chain starts inside this clause: the
                // clause's own POP_EXCEPT, if any, follows the nested
                // region — the body sub-walk folds the nested chain
                break;
            }
            k += 1;
        }
        let Some(pi) = pop_idx else {
            // a clause whose body never exits the except state (it ends
            // in `raise`): the body runs to the clause limit
            *pc = k;
            return if limit > body_start {
                self.decompile_region(body_start, limit)
            } else {
                Vec::new()
            };
        };
        // 3.9+/3.11+ shape: `[POP_TOP;] POP_EXCEPT; [as-cleanup]; body` —
        // the body FOLLOWS the POP_EXCEPT. The legacy shape keeps the body
        // BEFORE it (`body; POP_EXCEPT; cleanup; jump`).
        let prelude_only = self.instrs[*pc..=pi]
            .iter()
            .all(|i| matches!(i.op, Op::POP_TOP | Op::POP_EXCEPT | Op::NOP | Op::NOT_TAKEN));
        if prelude_only {
            let mut m = pi + 1;
            // skip the eager `as` cleanup: LOAD_CONST None; STORE n; DELETE n
            if matches!(self.instrs.get(m).map(|i| i.op), Some(Op::LOAD_CONST))
                && matches!(
                    self.instrs.get(m + 1).map(|i| i.op),
                    Some(Op::STORE_FAST) | Some(Op::STORE_NAME) | Some(Op::STORE_DEREF)
                )
                && matches!(
                    self.instrs.get(m + 2).map(|i| i.op),
                    Some(Op::DELETE_FAST) | Some(Op::DELETE_NAME) | Some(Op::DELETE_DEREF)
                )
            {
                m += 3;
            }
            let body_from = self.instrs.get(m).map(|i| i.offset).unwrap_or(limit);
            *pc = m;
            return if limit > body_from {
                self.decompile_region(body_from, limit)
            } else {
                Vec::new()
            };
        }
        // legacy shape: body before the POP_EXCEPT. A computed return
        // (`except E as e: return <expr with e>`) evaluates the value
        // BEFORE the POP_EXCEPT and returns AFTER the as-cleanup — extend
        // the body region over the cleanup to include that RETURN.
        let mut body_end = self.instrs[pi].offset;
        let mut k2 = pi + 1;
        // skip cleanup: [LOAD_CONST None; STORE; DELETE], closing jump
        while k2 < self.instrs.len() {
            let c = &self.instrs[k2];
            match c.op {
                Op::LOAD_CONST | Op::STORE_FAST | Op::STORE_NAME
                | Op::DELETE_FAST | Op::DELETE_NAME | Op::STORE_DEREF
                | Op::DELETE_DEREF => {
                    k2 += 1;
                }
                Op::RETURN_VALUE | Op::RETURN_CONST => {
                    body_end = c.end();
                    k2 += 1;
                    break;
                }
                Op::JUMP_FORWARD
                | Op::JUMP_BACKWARD
                | Op::JUMP_ABSOLUTE
                | Op::JUMP
                | Op::JUMP_NO_INTERRUPT
                | Op::RERAISE => {
                    k2 += 1;
                    break;
                }
                _ => break,
            }
        }
        // when the clause body ran up to the POP_EXCEPT and what follows
        // (before the mismatch RERAISE) is straight-line flow with no new
        // clause, the compiler sank the post-try continuation into the
        // handler region (`try: raise X / except X: ... / return v` — the
        // body always raises, so the flow is only reachable through the
        // handler). Include it so the function's tail is not lost.
        if k2 < self.instrs.len() && self.instrs[k2].offset < limit {
            let mut m2 = k2;
            let mut saw_term = false;
            while m2 < self.instrs.len() {
                let nx = &self.instrs[m2];
                match nx.op {
                    // the mismatch RERAISE sits exactly AT the clause
                    // limit — it is the terminator we look for
                    Op::RERAISE if nx.offset <= limit => {
                        saw_term = true;
                        break;
                    }
                    Op::CHECK_EXC_MATCH | Op::PUSH_EXC_INFO => break,
                    _ => {}
                }
                if nx.offset >= limit {
                    break;
                }
                m2 += 1;
            }
            if saw_term {
                body_end = self.instrs[m2].offset;
                k2 = m2;
            }
        }
        *pc = k2;
        if body_end > body_start {
            self.decompile_region(body_start, body_end)
        } else {
            Vec::new()
        }
    }

    /// End of a handler region: the next PUSH_EXC_INFO handler start.
    fn handler_region_end(&self, from: usize) -> usize {
        let mut end = self.code.code.len();
        for e in &self.exc_entries {
            if e.target <= from || e.target >= end {
                continue;
            }
            if let Some(&hi) = self.idx_of.get(&e.target) {
                if self.instrs.get(hi).map(|i| i.op) == Some(Op::PUSH_EXC_INFO) {
                    end = e.target;
                }
            }
        }
        end
    }

    /// Extent of the out-of-line handler chain starting at `from`: runs
    /// through clause bodies and trailing cleanups, ending after the last
    /// RERAISE not followed by more cleanup.
    fn chain_extent(&self, from: usize) -> usize {
        let Some(&i) = self.idx_of.get(&from) else {
            return from;
        };
        // a depth-0 entry inside the span whose target is another chain
        // head protects a REAL body laid out after this chain (a whole-
        // function try whose handler precedes its body) — stop before it
        let mut body_stops: Vec<usize> = Vec::new();
        for e in &self.exc_entries {
            if e.depth == 0 && e.start > from && self.chain_heads.contains(&e.target) {
                // chain-internal fragments (clause-closing jumps and
                // cleanup tails redirected onward) consist only of
                // cleanup/jump ops — real bodies contain user code
                let frag = self
                    .idx_of
                    .get(&e.start)
                    .map(|&si| {
                        self.instrs[si..]
                            .iter()
                            .take_while(|x| x.offset < e.end)
                            .all(|x| {
                                matches!(
                                    x.op,
                                    Op::COPY
                                        | Op::SWAP
                                        | Op::POP_TOP
                                        | Op::POP_EXCEPT
                                        | Op::RERAISE
                                        | Op::LOAD_CONST
                                        | Op::STORE_FAST
                                        | Op::STORE_NAME
                                        | Op::STORE_DEREF
                                        | Op::DELETE_FAST
                                        | Op::DELETE_NAME
                                        | Op::DELETE_DEREF
                                        | Op::NOP
                                        | Op::NOT_TAKEN
                                        | Op::JUMP_FORWARD
                                        | Op::JUMP
                                        | Op::JUMP_NO_INTERRUPT
                                )
                            })
                    })
                    .unwrap_or(false);
                if !frag {
                    body_stops.push(e.start);
                }
            }
        }
        // table closure: entries targeting this chain, plus entries whose
        // range lies inside the covered span (clause bodies and cleanup
        // redirects), transitively — the chain's code is scattered with
        // inline clause bodies that the canonical op scan cannot cross.
        // The span can never reach a body stop: that is main-flow code
        // following the chain (e.g. the try body after an async-with
        // cleanup handler), even when in-chain entries redirect to
        // far-away dead-end handlers (StopIteration intrinsics).
        let stop_cap = body_stops.iter().filter(|s| **s > from).min().copied();
        let mut table_end = from;
        loop {
            let mut grew = false;
            for e in &self.raw_exc_entries {
                let seed = e.start == from
                    || (e.target == from && e.start < from);
                let inside = e.start >= from
                    && e.start < table_end
                    && !body_stops.contains(&e.start);
                if (seed || inside) && !body_stops.contains(&e.start) {
                    // targets of in-chain redirects stay inside the span;
                    // a target that is ANOTHER chain head (e.g. a finally
                    // handler of the enclosing try) bounds it instead
                    let cands: [usize; 2] =
                        [e.end, if self.chain_heads.contains(&e.target) { from } else { e.target }];
                    for cand in cands {
                        if cand > table_end && cand > from {
                            if stop_cap.map_or(false, |cap| cand >= cap) {
                                continue;
                            }
                            table_end = cand;
                            grew = true;
                        }
                    }
                }
            }
            if !grew {
                break;
            }
        }
        let mut end = from;
        let mut k = i;
        while k < self.instrs.len() {
            let ins = &self.instrs[k];
            if body_stops.contains(&ins.offset) {
                break;
            }
            end = ins.end();
            if matches!(ins.op, Op::RETURN_VALUE | Op::RETURN_CONST) {
                break;
            }
            if ins.op == Op::RERAISE {
                // the chain continues through cleanup tails AND through
                // the pattern loads of a following clause — it only ends
                // when no CHECK_EXC_MATCH is reachable through the
                // cleanup/pattern vocabulary
                let mut m = k + 1;
                let mut cont = false;
                let mut stop_at = None;
                let mut last_cleanup_end = None;
                let mut steps = 0;
                while let Some(nx) = self.instrs.get(m) {
                    if body_stops.contains(&nx.offset) {
                        stop_at = Some(nx.offset);
                        break;
                    }
                    match nx.op {
                        Op::CHECK_EXC_MATCH => {
                            cont = true;
                            break;
                        }
                        // the adjacent chain head ends this chain's extent
                        // exactly at the head (nesting adjacency)
                        Op::PUSH_EXC_INFO => {
                            stop_at = Some(nx.offset);
                            break;
                        }
                        Op::COPY
                        | Op::SWAP
                        | Op::POP_EXCEPT
                        | Op::POP_TOP
                        | Op::RERAISE
                        | Op::NOP
                        | Op::NOT_TAKEN => {
                            last_cleanup_end = Some(nx.end());
                            m += 1;
                            steps += 1;
                        }
                        // pattern loads only continue the chain when they
                        // lead to a CHECK_EXC_MATCH (tracked via cont)
                        Op::LOAD_CONST
                        | Op::LOAD_GLOBAL
                        | Op::LOAD_NAME
                        | Op::BUILD_TUPLE
                        | Op::EXTENDED_ARG => {
                            m += 1;
                            steps += 1;
                        }
                        _ => break,
                    }
                    if steps > 16 {
                        break;
                    }
                }
                if let Some(sa) = stop_at {
                    end = sa;
                    break;
                }
                if !cont {
                    // walk the trailing dead cleanup tail (COPY/POP_EXCEPT/
                    // RERAISE zero-depth-finally padding) so the extent
                    // covers it; stop at anything that is not tail padding
                    let mut t = m;
                    let mut tail_end = last_cleanup_end;
                    while let Some(nx) = self.instrs.get(t) {
                        if body_stops.contains(&nx.offset) {
                            break;
                        }
                        match nx.op {
                            Op::COPY
                            | Op::SWAP
                            | Op::POP_EXCEPT
                            | Op::POP_TOP
                            | Op::RERAISE
                            | Op::NOP
                            | Op::NOT_TAKEN
                            | Op::JUMP_BACKWARD_NO_INTERRUPT => {
                                tail_end = Some(nx.end());
                                t += 1;
                            }
                            _ => break,
                        }
                    }
                    if let Some(te) = tail_end {
                        end = te;
                    }
                    break;
                }
            }
            k += 1;
        }
        // the op scan stopping at a body stop already bounds the extent;
        // otherwise a table closure with no body stop (tail-most chain)
        // must not ride depth-0 lasti redirects to far-away dead-end
        // handlers (StopIterationError intrinsics) past the chain's own
        // trailing cleanup. The chain's normal-exit JUMP_FORWARDs target
        // exactly the main-flow resume point — cap the closure there.
        if stop_cap.is_none() {
            let mut exit_cap = usize::MAX;
            let mut k2 = i;
            while k2 < self.instrs.len() {
                let ins = &self.instrs[k2];
                if body_stops.contains(&ins.offset) {
                    break;
                }
                if matches!(ins.op, Op::JUMP_FORWARD | Op::JUMP) {
                    if let Some(t) = ins.target {
                        if t > ins.offset && t > from && t < exit_cap {
                            exit_cap = t;
                        }
                    }
                }
                if ins.op == Op::RERAISE && k2 + 1 < self.instrs.len() {
                    let nx = &self.instrs[k2 + 1];
                    if nx.op == Op::PUSH_EXC_INFO {
                        break;
                    }
                }
                if matches!(ins.op, Op::RETURN_VALUE | Op::RETURN_CONST) {
                    break;
                }
                k2 += 1;
            }
            if exit_cap < usize::MAX {
                table_end = table_end.min(exit_cap);
            }
        }
        end.max(table_end)
    }

    /// Dispatch-loop end: the region end, additionally capped at the start
    /// of a NESTED try's protected code inside this region — the nested
    /// chain (folded by the body sub-walk) must not be re-parsed here.
    fn dispatch_region_end(&self, from: usize) -> usize {
        let mut end = self.handler_region_end(from);
        for e in &self.exc_entries {
            if e.start > from && e.start < end && e.target > from {
                end = e.start;
            }
        }
        end
    }

    /// Save the outer legacy-chain state so a nested chain (a try inside
    /// an except body) can parse in the single legacy_try/legacy_handler
    /// slots; `finish_legacy_nest` restores it right before the nested
    /// Try is emitted so push_stmt routes it into the outer handler body.
    fn begin_legacy_nest(&mut self) {
        self.legacy_nest.push(LegacyNest {
            outer_try: self.legacy_try.take(),
            outer_handler: self.legacy_handler.take(),
            outer_handler_end: self.legacy_handler_end.take(),
            outer_prelude: self.in_handler_prelude,
            depth: self.blocks.len(),
            skipped_chain: None,
        });
        self.in_handler_prelude = false;
    }

    /// The nested body-end jump flies over the nested handler chain
    /// (py2 emits JUMP_ABSOLUTE here, which the walk follows): parse the
    /// skipped chain [handler_start, target) with a region sub-walk, fold
    /// any handler the sub-walk left open (a terminating `return` body
    /// breaks it before END_FINALLY), and mark the chain done when at
    /// least one clause was parsed — the jump past the chain end IS the
    /// chain completion for a nested try
    fn parse_skipped_nested_chain(&mut self, target: usize) -> bool {
        let Some(lt) = self.legacy_try.clone() else {
            return false;
        };
        if !lt.handlers.is_empty() || target <= lt.handler_start {
            return false;
        }
        self.legacy_nest_depth += 1;
        self.decompile_region(lt.handler_start, target);
        self.legacy_nest_depth -= 1;
        if let Some(nest) = self.legacy_nest.last_mut() {
            nest.skipped_chain = Some((lt.handler_start, target));
        }
        if let Some(h) = self.legacy_handler.take() {
            if let Some(l) = self.legacy_try.as_mut() {
                l.handlers.push(ExceptHandler {
                    type_: h.type_,
                    name: h.name,
                    body: h.body,
                });
            }
            self.legacy_handler_end = None;
        }
        if let Some(l) = self.legacy_try.as_mut() {
            if !l.handlers.is_empty() {
                l.chain_done = true;
                // the region after the chain belongs to the OUTER flow —
                // never redirect statements into the nested else
                l.else_start = None;
            }
        }
        matches!(self.legacy_try.as_ref(), Some(l) if !l.handlers.is_empty())
    }

    /// Restore the saved outer chain state, returning the nesting depth
    /// (blocks that opened inside the nested chain and are still open must
    /// be closed before the nested Try is emitted).
    fn finish_legacy_nest(&mut self) -> Option<usize> {
        let nest = self.legacy_nest.pop()?;
        self.legacy_try = nest.outer_try;
        self.legacy_handler = nest.outer_handler;
        self.legacy_handler_end = nest.outer_handler_end;
        self.in_handler_prelude = nest.outer_prelude;
        // the nested chain's handler-exit jump landing exactly on the
        // outer else_start means the outer handler flow continues into
        // that region: it is a trailing statement zone, not an else
        if let Some(lt) = self.legacy_try.as_mut() {
            if !lt.handlers.is_empty() && self.legacy_handler.is_none() {
                lt.chain_done = true;
            }
        }
        if let (Some((rs, re)), Some(lt)) = (nest.skipped_chain, self.legacy_try.as_mut()) {
            if let Some(es) = lt.else_start {
                let exit_lands_on_else = self
                    .idx_of
                    .get(&rs)
                    .map_or(false, |&ri| {
                        self.instrs[ri..]
                            .iter()
                            .take_while(|x| x.offset < re)
                            .any(|x| {
                                matches!(x.op, Op::JUMP_FORWARD | Op::JUMP_ABSOLUTE)
                                    && x.target == Some(es)
                            })
                    });
                if exit_lands_on_else {
                    lt.else_start = None;
                }
            }
        }
        Some(nest.depth)
    }

    /// Restore without block bookkeeping (the emission sites where the
    /// nested chain's blocks are already closed)
    fn restore_legacy_nest(&mut self) {
        let _ = self.finish_legacy_nest();
    }

    /// Drive the pre-3.11 try/except handler chain state machine.
    fn legacy_chain_step(&mut self, inst: &Instruction) {
        if self.version.at_least(3, 11) {
            return;
        }
        let Some(lt) = self.legacy_try.clone() else {
            return;
        };
        let pos = inst.offset;

        // bare `except:` entry: the handler starts with POP_TOPs instead of
        // DUP_TOP + COMPARE_OP + PJIF — open a typeless legacy handler whose
        // end is the first POP_EXCEPT / END_FINALLY / RERAISE
        if self.legacy_handler.is_none()
            && lt.handlers.is_empty()
            && lt.else_start.is_none()
            && pos == lt.handler_start
            && inst.op == Op::POP_TOP
        {
            let mut hend = usize::MAX;
            for ins in self.instrs.iter() {
                if ins.offset <= pos {
                    continue;
                }
                if matches!(ins.op, Op::POP_EXCEPT | Op::END_FINALLY | Op::RERAISE) {
                    hend = ins.offset;
                    break;
                }
            }
            self.legacy_handler = Some(LegacyHandler {
                type_: None,
                name: None,
                body: Vec::new(),
                block_depth: self.blocks.len(),
                pop_seen: false,
            });
            self.legacy_handler_end = Some(hend);
            self.in_handler_prelude = true;
        }

        // current handler body ends at the mismatch jump
        if self.legacy_handler.is_some() {
            let end = self.legacy_handler_end.unwrap_or(usize::MAX);
            if pos >= end {
                if self.legacy_handler.is_some() {
                    self.flush_pending_stores();
                }
                if let Some(h) = self.legacy_handler.take() {
                    if let Some(he) = &h.name {
                        if let Expr::Name(n) = &**he {
                            self.pending_as_cleanup = Some(n.clone());
                        }
                    }
                    if let Some(lt) = self.legacy_try.as_mut() {
                        lt.handlers.push(ExceptHandler {
                            type_: h.type_,
                            name: h.name,
                            body: h.body,
                        });
                    }
                }
                self.legacy_handler_end = None;
            }
        }

        // swallow the implicit `name = None; del name` handler cleanup
        if self.legacy_handler.is_some() {
            let hname = self
                .legacy_handler
                .as_ref()
                .and_then(|h| match &h.name {
                    Some(e) => match &**e {
                        Expr::Name(n) => Some(n.clone()),
                        _ => None,
                    },
                    None => None,
                });
            if let Some(hname) = hname {
                let nm = match inst.op {
                    Op::STORE_NAME | Op::DELETE_NAME => {
                        Some(self.const_name(inst.arg as usize))
                    }
                    Op::STORE_FAST | Op::DELETE_FAST => {
                        Some(self.local_name(inst.arg as usize))
                    }
                    Op::STORE_DEREF | Op::DELETE_DEREF => self
                        .code
                        .deref_name(inst.arg as usize)
                        .map(str::to_string),
                    _ => None,
                };
                if nm.as_deref() == Some(hname.as_str()) {
                    self.legacy_handler_cleanup = true;
                }
            }
        }

        match inst.op {
            // `except E as name:` (py3) / `except E, name:` (py2) — both
            // emit an explicit store inside the handler prelude whose value
            // is the phantom exception we never model. A body store instead
            // pops a real pushed value, so an empty simulation stack is the
            // discriminator (LOAD_CONST is prelude-allowed and would
            // otherwise let a first body statement be swallowed as a name).
            Op::STORE_FAST | Op::STORE_NAME | Op::STORE_DEREF => {
                // the `as` store sits inside the handler prelude (right
                // after the POP_TOPs); a store after real body instructions
                // started (prelude cleared) is a body statement
                let wants_name = self.in_handler_prelude
                    && (self.version.major >= 3 || self.legacy_nest_depth == 0)
                    && self.stack.is_empty()
                    && self
                        .legacy_handler
                        .as_ref()
                        .map(|h| h.name.is_none() && h.body.is_empty() && h.type_.is_some())
                        .unwrap_or(false);
                if wants_name {
                    // the `as name` store follows the match jump; let
                    // emit_store capture the target expression
                    self.legacy_handler_name_store = true;
                }
            }
            // end of a handler body
            Op::POP_EXCEPT => {
                self.in_handler_prelude = false;
                // 3.9 terminating handlers run POP_EXCEPT BEFORE the body
                // (`except E: return`): defer the fold to the body's end
                let next_is_body = self
                    .idx_of
                    .get(&pos)
                    .and_then(|&pi| self.instrs.get(pi + 1))
                    .map_or(false, |nx| {
                        !matches!(
                            nx.op,
                            Op::RERAISE
                                | Op::END_FINALLY
                                | Op::JUMP_FORWARD
                                | Op::JUMP_ABSOLUTE
                                | Op::JUMP
                        ) && self
                            .legacy_handler_end
                            .map_or(true, |e| nx.offset < e)
                    });
                if next_is_body {
                    if let Some(h) = self.legacy_handler.as_mut() {
                        h.pop_seen = true;
                    }
                } else {
                    if self.legacy_handler.is_some() {
                        self.flush_pending_stores();
                    }
                    if let Some(h) = self.legacy_handler.take() {
                        if let Some(he) = &h.name {
                            if let Expr::Name(n) = &**he {
                                self.pending_as_cleanup = Some(n.clone());
                            }
                        }
                        if let Some(l) = self.legacy_try.as_mut() {
                            l.handlers.push(ExceptHandler {
                                type_: h.type_,
                                name: h.name,
                                body: h.body,
                            });
                        }
                    }
                    self.legacy_handler_end = None;
                }
            }
            // RERAISE ends the current handler; a mismatch-path RERAISE with
            // no open handler ends the whole chain
            Op::RERAISE => {
                self.in_handler_prelude = false;
                if self.legacy_handler.is_some() {
                    self.flush_pending_stores();
                }
                if let Some(h) = self.legacy_handler.take() {
                    if let Some(he) = &h.name {
                        if let Expr::Name(n) = &**he {
                            self.pending_as_cleanup = Some(n.clone());
                        }
                    }
                    self.legacy_handler_end = None;
                    if let Some(l) = self.legacy_try.as_mut() {
                        l.handlers.push(ExceptHandler {
                            type_: h.type_,
                            name: h.name,
                            body: h.body,
                        });
                    }
                } else if self
                    .legacy_try
                    .as_ref()
                    .map(|l| !l.handlers.is_empty())
                    .unwrap_or(false)
                {
                    let has_else_after = self
                        .legacy_try
                        .as_ref()
                        .map_or(false, |l| l.else_start.map_or(true, |es| pos >= es) == false);
                    if has_else_after {
                        // an else region follows the chain: defer emission
                        // until the region is consumed
                        if let Some(l) = self.legacy_try.as_mut() {
                            l.chain_done = true;
                        }
                    } else {
                        let l = self.legacy_try.take().unwrap();
                        self.restore_legacy_nest();
                        self.push_stmt(Stmt::Try {
                            body: l.body,
                            handlers: l.handlers,
                            orelse: l.orelse,
                            finalbody: l.finalbody,
                        });
                    }
                }
            }
            // END_FINALLY closes a finally handler (and the statement)
            Op::END_FINALLY => {
                // a swallowed as-cleanup wrapper's END_FINALLY is not the
                // chain end
                if self.as_cleanup_wrappers.iter().any(|(_, e)| *e == pos) {
                    return;
                }
                let mut end_at_chain = false;
                if let Some(l) = self.legacy_try.as_mut() {
                    if !l.handlers.is_empty() && !l.has_finally {
                        // last handler mismatch path: chain fully parsed
                        l.chain_done = true;
                        if l.else_start == Some(pos) {
                            // forward jump from the body landed exactly at
                            // the chain end: no else region, emit now
                            end_at_chain = true;
                        }
                    }
                }
                if end_at_chain {
                    let l = self.legacy_try.take().unwrap();
                    self.flush_pending_stores();
                    self.restore_legacy_nest();
                    self.push_stmt(Stmt::Try {
                        body: l.body,
                        handlers: l.handlers,
                        orelse: l.orelse,
                        finalbody: l.finalbody,
                    });
                }
                if let Some(l) = self.legacy_try.as_mut() {
                    if l.has_finally {
                        let l = self.legacy_try.take().unwrap();
                        self.restore_legacy_nest();
                        self.push_stmt(Stmt::Try {
                            body: l.body,
                            handlers: l.handlers,
                            orelse: l.orelse,
                            finalbody: l.finalbody,
                        });
                    }
                }
            }
            // a JUMP_FORWARD inside a handler (not part of an open handler
            // body anymore) ends the chain: emit try (+else target region)
            Op::JUMP_FORWARD | Op::JUMP_ABSOLUTE => {
                // py2 handler normal exits are forward jumps: one
                // landing exactly on the body jump's target retracts the
                // presumed else region (no-else chain)
                if lt.else_start == inst.target
                    && (self.legacy_handler.is_some() || !lt.handlers.is_empty())
                    && inst.target.map_or(false, |t| t > pos)
                {
                    if let Some(l) = self.legacy_try.as_mut() {
                        l.else_start = None;
                    }
                }
                // 3.8-3.10 try/finally: the inline finally body ends with
                // the forward jump over the handler copy — emit and skip
                if lt.has_finally
                    && self.legacy_handler.is_none()
                    && lt.else_start.map_or(false, |es| pos >= es)
                {
                    if let Some(target) = inst.target {
                        if target > pos && target >= lt.handler_start {
                            self.flush_pending_stores();
                            let l = self.legacy_try.take().unwrap();
                            self.restore_legacy_nest();
                            self.push_stmt(Stmt::Try {
                                body: l.body,
                                handlers: l.handlers,
                                orelse: l.orelse,
                                finalbody: l.finalbody,
                            });
                            self.skip_until = Some(target);
                            return;
                        }
                    }
                }
                if self.legacy_handler.is_none() && !lt.has_finally {
                    let in_else = lt
                        .else_start
                        .map_or(false, |es| pos >= es && pos < lt.else_stop);
                    let past_chain = lt
                        .else_start
                        .map_or(true, |es| pos >= es && pos >= lt.else_stop);
                    if let Some(target) = inst.target {
                        // handler normal-exit FORWARD jump landing exactly
                        // where the body's forward jump lands == no else
                        // region (a backward jump there is a loop back edge)
                        if !lt.handlers.is_empty()
                            && lt.else_start == Some(target)
                            && target > pos
                        {
                            if let Some(l) = self.legacy_try.as_mut() {
                                l.else_start = None;
                            }
                        }
                        let onto_loop_back_edge = self
                            .idx_of
                            .get(&target)
                            .and_then(|&ti| self.instrs.get(ti))
                            .map_or(false, |x| {
                                x.is_backward
                                    && matches!(
                                        x.op,
                                        Op::JUMP_ABSOLUTE
                                            | Op::JUMP_BACKWARD
                                            | Op::JUMP_BACKWARD_NO_INTERRUPT
                                    )
                                    && x.target.map_or(false, |t| {
                                        self.blocks.iter().any(|b| {
                                            matches!(b.kind, BlockType::While | BlockType::For)
                                                && (b.start == t
                                                    || (b.cond_end != usize::MAX && b.cond_end == t))
                                        })
                                    })
                            });
                        // a handler chain starting with POP_TOP (no
                        // DUP_TOP+match) is a bare `except:` — the body-end
                        // jump flies over the whole chain, there is no else
                        let bare_chain = self
                            .idx_of
                            .get(&lt.handler_start)
                            .and_then(|&hi2| self.instrs.get(hi2))
                            .map_or(false, |hx| hx.op == Op::POP_TOP);
                        if lt.handlers.is_empty() && lt.else_start.is_none()
                            && target > pos && target > lt.handler_start
                            && !onto_loop_back_edge && !bare_chain
                        {
                            // end of the try body: forward jump over the
                            // handler chain into the else region. Handlers
                            // are parsed inline as execution continues; else
                            // statements are redirected into orelse by
                            // push_stmt until the region ends.
                            let stop = self.next_boundary(target, usize::MAX);
                            if let Some(l) = self.legacy_try.as_mut() {
                                l.else_start = Some(target);
                                l.else_stop = stop;
                            }
                        } else if !lt.handlers.is_empty() && (in_else || (past_chain && target < pos)) {
                            // end of the else region (back edge or jump out):
                            // emit the complete try statement; flush first so
                            // else-region stores land in orelse, not after it
                            self.flush_pending_stores();
                            let l = self.legacy_try.take().unwrap();
                            self.restore_legacy_nest();
                            self.push_stmt(Stmt::Try {
                                body: l.body,
                                handlers: l.handlers,
                                orelse: l.orelse,
                                finalbody: l.finalbody,
                            });
                        }
                    }
                }
            }
            _ => {}
        }
        // chain fully parsed and no else region followed: emit on the next
        // instruction so statement order stays correct
        if let Some(l) = &self.legacy_try {
            if l.chain_done
                && l.else_start.is_none()
                && !l.handlers.is_empty()
                && self.legacy_handler.is_none()
            {
                let l = self.legacy_try.take().unwrap();
                self.flush_pending_stores();
                self.restore_legacy_nest();
                self.push_stmt(Stmt::Try {
                    body: l.body,
                    handlers: l.handlers,
                    orelse: l.orelse,
                    finalbody: l.finalbody,
                });
            }
        }
        let _ = &lt;
    }

    /// Close every block whose `end == pos` (innermost first).
    /// While blocks created for 3.8+ loops have end == start (the cond jump
    /// offset) and must not auto-close there; they are closed by the back
    /// edge.
    fn close_blocks_at(&mut self, pos: usize) {
        // A zero-size rotated-While on top blocks position-based closing;
        // it is closed by its back edge instead.
        if let Some(top) = self.blocks.last() {
            if matches!(top.kind, BlockType::While) && top.start == top.end {
                return;
            }
            if top.kind == BlockType::Main || top.end > pos {
                return;
            }
        }
        // close every non-Main block whose region has ended (possibly
        // earlier than `pos` when control arrived here via a jump)
        while self.blocks.len() > 1 {
            let end = {
                let top = self.blocks.last().unwrap();
                if top.kind == BlockType::Main || top.end > pos {
                    break;
                }
                if matches!(top.kind, BlockType::While) && top.start == top.end {
                    break;
                }
                top.end
            };
            self.force_close_top(end);
        }
    }

    /// Close the topmost block, converting it to statement(s).
    fn force_close_top(&mut self, pos: usize) {
        // stores that happened inside this block must land in it, not in
        // whatever block is open after closing
        self.flush_pending_stores();
        let mut b = self.blocks.pop().unwrap();
        match b.kind {
            BlockType::Main => {
                self.blocks.push(b);
            }
            BlockType::If => {
                let cond = b.cond.take().unwrap_or_else(|| self.name_expr("???"));
                // JUMP_IF_*_OR_POP short-circuit regions merge here into a
                // BoolOp expression instead of an if statement
                if let Some(or_form) = b.short_circuit {
                    if b.stmts.is_empty() {
                        if let Some(Sv::E(right)) = self.stack.last() {
                            let right = right.clone();
                            self.stack.pop();
                            // chained comparison (`a < b < c` via JFOP)
                            if let Some(merged) = merge_chain_compare(&cond, &right) {
                                self.push(merged);
                                if let Some(skip) = b.else_end {
                                    self.skip_until = Some(skip);
                                }
                                return;
                            }
                            let kind = if or_form {
                                BoolOpKind::Or
                            } else {
                                BoolOpKind::And
                            };
                            let mut values = Vec::new();
                            flatten_boolop(cond, kind, &mut values);
                            flatten_boolop(right, kind, &mut values);
                            self.push(Rc::new(Expr::BoolOp { op: kind, values }));
                            return;
                        }
                    }
                }
                let body = std::mem::take(&mut b.stmts);
                // 3.14 `if c: break` shape: PJIT over a break block with a
                // continue on the fall-through — normalize back
                if body.len() == 1 && matches!(body[0], Stmt::Continue) {
                    if let Expr::Unary {
                        op: UnaryOp::Not,
                        operand,
                    } = &*cond
                    {
                        if let Some(&ti0) = self.idx_of.get(&pos) {
                            // the break block may start with the POP_TOP
                            // that drops the loop iterator (3.12 `if c:
                            // break` inside a for)
                            let mut ti = ti0;
                            while matches!(
                                self.instrs.get(ti).map(|x| x.op),
                                Some(Op::POP_TOP) | Some(Op::NOP) | Some(Op::NOT_TAKEN)
                            ) {
                                ti += 1;
                            }
                            let ins = self.instrs[ti];
                            if matches!(
                                ins.op,
                                Op::JUMP | Op::JUMP_FORWARD | Op::JUMP_ABSOLUTE
                            ) {
                                if let Some(t) = ins.target {
                                    if self.find_loop_exit(t).is_some() {
                                        let c = operand.clone();
                                        self.push_stmt(Stmt::If {
                                            cond: c,
                                            body: vec![Stmt::Break],
                                            orelse: Vec::new(),
                                        });
                                        self.skip_until = Some(ins.end());
                                        return;
                                    }
                                }
                            }
                        }
                    }
                }
                if b.else_end.is_none()
                    && body.is_empty()
                    && b.value_merge.is_some()
                    && !self.stack.is_empty()
                {
                    let kind = b.value_merge.unwrap();
                    // value-flow merge: `a and b` / `a or b` chains
                    let right = self.pop_expr();
                    // restore the tested value's polarity (the block cond was
                    // negated for jump-if-true fall-through modeling)
                    let cond = if b.jump_if_true { simplify_not(cond) } else { cond };
                    if let Some(merged) = merge_chain_compare(&cond, &right) {
                        self.push(merged);
                        return;
                    }
                    let mut values = Vec::new();
                    flatten_boolop(cond, kind, &mut values);
                    flatten_boolop(right, kind, &mut values);
                    self.push(Rc::new(Expr::BoolOp { op: kind, values }));
                    return;
                }
                if let Some(else_end) = b.else_end {
                    // value-merge block (COPY+cond jump) with a forward jump:
                    // both branches produce values — merge into chain compare
                    // or ternary and skip the false-path instructions
                    if let Some(_kind) = b.value_merge {
                        if !body.is_empty() {
                            // py2 if/else STATEMENT compiled value-preserving:
                            // body holds the then statements; open the Else
                            // region and let execution collect the else body
                            let is_elif = self.starts_with_cond_jump(pos, else_end);
                            let real_end = if is_elif {
                                else_end
                            } else {
                                self.next_boundary(pos, else_end)
                            };
                            let mut else_blk = Block::new(BlockType::Else, pos, real_end);
                            else_blk.cond = Some(cond);
                            else_blk.is_elif = is_elif;
                            self.pending_then.push(body);
                            self.blocks.push(else_blk);
                            return;
                        }
                        if body.is_empty() {
                            if let Some(Sv::E(v)) = self.stack.last() {
                                let v = v.clone();
                                if let Some(merged) = merge_chain_compare(&cond, &v) {
                                    self.stack.pop();
                                    self.push(merged);
                                    self.skip_chain_else_arm(else_end);
                                    return;
                                }
                                // A ternary needs the tested value still on
                                // the stack right under the arm value (the
                                // py2 peek-style JUMP_IF_* if-shape and the
                                // 3.12+ COPY both retain it). When the arm's
                                // POP_TOP already dropped the tested value
                                // (py2 / PJFP-style short circuit), a single
                                // arm value is `a and b` / `a or b`.
                                let tested_retained = self
                                    .stack
                                    .get(self.stack.len().wrapping_sub(2))
                                    .map_or(false, |sv| {
                                        matches!(sv, Sv::E(e) if expr_eq(e, &cond))
                                    });
                                if self.stack.len() >= 2 && tested_retained {
                                    self.stack.pop();
                                    let then_val = self.pop_expr();
                                    self.push(Rc::new(Expr::Ternary {
                                        cond,
                                        then_expr: then_val,
                                        else_expr: v,
                                    }));
                                    self.skip_chain_else_arm(else_end);
                                    return;
                                }
                                // py2 short-circuit `a and b` / `a or b`:
                                // the cond was popped by the branch POP_TOP
                                // and the fall-through produced one value
                                let kind = b.value_merge.unwrap();
                                let cond = if b.jump_if_true {
                                    simplify_not(cond)
                                } else {
                                    cond
                                };
                                self.stack.pop();
                                let mut values = Vec::new();
                                flatten_boolop(cond, kind, &mut values);
                                flatten_boolop(v, kind, &mut values);
                                self.push(Rc::new(Expr::BoolOp { op: kind, values }));
                                self.skip_chain_else_arm(else_end);
                                return;
                            }
                        }
                    }
                    let is_elif = self.starts_with_cond_jump(pos, else_end);
                    let real_end = if is_elif {
                        else_end
                    } else {
                        self.next_boundary(pos, else_end)
                    };
                    let mut else_blk = Block::new(BlockType::Else, pos, real_end);
                    else_blk.cond = Some(cond);
                    else_blk.is_elif = is_elif;
                    self.pending_then.push(body);
                    self.blocks.push(else_blk);
                } else if b.folded_exit {
                    // folded chain exit: an elif/else region starts right
                    // here and runs until the next folded exit (or the
                    // enclosing structure closes it)
                    let mut else_blk = Block::new(BlockType::Else, pos, usize::MAX);
                    else_blk.cond = Some(cond);
                    else_blk.folded_exit = true;
                    self.pending_then.push(body);
                    self.blocks.push(else_blk);
                } else {
                    self.push_stmt(Stmt::If {
                        cond,
                        body,
                        orelse: Vec::new(),
                    });
                }
            }
            BlockType::Else => {
                let cond = b.cond.take().unwrap_or_else(|| self.name_expr("???"));
                let mut orelse = std::mem::take(&mut b.stmts);
                let body = self.pending_then.pop().unwrap_or_default();
                if body.is_empty() && orelse.is_empty() {
                    // chained comparison merge: one value on the stack that
                    // shares an operand with the condition (`a < b < c`)
                    if let Some(Sv::E(v)) = self.stack.last() {
                        let v = v.clone();
                        if let Some(merged) = merge_chain_compare(&cond, &v) {
                            self.stack.pop();
                            self.push(merged);
                            return;
                        }
                    }
                    // conditional expression: both branches are pure values
                    if self.stack.len() >= 2 {
                        let else_val = self.pop_expr();
                        let then_val = self.pop_expr();
                        self.push(Rc::new(Expr::Ternary {
                            cond,
                            then_expr: then_val,
                            else_expr: else_val,
                        }));
                        return;
                    }
                }
                if b.folded_exit && body.is_empty() && orelse.len() == 1 {
                    if let Stmt::If { cond: c2, body: t2, orelse: e2 } = orelse.pop().unwrap() {
                        // folded elif link: the region held the next chain
                        // link — re-arm so a following final-else region
                        // receives the whole accumulated chain
                        self.pending_then.push(t2);
                        let mut next_else = Block::new(BlockType::Else, pos, usize::MAX);
                        next_else.cond = Some(c2);
                        next_else.folded_exit = true;
                        next_else.is_elif = true;
                        // e2 (any deeper chain) is preserved by pushing it
                        // into the new block when non-empty
                        next_else.stmts = e2;
                        self.blocks.push(next_else);
                        let _ = cond;
                        return;
                    }
                }
                // Nesting the else body preserves full fidelity; the
                // codegen renders `else: <single if>` as `elif` anyway
                // (which also covers folded elif chains).
                self.push_stmt(Stmt::If { cond, body, orelse });
            }
            BlockType::While => {
                let cond = b.cond.take().unwrap_or_else(|| self.name_expr("True"));
                let body = std::mem::take(&mut b.stmts);
                if let Some(else_end) = b.loop_else_end {
                    self.pending_loop.push((Some(cond), None, None, body, false));
                    let else_blk = Block::new(BlockType::WhileElse, pos, else_end);
                    self.blocks.push(else_blk);
                } else {
                    self.push_stmt(Stmt::While {
                        cond,
                        body,
                        orelse: Vec::new(),
                    });
                }
            }
            BlockType::For => {
                let target = b.target.take().unwrap_or_else(|| self.name_expr("_"));
                let iter = b.iter.take().unwrap_or_else(|| self.name_expr("???"));
                let body = std::mem::take(&mut b.stmts);
                let is_async = b.is_async;
                let probed_else = if b.loop_else_end.is_none()
                    && b.for_setup_end.is_none()
                    && pos == b.end
                {
                    self.probe_for_else(pos)
                } else {
                    None
                };
                if let Some(else_end) = b.loop_else_end.or(probed_else) {
                    self.pending_loop
                        .push((None, Some(target), Some(iter), body, is_async));
                    let else_blk = Block::new(BlockType::ForElse, pos, else_end);
                    self.blocks.push(else_blk);
                } else if let Some(se) = b.for_setup_end.filter(|se| *se > b.end) {
                    // SETUP_LOOP-era for-else: the exhaustion exit (b.end)
                    // closed the body; the else region runs to the loop pop
                    self.pending_loop
                        .push((None, Some(target), Some(iter), body, is_async));
                    let else_blk = Block::new(BlockType::ForElse, b.end, se);
                    self.blocks.push(else_blk);
                } else {
                    self.push_stmt(Stmt::For {
                        target,
                        iter,
                        body,
                        orelse: Vec::new(),
                        is_async,
                    });
                }
            }
            BlockType::WhileElse => {
                let orelse = std::mem::take(&mut b.stmts);
                let (cond, _, _, body, _) = self.pending_loop.pop().unwrap_or_default();
                self.push_stmt(Stmt::While {
                    cond: cond.unwrap_or_else(|| self.name_expr("True")),
                    body,
                    orelse,
                });
            }
            BlockType::ForElse => {
                let orelse = std::mem::take(&mut b.stmts);
                let (_, target, iter, body, is_async) =
                    self.pending_loop.pop().unwrap_or_default();
                self.push_stmt(Stmt::For {
                    target: target.unwrap_or_else(|| self.name_expr("_")),
                    iter: iter.unwrap_or_else(|| self.name_expr("???")),
                    body,
                    orelse,
                    is_async,
                });
            }
            BlockType::Try => {
                let body = std::mem::take(&mut b.stmts);
                // 3.11+ exception-table-driven try: body done, handlers are
                // parsed out-of-line; else/finally emission happens when the
                // protected region ends (or immediately without finally)
                if let Some(tc) = self.active_try.take() {
                    self.pending_try_body.push(body);
                    let cover = tc.region_end;
                    if cover > pos {
                        self.pending_try_ctx = Some(tc);
                    } else {
                        self.emit_try_tail(tc, pos);
                    }
                    return;
                }
                if let Some(finally_target) = b.finally_target {
                    // Either except handlers follow (pushed by the closing
                    // jump / exception-table flow) or this is try/finally.
                    let handlers = std::mem::take(&mut self.pending_handlers);
                    self.pending_try_body.push(body);
                    self.pending_try_handlers.push(handlers);
                    let mut fin = Block::new(BlockType::Finally, pos, usize::MAX);
                    fin.finally_target = Some(finally_target);
                    self.blocks.push(fin);
                } else if self.version.at_least(3, 11) {
                    let handlers = std::mem::take(&mut self.pending_handlers);
                    self.push_stmt(Stmt::Try {
                        body,
                        handlers,
                        orelse: Vec::new(),
                        finalbody: Vec::new(),
                    });
                } else {
                    // pre-3.11: handlers live out-of-line starting at `pos`;
                    // defer emission until the chain completes
                    // 3.8-3.10 try/finally: the out-of-line region is a
                    // finally COPY (no except dispatch, ends in RERAISE /
                    // END_FINALLY) and the real finally body runs INLINE
                    // right after this POP_BLOCK
                    let mut has_finally = false;
                    let mut inline_end = usize::MAX;
                    if self.version.at_least(3, 8) {
                        if let Some(&hi) = self.idx_of.get(&pos) {
                            for ins in self.instrs[hi..].iter().take(64) {
                                match ins.op {
                                    Op::DUP_TOP
                                    | Op::JUMP_IF_NOT_EXC_MATCH
                                    | Op::POP_EXCEPT => break,
                                    Op::COMPARE_OP
                                        if cmp_from_index(compare_op_index(
                                            ins.arg as u32,
                                            self.version,
                                        )) == CmpOp::ExceptionMatch =>
                                    {
                                        break;
                                    }
                                    Op::RERAISE | Op::END_FINALLY => {
                                        has_finally = true;
                                        break;
                                    }
                                    _ => {}
                                }
                            }
                        }
                        if has_finally {
                            // the inline finally body runs from right after
                            // the POP_BLOCK to its RETURN (function-tail
                            // finally) or the forward jump over the handler
                            // copy — the block end is the handler start,
                            // which lies PAST the inline region
                            for ins in self.instrs.iter() {
                                if ins.offset < self.cur_next {
                                    continue;
                                }
                                match ins.op {
                                    Op::RETURN_VALUE | Op::RETURN_CONST => {
                                        inline_end = ins.offset;
                                        break;
                                    }
                                    Op::JUMP_FORWARD | Op::JUMP_ABSOLUTE => {
                                        if ins.target.unwrap_or(0) > pos {
                                            inline_end = ins.offset;
                                            break;
                                        }
                                    }
                                    _ => {}
                                }
                            }
                        }
                    }
                    self.legacy_try = Some(LegacyTry {
                        body,
                        handlers: Vec::new(),
                        orelse: Vec::new(),
                        finalbody: Vec::new(),
                        handler_start: pos,
                        has_finally,
                        else_start: if has_finally {
                            Some(self.cur_next)
                        } else {
                            None
                        },
                        else_stop: inline_end,
                        chain_done: false,
                    });
                }
            }
            BlockType::TryElse => {
                // try body finished; else clause runs until the finally
                let orelse = std::mem::take(&mut b.stmts);
                let body = self.pending_try_body.pop().unwrap_or_default();
                let handlers = self.pending_try_handlers.pop().unwrap_or_default();
                let mut fin = Block::new(BlockType::Finally, pos, usize::MAX);
                fin.finally_target = b.finally_target;
                self.pending_try_body.push(body);
                self.pending_try_handlers.push(handlers);
                self.pending_try_orelse.push(orelse);
                self.blocks.push(fin);
            }
            BlockType::Except => {
                let handler = ExceptHandler {
                    type_: b.handler_type.take(),
                    name: b.handler_name.take(),
                    body: std::mem::take(&mut b.stmts),
                };
                self.pending_handlers.push(handler);
            }
            BlockType::Finally => {
                let finalbody = std::mem::take(&mut b.stmts);
                let body = self.pending_try_body.pop().unwrap_or_default();
                let handlers = self.pending_try_handlers.pop().unwrap_or_default();
                let orelse = self.pending_try_orelse.pop().unwrap_or_default();
                if finalbody.iter().all(|s| matches!(s, Stmt::Pass)) && handlers.is_empty() {
                    // bare container close — emit body directly
                    self.push_stmt_all(body);
                    self.push_stmt_all(orelse);
                } else {
                    self.push_stmt(Stmt::Try {
                        body,
                        handlers,
                        orelse,
                        finalbody,
                    });
                }
            }
            BlockType::With => {
                let items = match b.with_item.take() {
                    Some(item) => vec![item],
                    None => self.pending_with.pop().unwrap_or_else(|| {
                        vec![WithItem {
                            ctx: self.name_expr("???"),
                            target: None,
                        }]
                    }),
                };
                let stmt = Stmt::With {
                    items,
                    body: std::mem::take(&mut b.stmts),
                    is_async: b.is_async,
                };
                self.push_stmt(stmt);
            }
            BlockType::Container => {
                if !b.stmts.is_empty() {
                    let stmts = std::mem::take(&mut b.stmts);
                    self.push_stmt_all(stmts);
                }
            }
        }
    }

    fn flush_stack(&mut self) {
        // Leftover stack values at stream end are simulation artifacts
        // (iterator bookkeeping, saved locals from inline comprehensions);
        // only import markers still carry statement meaning.
        while let Some(sv) = self.stack.pop() {
            if let Sv::ImportModule { module, .. } = sv {
                self.push_stmt(Stmt::Import { names: vec![(module, None)] });
            }
        }
    }

    // ----- stack helpers -----

    fn push(&mut self, e: ExprRef) {
        self.stack.push(Sv::E(e));
    }

    fn pop(&mut self) -> Option<Sv> {
        self.stack.pop()
    }

    fn pop_expr(&mut self) -> ExprRef {
        loop {
            match self.stack.pop() {
                Some(Sv::E(e)) => return e,
                Some(Sv::Null) => continue,
                Some(other) => {
                    // keep import markers on the stack; anything else is
                    // rendered as None so the output stays compilable
                    if matches!(other, Sv::ImportModule { .. } | Sv::ImportFrom { .. }) {
                        self.stack.push(other);
                        self.clean = false;
                        return Rc::new(Expr::Const(Rc::new(PyObject::None)));
                    }
                    self.clean = false;
                    return Rc::new(Expr::Const(Rc::new(PyObject::None)));
                }
                None => {
                    self.clean = false;
                    if std::env::var("PYCDC_TRACE").is_ok() {
                        eprintln!("AW UNDERFLOW pop_expr at {} in {:?}", self.cur_offset, self.code.name);
                    }
                    return Rc::new(Expr::Const(Rc::new(PyObject::None)));
                }
            }
        }
    }

    fn pop_expr_raw(&mut self) -> Option<Sv> {
        self.stack.pop()
    }

    /// Restore PEP 8 private names: inside class C the compiler rewrites
    /// `__x` to `_C__x`. The decompiler walks class bodies with the class
    /// name on `class_scope`, so reverse it here.
    fn unmangle(&self, name: &str) -> String {
        if name.starts_with('_') && !name.ends_with("__") {
            for cls in self.class_scope.iter().rev() {
                let ident = cls.trim_start_matches('_');
                if ident.is_empty() {
                    continue;
                }
                let prefix = format!("_{}__", ident);
                if name.starts_with(&prefix) && name.len() > prefix.len() {
                    return format!("__{}", &name[prefix.len()..]);
                }
            }
        }
        name.to_string()
    }

    /// Like `pop_expr`, but reports whether a NULL marker was skipped on
    /// the way to the expression (3.13 pushes NULL above the callable).
    fn pop_expr_skipped(&mut self) -> (ExprRef, bool) {
        let mut skipped = false;
        loop {
            match self.stack.pop() {
                Some(Sv::E(e)) => return (e, skipped),
                Some(Sv::Null) => {
                    skipped = true;
                    continue;
                }
                Some(other) => {
                    if matches!(other, Sv::ImportModule { .. } | Sv::ImportFrom { .. }) {
                        self.stack.push(other);
                        self.clean = false;
                        return (Rc::new(Expr::Const(Rc::new(PyObject::None))), skipped);
                    }
                    self.clean = false;
                    return (Rc::new(Expr::Const(Rc::new(PyObject::None))), skipped);
                }
                None => {
                    self.clean = false;
                    return (Rc::new(Expr::Const(Rc::new(PyObject::None))), skipped);
                }
            }
        }
    }

    fn const_expr(&mut self, idx: usize) -> ExprRef {
        match self.code.consts.get(idx) {
            Some(o) => Rc::new(Expr::Const(o.clone())),
            None => {
                self.clean = false;
                self.name_expr(format!("/*bad-const-{idx}*/"))
            }
        }
    }

    fn name_expr(&self, name: impl Into<String>) -> ExprRef {
        Rc::new(Expr::Name(name.into()))
    }

    fn const_name(&self, idx: usize) -> String {
        let n = self
            .code
            .names
            .get(idx)
            .and_then(|n| match &**n {
                PyObject::Str(s) => Some(s.clone()),
                PyObject::Bytes(b) => Some(String::from_utf8_lossy(b).into_owned()),
                _ => None,
            })
            .unwrap_or_else(|| format!("/*bad-name-{idx}*/"));
        self.unmangle(&n)
    }

    fn local_name(&self, idx: usize) -> String {
        self.code
            .varnames
            .get(idx)
            .map(|n| sanitize_varname(n))
            .unwrap_or_else(|| format!("/*bad-local-{idx}*/"))
    }

    /// 2.6 comprehension accumulator temps (`_[1]` …) are compiler
    /// synthetic names — no source statement ever references them
    fn is_comp_temp_name(&self, n: &str) -> bool {
        self.version.major == 2 && n.starts_with("_[") && n.ends_with(']')
    }

    fn push_stmt(&mut self, stmt: Stmt) {
        // any other statement flushes a pending same-line store group first
        // to preserve source order
        if !self.flushing && !self.pending_stores.is_empty() {
            self.flushing = true;
            self.flush_pending_stores();
            self.flushing = false;
        }
        self.last_flush_offset = self.cur_offset;
        if let Some(h) = self.legacy_handler.as_mut() {
            if self.blocks.len() <= h.block_depth {
                h.body.push(stmt);
                return;
            }
            // a block (If/While/...) opened inside the handler collects the
            // statement; it lands in the handler body when the block closes
        }
        // statements executed inside a collected try-else region belong to
        // the Try's orelse, not to the enclosing block; a 3.8-3.10 inline
        // finally body collects into finalbody
        if let Some(lt) = self.legacy_try.as_mut() {
            if let Some(es) = lt.else_start {
                if self.cur_offset >= es && self.cur_offset < lt.else_stop {
                    if lt.has_finally {
                        lt.finalbody.push(stmt);
                    } else {
                        lt.orelse.push(stmt);
                    }
                    return;
                }
            }
        }
        if let Some(top) = self.blocks.last_mut() {
            top.stmts.push(stmt);
        }
    }

    fn push_stmt_all(&mut self, stmts: Vec<Stmt>) {
        if let Some(top) = self.blocks.last_mut() {
            top.stmts.extend(stmts);
        }
    }

    fn pop_n_exprs(&mut self, n: usize) -> Vec<ExprRef> {
        let mut out = Vec::with_capacity(n);
        for _ in 0..n {
            out.push(self.pop_expr());
        }
        out.reverse();
        out
    }

    fn mark_unclean(&mut self) {
        self.clean = false;
    }

    fn unimplemented(&mut self, inst: &Instruction, what: &str) {
        self.clean = false;
        let text = format!(
            "/* {what}: {} {} @{} */",
            self.table.name(inst.opcode),
            if inst.has_arg {
                inst.arg.to_string()
            } else {
                String::new()
            },
            inst.offset
        );
        self.push_stmt(Stmt::Unimplemented(text));
    }
}

#[allow(dead_code)]
fn short(sv: &Sv) -> String {
    match sv {
        Sv::Null => "null".into(),
        Sv::ImportModule { module, .. } => format!("import:{module}"),
        Sv::ImportFrom { module, name, .. } => format!("from:{module}:{name}"),
        Sv::E(_) => "expr".into(),
    }
}

// =====================  instruction dispatch  =====================

use crate::opcode::Op;

impl<'a> Ctx<'a> {
    /// Execute one instruction. Returns false when the instruction stream
    /// should stop being processed (unconditional exit).
    fn exec(&mut self, inst: &Instruction) -> bool {
        let arg = inst.arg;
        let cont = match inst.op {
            // ---------- no-ops / housekeeping ----------
            Op::NOP
            | Op::CACHE
            | Op::RESUME
            | Op::RESUME_CHECK
            | Op::PRECALL
            | Op::COPY_FREE_VARS
            | Op::MAKE_CELL
            | Op::SETUP_ANNOTATIONS
            | Op::EXTENDED_ARG
            | Op::GEN_START
            | Op::ASYNC_GEN_WRAP
            | Op::SET_LINENO
            | Op::STOP_CODE
            | Op::PUSH_EXC_INFO
            | Op::ANNOTATIONS_PLACEHOLDER
            | Op::JUMP_BACKWARD_NO_INTERRUPT
            | Op::NOT_TAKEN
            | Op::BEGIN_FINALLY => true,

            // ---------- constants / names ----------
            Op::LOAD_CONST => {
                if let Some(PyObject::Code(c)) =
                    self.code.consts.get(arg as usize).map(|o| &**o)
                {
                    self.recent_code_const = Some(c.clone());
                }
                let e = self.const_expr(arg as usize);
                self.push(e);
                true
            }
            Op::RETURN_CONST => {
                let e = self.const_expr(arg as usize);
                self.emit_return(Some(e));
                !matches!(self.blocks.last().map(|b| b.kind), Some(BlockType::Main))
                    || self.legacy_try.is_some()
            }
            Op::LOAD_NAME => {
                let n = self.const_name(arg as usize);
                // 2.6 synthetic temp: inside an inline comprehension the
                // accumulator reload is tracked by the comp model; outside
                // (with-as target) the stashed value is reloaded
                if self.is_comp_temp_name(&n) {
                    if self.inline_comp.is_some() {
                        return true;
                    }
                    if let Some(v) = self.py26_temps.get(&n).cloned() {
                        self.stack.push(v);
                    } else {
                        self.push(self.name_expr(n));
                    }
                    return true;
                }
                self.push(self.name_expr(n));
                true
            }
            Op::LOAD_FAST
            | Op::LOAD_FAST_CHECK
            | Op::LOAD_FAST_AND_CLEAR
            | Op::LOAD_FAST_BORROW => {
                let n = self.local_name(arg as usize);
                self.push(self.name_expr(n));
                true
            }
            Op::LOAD_FAST_BORROW_LOAD_FAST_BORROW => {
                // 3.14: loads two locals, (arg >> 4) first then (arg & 0xF)
                let a = self.local_name(((arg >> 4) & 0xF) as usize);
                let b = self.local_name((arg & 0xF) as usize);
                self.push(self.name_expr(a));
                self.push(self.name_expr(b));
                true
            }
            Op::LOAD_FAST_LOAD_FAST => {
                let a = self.local_name((arg >> 4) as usize);
                let b = self.local_name((arg & 0xF) as usize);
                self.push(self.name_expr(a));
                self.push(self.name_expr(b));
                true
            }
            Op::STORE_FAST | Op::STORE_FAST_MAYBE_NULL => {
                let n = self.local_name(arg as usize);
                if self.walrus_at_name(inst, &n) {
                    let val = self.pop_expr();
                    self.pop(); // the duplicated original
                    self.push(Rc::new(Expr::Named {
                        target: self.name_expr(n),
                        value: val,
                    }));
                    return true;
                }
                let val = self.pop_store_value();
                self.emit_store_sv(self.name_expr(n), val);
                true
            }
            Op::STORE_FAST_LOAD_FAST => {
                let store_idx = (arg >> 4) as usize;
                let load_idx = (arg & 0xF) as usize;
                let val = self.pop_store_value();
                let n = self.local_name(store_idx);
                self.emit_store_sv(self.name_expr(n.clone()), val);
                let ln = self.local_name(load_idx);
                self.push(self.name_expr(ln));
                true
            }
            Op::STORE_FAST_STORE_FAST => {
                // first store (arg >> 4) consumes the TOP of stack
                let a = ((arg >> 4) & 0xF) as usize;
                let b = (arg & 0xF) as usize;
                let val_a = self.pop_store_value();
                let val_b = self.pop_store_value();
                let na = self.local_name(a);
                self.emit_store_sv(self.name_expr(na), val_a);
                let nb = self.local_name(b);
                self.emit_store_sv(self.name_expr(nb), val_b);
                true
            }
            Op::DELETE_FAST => {
                let n = self.local_name(arg as usize);
                self.emit_delete(self.name_expr(n));
                true
            }
            Op::LOAD_GLOBAL => {
                let idx = if self.version.at_least(3, 11) {
                    (arg >> 1) as usize
                } else {
                    arg as usize
                };
                let n = self.const_name(idx);
                if arg & 1 != 0 {
                    if self.version.at_least(3, 14) {
                        // 3.14 CALL slots: [callable, NULL, args] — value
                        // first, NULL marker on top
                        self.push(self.name_expr(n));
                        self.stack.push(Sv::Null);
                    } else {
                        // 3.11-3.13: NULL below the value
                        self.stack.push(Sv::Null);
                        self.push(self.name_expr(n));
                    }
                } else {
                    self.push(self.name_expr(n));
                }
                true
            }
            Op::STORE_GLOBAL => {
                let n = self.const_name(arg as usize);
                if !self.globals.contains(&n) {
                    self.globals.push(n.clone());
                }
                if self.walrus_at_name(inst, &n) {
                    // a walrus inside a comprehension stores to the
                    // enclosing scope (STORE_GLOBAL at module level)
                    let val = self.pop_expr();
                    self.pop(); // the duplicated original
                    self.push(Rc::new(Expr::Named {
                        target: self.name_expr(n),
                        value: val,
                    }));
                    return true;
                }
                let val = self.pop_store_value();
                self.emit_store_sv(self.name_expr(n), val);
                true
            }
            Op::DELETE_GLOBAL => {
                let n = self.const_name(arg as usize);
                if !self.globals.contains(&n) {
                    self.globals.push(n.clone());
                }
                self.emit_delete(self.name_expr(n));
                true
            }
            Op::STORE_NAME => {
                let n = self.const_name(arg as usize);
                // 2.6 inline comprehension accumulator stash (`_[N]`):
                // synthetic name, no source statement
                if self.is_comp_temp_name(&n) {
                    let v = self.pop_store_value();
                    self.py26_temps.insert(n.clone(), v);
                    self.last_py26_temp = Some(n);
                    return true;
                }
                if self.walrus_at_name(inst, &n) {
                    let val = self.pop_expr();
                    self.pop(); // the duplicated original
                    self.push(Rc::new(Expr::Named {
                        target: self.name_expr(n),
                        value: val,
                    }));
                    return true;
                }
                let val = self.pop_store_value();
                self.emit_store_sv(self.name_expr(n), val);
                true
            }
            Op::DELETE_NAME => {
                let n = self.const_name(arg as usize);
                if self.is_comp_temp_name(&n) {
                    self.py26_temps.remove(&n);
                    return true;
                }
                self.emit_delete(self.name_expr(n));
                true
            }
            Op::LOAD_DEREF | Op::LOAD_CLOSURE | Op::LOAD_CLASSDEREF => {
                let n = self
                    .code
                    .deref_name(arg as usize)
                    .unwrap_or("/*bad-deref*/")
                    .to_string();
                self.push(self.name_expr(n));
                true
            }
            Op::STORE_DEREF => {
                let n = self
                    .code
                    .deref_name(arg as usize)
                    .unwrap_or("/*bad-deref*/")
                    .to_string();
                // STORE_DEREF on a freevar (not cellvar) implies `nonlocal`
                let is_free = self.code.freevars.iter().any(|f| *f == n)
                    && self.version.at_least(3, 0)
                    && self.code.name != "<module>";
                if is_free && !self.nonlocals.contains(&n) {
                    self.nonlocals.push(n.clone());
                }
                if self.walrus_at_name(inst, &n) {
                    let val = self.pop_expr();
                    self.pop(); // the duplicated original
                    self.push(Rc::new(Expr::Named {
                        target: self.name_expr(n),
                        value: val,
                    }));
                    return true;
                }
                let val = self.pop_store_value();
                self.emit_store_sv(self.name_expr(n), val);
                true
            }
            Op::DELETE_DEREF => {
                let n = self
                    .code
                    .deref_name(arg as usize)
                    .unwrap_or("/*bad-deref*/")
                    .to_string();
                self.emit_delete(self.name_expr(n));
                true
            }
            Op::LOAD_LOCALS => {
                self.push(self.name_expr("locals()"));
                true
            }
            Op::STORE_LOCALS => {
                // py2 class body: locals() -> class dict
                self.pop();
                true
            }
            Op::LOAD_BUILD_CLASS => {
                self.push(self.name_expr("__build_class__"));
                true
            }
            Op::LOAD_ASSERTION_ERROR => {
                self.push(self.name_expr("AssertionError"));
                true
            }
            Op::LOAD_SMALL_INT => {
                // 3.14+: pushes the small int `arg`
                self.push(Rc::new(Expr::Const(Rc::new(PyObject::Int(arg as i32)))));
                true
            }
            Op::LOAD_COMMON_CONSTANT => {
                // 3.14+: 0 = None; 3/4 = built-in all/any, emitted only by
                // the inline all/any-genexpr optimization guard:
                //   <all>; COPY 1; LOAD_COMMON_CONSTANT all; IS_OP 0;
                //   PJIF Lslow; NOT_TAKEN; POP_TOP; <inline genexpr loop
                //   with early exits>; Lslow: PUSH_NULL; <genexpr>;
                //   CALL 0; CALL 1  — both paths merge with one value.
                // Divert to the slow path: it renders the plain
                // `all(<genexpr>)` call via the existing machinery.
                if (arg == 3 || arg == 4) && self.version.at_least(3, 14) {
                    if let Some(slow) = self.inline_all_any_slow_path(arg == 3) {
                        // drop the COPY 1 duplicate; the slow path expects
                        // just the callable
                        self.pop();
                        self.skip_until = Some(slow);
                        return true;
                    }
                }
                if arg == 0 {
                    self.push(Rc::new(Expr::Const(Rc::new(PyObject::None))));
                } else {
                    self.mark_unclean();
                    self.push(Rc::new(Expr::Const(Rc::new(PyObject::None))));
                }
                true
            }

            // ---------- attributes ----------
            Op::LOAD_ATTR | Op::LOAD_METHOD => {
                let (idx, is_method) = match inst.op {
                    Op::LOAD_METHOD => (arg as usize, true),
                    _ if self.version.at_least(3, 12) => {
                        ((arg >> 1) as usize, arg & 1 != 0)
                    }
                    _ => (arg as usize, false),
                };
                let attr = self.unmangle(&self.const_name(idx));
                let value = self.pop_expr();
                let e: ExprRef = Rc::new(Expr::Attribute {
                    value: value.clone(),
                    attr,
                });
                if is_method {
                    if self.version.at_least(3, 14) {
                        // 3.14: [method, self_or_null] — marker on top
                        self.push(e);
                        self.push(value);
                    } else if self.version.at_least(3, 11) {
                        // 3.11-3.13: [self_or_null, method] — method on top
                        self.push(value);
                        self.push(e);
                    } else {
                        // 3.7-3.10: [method, self_or_null] — marker on top
                        self.push(e);
                        self.push(value);
                    }
                } else {
                    self.push(e);
                }
                true
            }
            Op::LOAD_SUPER_ATTR => {
                let idx = if self.version.at_least(3, 12) {
                    (arg >> 2) as usize
                } else {
                    arg as usize
                };
                let attr = self.unmangle(&self.const_name(idx));
                let _attr_name = self.pop_expr();
                let _cls = self.pop_expr();
                let _self_e = self.pop_expr();
                let e: ExprRef = Rc::new(Expr::Attribute {
                    value: self.name_expr("super()"),
                    attr,
                });
                if self.version.at_least(3, 12) && arg & 1 != 0 {
                    self.stack.push(Sv::Null);
                }
                self.push(e);
                true
            }
            Op::LOAD_SPECIAL => {
                // 3.14: the arg indexes a fixed special-method table
                // ['__enter__','__exit__','__aenter__','__aexit__'],
                // NOT co_names
                let attr = ["__enter__", "__exit__", "__aenter__", "__aexit__"]
                    .get(arg as usize)
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| self.const_name(arg as usize));
                // 3.14 with header (BEFORE_WITH/BEFORE_ASYNC_WITH are gone):
                //   ctx; COPY 1; LOAD_SPECIAL __exit__; SWAP 2; SWAP 3;
                //   LOAD_SPECIAL __enter__; CALL 0; [GET_AWAITABLE..END_SEND]
                // Recognize it at the exit special: swallow the whole
                // header, open the With block, and leave the enter-result
                // placeholder for the `as` store / POP_TOP.
                if self.version.at_least(3, 14)
                    && (attr == "__exit__" || attr == "__aexit__")
                    && self
                        .idx_of
                        .get(&inst.offset)
                        .and_then(|&si| self.instrs.get(si - 1))
                        .map_or(false, |p| p.op == Op::COPY && p.arg == 1)
                {
                    let is_async = attr == "__aexit__";
                    let ctx_e = self.pop_expr();
                    let _dup = self.pop_expr(); // the COPY 1 duplicate
                    self.with_exits += 1;
                    // stand-in for the __exit__ pair the VM keeps under the
                    // body: 3.14 CALL pops [callable, NULL] marker-first, so
                    // model both slots — the exit CALL then finds the
                    // None-const callable the swallow recognizer expects
                    self.push(Rc::new(Expr::Const(Rc::new(PyObject::None))));
                    self.stack.push(Sv::Null);
                    let item = WithItem {
                        ctx: ctx_e,
                        target: None,
                    };
                    let start = self.cur_offset;
                    let end = self
                        .with_regions
                        .get(&start)
                        .copied()
                        .or_else(|| {
                            // the protected body starts after the enter
                            // protocol (async) or enter CALL (sync): take
                            // the first with region at/after the header
                            self.with_regions
                                .iter()
                                .filter(|(k, _)| **k >= start)
                                .min_by_key(|(k, _)| *k)
                                .map(|(_, v)| *v)
                        })
                        .unwrap_or(usize::MAX);
                    let mut wb = Block::new(BlockType::With, start, end);
                    wb.is_async = is_async;
                    wb.with_item = Some(item);
                    self.blocks.push(wb);
                    self.push(self.name_expr(WITH_RESULT_PLACEHOLDER));
                    // skip the SWAPs, enter special + CALL, and (async) the
                    // await protocol; stop AT the instruction that consumes
                    // the enter result (STORE as-target / POP_TOP) or at the
                    // body's first instruction
                    if let Some(&si) = self.idx_of.get(&inst.offset) {
                        let mut saw_enter_call = false;
                        let mut skip_to = None;
                        for k in si + 1..self.instrs.len().min(si + 26) {
                            match self.instrs[k].op {
                                Op::END_SEND => {
                                    skip_to = Some(self.instrs[k].end());
                                    break;
                                }
                                Op::CALL if saw_enter_call => {}
                                Op::CALL => saw_enter_call = true,
                                Op::STORE_FAST
                                | Op::STORE_NAME
                                | Op::STORE_DEREF
                                | Op::POP_TOP
                                    if saw_enter_call || !is_async =>
                                {
                                    skip_to = Some(self.instrs[k].offset);
                                    break;
                                }
                                Op::RETURN_VALUE | Op::RETURN_CONST => break,
                                _ => {}
                            }
                        }
                        if let Some(st) = skip_to {
                            self.skip_until = Some(st);
                        }
                    }
                    return true;
                }
                let value = self.pop_expr();
                self.push(Rc::new(Expr::Attribute { value, attr }));
                true
            }
            Op::STORE_ATTR => {
                // STORE_ATTR uses the plain name index in all versions
                let idx = arg as usize;
                let attr = self.unmangle(&self.const_name(idx));
                // all CPython versions push value first, owner on top
                let obj = self.pop_expr();
                let val = self.pop_expr();
                let target: ExprRef = Rc::new(Expr::Attribute { value: obj, attr });
                self.emit_store(target, val);
                true
            }
            Op::DELETE_ATTR => {
                let attr = self.unmangle(&self.const_name(arg as usize));
                let obj = self.pop_expr();
                let target: ExprRef = Rc::new(Expr::Attribute { value: obj, attr });
                self.emit_delete(target);
                true
            }

            // ---------- subscripts / slices ----------
            Op::BINARY_SUBSCR => {
                let idx = self.pop_expr();
                let val = self.pop_expr();
                // 3.14 builds extended slices via `slice(...)` calls or
                // marshalled slice constants
                let idx = normalize_slice_call(idx);
                self.push(Rc::new(Expr::Subscript { value: val, index: idx }));
                true
            }
            Op::BINARY_SLICE => {
                let stop = self.pop_expr();
                let start = self.pop_expr();
                let val = self.pop_expr();
                let slice = Rc::new(Expr::Slice(Box::new(SliceExpr {
                    start: none_if_const_none(start),
                    stop: none_if_const_none(stop),
                    step: None,
                })));
                self.push(Rc::new(Expr::Subscript {
                    value: val,
                    index: slice,
                }));
                true
            }
            Op::STORE_SUBSCR => {
                // All versions: obj and sub on top, value below.
                // <=3.10: [value, obj, sub] (sub top); 3.11+: [sub, obj, value]
                let (val, obj, idx) = if self.version.at_least(3, 11) {
                    let idx = self.pop_expr();
                    let obj = self.pop_expr();
                    let val = self.pop_expr();
                    (val, obj, idx)
                } else {
                    let idx = self.pop_expr();
                    let obj = self.pop_expr();
                    let val = self.pop_expr();
                    (val, obj, idx)
                };
                let target = Rc::new(Expr::Subscript { value: obj, index: idx });
                self.emit_store(target, val);
                true
            }
            Op::DELETE_SUBSCR => {
                let idx = self.pop_expr();
                let obj = self.pop_expr();
                let target = Rc::new(Expr::Subscript { value: obj, index: idx });
                self.emit_delete(target);
                true
            }
            Op::STORE_SLICE
            | Op::STORE_SLICE_0
            | Op::STORE_SLICE_1
            | Op::STORE_SLICE_2
            | Op::STORE_SLICE_3
            | Op::DELETE_SLICE_0
            | Op::DELETE_SLICE_1
            | Op::DELETE_SLICE_2
            | Op::DELETE_SLICE_3
            | Op::SLICE_0
            | Op::SLICE_1
            | Op::SLICE_2
            | Op::SLICE_3 => {
                self.handle_slice_ops(inst);
                true
            }

            // ---------- unary / binary ----------
            Op::UNARY_NEGATIVE | Op::UNARY_POSITIVE | Op::UNARY_INVERT | Op::UNARY_NOT => {
                let op = match inst.op {
                    Op::UNARY_NEGATIVE => UnaryOp::Neg,
                    Op::UNARY_POSITIVE => UnaryOp::Pos,
                    Op::UNARY_INVERT => UnaryOp::Invert,
                    _ => UnaryOp::Not,
                };
                let e = self.pop_expr();
                self.push(Rc::new(Expr::Unary { op, operand: e }));
                true
            }
            Op::UNARY_CONVERT => {
                let e = self.pop_expr();
                self.push(Rc::new(Expr::Backquote(e)));
                true
            }
            Op::BINARY_OP => {
                match binary_op_name(arg, self.version) {
                    Some(name) => {
                        if name.ends_with('=') {
                            self.apply_inplace(name.trim_end_matches('='), arg);
                        } else {
                            self.apply_binary(name);
                        }
                    }
                    None if self.version.at_least(3, 14) => {
                        // 3.14 folded BINARY_SUBSCR into BINARY_OP 26 (`[]`)
                        let idx = self.pop_expr();
                        let val = self.pop_expr();
                        let idx = normalize_slice_call(idx);
                        self.push(Rc::new(Expr::Subscript { value: val, index: idx }));
                    }
                    None => {
                        self.mark_unclean();
                        self.apply_binary("+");
                    }
                }
                true
            }
            Op::BINARY_ADD
            | Op::BINARY_SUBTRACT
            | Op::BINARY_MULTIPLY
            | Op::BINARY_DIVIDE
            | Op::BINARY_FLOOR_DIVIDE
            | Op::BINARY_MODULO
            | Op::BINARY_POWER
            | Op::BINARY_LSHIFT
            | Op::BINARY_RSHIFT
            | Op::BINARY_OR
            | Op::BINARY_XOR
            | Op::BINARY_AND
            | Op::BINARY_MATRIX_MULTIPLY
            | Op::BINARY_TRUE_DIVIDE => {
                let name = match inst.op {
                    Op::BINARY_ADD => "+",
                    Op::BINARY_SUBTRACT => "-",
                    Op::BINARY_MULTIPLY => "*",
                    Op::BINARY_DIVIDE | Op::BINARY_TRUE_DIVIDE => "/",
                    Op::BINARY_FLOOR_DIVIDE => "//",
                    Op::BINARY_MODULO => "%",
                    Op::BINARY_POWER => "**",
                    Op::BINARY_LSHIFT => "<<",
                    Op::BINARY_RSHIFT => ">>",
                    Op::BINARY_OR => "|",
                    Op::BINARY_XOR => "^",
                    Op::BINARY_AND => "&",
                    Op::BINARY_MATRIX_MULTIPLY => "@",
                    _ => unreachable!(),
                };
                self.apply_binary(name);
                true
            }
            Op::INPLACE_ADD
            | Op::INPLACE_SUBTRACT
            | Op::INPLACE_MULTIPLY
            | Op::INPLACE_DIVIDE
            | Op::INPLACE_FLOOR_DIVIDE
            | Op::INPLACE_MODULO
            | Op::INPLACE_POWER
            | Op::INPLACE_LSHIFT
            | Op::INPLACE_RSHIFT
            | Op::INPLACE_OR
            | Op::INPLACE_XOR
            | Op::INPLACE_AND
            | Op::INPLACE_MATRIX_MULTIPLY
            | Op::INPLACE_TRUE_DIVIDE => {
                let name = match inst.op {
                    Op::INPLACE_ADD => "+",
                    Op::INPLACE_SUBTRACT => "-",
                    Op::INPLACE_MULTIPLY => "*",
                    Op::INPLACE_DIVIDE | Op::INPLACE_TRUE_DIVIDE => "/",
                    Op::INPLACE_FLOOR_DIVIDE => "//",
                    Op::INPLACE_MODULO => "%",
                    Op::INPLACE_POWER => "**",
                    Op::INPLACE_LSHIFT => "<<",
                    Op::INPLACE_RSHIFT => ">>",
                    Op::INPLACE_OR => "|",
                    Op::INPLACE_XOR => "^",
                    Op::INPLACE_AND => "&",
                    Op::INPLACE_MATRIX_MULTIPLY => "@",
                    _ => unreachable!(),
                };
                self.apply_inplace(name, u32::MAX);
                true
            }
            Op::COMPARE_OP => {
                let idx = compare_op_index(arg, self.version);
                let op = cmp_from_index(idx);
                let rhs = self.pop_expr();
                let lhs = self.pop_expr();
                self.push(Rc::new(Expr::Compare {
                    operands: vec![lhs, rhs],
                    ops: vec![op],
                }));
                true
            }
            Op::IS_OP => {
                let rhs = self.pop_expr();
                let lhs = self.pop_expr();
                let op = if arg == 1 { CmpOp::IsNot } else { CmpOp::Is };
                self.push(Rc::new(Expr::Compare {
                    operands: vec![lhs, rhs],
                    ops: vec![op],
                }));
                true
            }
            Op::CONTAINS_OP => {
                let rhs = self.pop_expr();
                let lhs = self.pop_expr();
                let op = if arg == 1 { CmpOp::NotIn } else { CmpOp::In };
                self.push(Rc::new(Expr::Compare {
                    operands: vec![lhs, rhs],
                    ops: vec![op],
                }));
                true
            }
            Op::TO_BOOL => true,

            // ---------- container building ----------
            Op::BUILD_TUPLE | Op::BUILD_LIST | Op::BUILD_SET => {
                let items = self.pop_n_exprs(arg as usize);
                // <=3.5 decorators: BUILD_TUPLE wrapping the function object
                if inst.op == Op::BUILD_TUPLE && items.len() == 1 {
                    if let Expr::Function(fd) = &*items[0] {
                        let mut fd = (**fd).clone();
                        fd.decorators.push(self.name_expr("__decorator__"));
                        self.pending_decorators.push(self.name_expr("__decorator__"));
                        self.push(Rc::new(Expr::Function(Rc::new(fd))));
                        return true;
                    }
                }
                let e = match inst.op {
                    Op::BUILD_TUPLE => Expr::Tuple(items),
                    Op::BUILD_LIST => Expr::List(items),
                    _ => Expr::Set(items),
                };
                self.push(Rc::new(e));
                true
            }
            Op::BUILD_MAP => {
                if !self.version.at_least(3, 5) {
                    // py2-3.4: oparg is a size hint only; entries are added
                    // by STORE_MAP from values pushed *below* the dict
                    self.push(Rc::new(Expr::Dict(Vec::new())));
                } else {
                    let n = arg as usize;
                    let flat = self.pop_n_exprs(2 * n);
                    let mut entries = Vec::with_capacity(n);
                    for chunk in flat.chunks(2) {
                        if chunk.len() == 2 {
                            entries.push((chunk[0].clone(), chunk[1].clone()));
                        }
                    }
                    self.push(Rc::new(Expr::Dict(entries)));
                }
                true
            }
            Op::BUILD_CONST_KEY_MAP => {
                let keys_e = self.pop_expr();
                let values = self.pop_n_exprs(arg as usize);
                let keys: Vec<ObjectRef> = match &*keys_e {
                    Expr::Const(o) => match &**o {
                        PyObject::Tuple(t) => t.clone(),
                        _ => vec![],
                    },
                    _ => vec![],
                };
                let mut entries = Vec::with_capacity(values.len());
                for (i, v) in values.into_iter().enumerate() {
                    let k = keys
                        .get(i)
                        .cloned()
                        .map(|o| Rc::new(Expr::Const(o)) as ExprRef)
                        .unwrap_or_else(|| self.name_expr("/*key?*/"));
                    entries.push((k, v));
                }
                self.push(Rc::new(Expr::Dict(entries)));
                true
            }
            Op::STORE_MAP => {
                // py2: [map, value, key] with key on top
                let key = self.pop_expr();
                let value = self.pop_expr();
                let map = self.pop_expr();
                let mut entries = match &*map {
                    Expr::Dict(d) => d.clone(),
                    _ => Vec::new(),
                };
                entries.push((key, value));
                self.push(Rc::new(Expr::Dict(entries)));
                true
            }
            Op::BUILD_STRING => {
                let parts_e = self.pop_n_exprs(arg as usize);
                let mut out_parts = Vec::new();
                for p in parts_e {
                    match &*p {
                        Expr::Const(o) => match &**o {
                            PyObject::Str(s) => {
                                out_parts.push(FStringPart::Literal(s.clone()))
                            }
                            _ => out_parts.push(FStringPart::Value {
                                value: p.clone(),
                                conversion: None,
                                format_spec: None,
                            }),
                        },
                        Expr::FString(fs) => out_parts.extend(fs.parts.iter().cloned()),
                        _ => out_parts.push(FStringPart::Value {
                            value: p.clone(),
                            conversion: None,
                            format_spec: None,
                        }),
                    }
                }
                self.push(Rc::new(Expr::FString(Box::new(FString {
                    parts: out_parts,
                }))));
                true
            }
            Op::BUILD_SLICE => {
                let (start, stop, step) = if arg == 3 {
                    let step = none_if_const_none(self.pop_expr());
                    let stop = none_if_const_none(self.pop_expr());
                    let start = none_if_const_none(self.pop_expr());
                    (start, stop, step)
                } else {
                    let stop = none_if_const_none(self.pop_expr());
                    let start = none_if_const_none(self.pop_expr());
                    (start, stop, None)
                };
                self.push(Rc::new(Expr::Slice(Box::new(SliceExpr {
                    start,
                    stop,
                    step,
                }))));
                true
            }
            Op::LIST_EXTEND | Op::SET_UPDATE | Op::DICT_UPDATE | Op::LIST_APPEND
            | Op::SET_ADD | Op::MAP_ADD | Op::LIST_TO_TUPLE | Op::DICT_MERGE
            | Op::COPY_DICT_WITHOUT_KEYS => {
                if self.inline_comp.is_some()
                    && matches!(inst.op, Op::LIST_APPEND | Op::SET_ADD | Op::MAP_ADD)
                {
                    self.comp_add_element(inst);
                } else {
                    self.handle_collection_op(inst, arg);
                }
                true
            }
            Op::BUILD_LIST_UNPACK
            | Op::BUILD_TUPLE_UNPACK
            | Op::BUILD_SET_UNPACK
            | Op::BUILD_MAP_UNPACK
            | Op::BUILD_MAP_UNPACK_WITH_CALL
            | Op::BUILD_TUPLE_UNPACK_WITH_CALL => {
                let items = self.pop_n_exprs(arg as usize);
                let for_call = matches!(
                    inst.op,
                    Op::BUILD_TUPLE_UNPACK | Op::BUILD_TUPLE_UNPACK_WITH_CALL
                );
                let mut out: Vec<ExprRef> = Vec::new();
                for it in items {
                    if for_call {
                        // call-argument groups: plain tuples contribute their
                        // items positionally, everything else is *starred
                        match &*it {
                            Expr::Tuple(inner) => out.extend(inner.iter().cloned()),
                            other => {
                                out.push(Rc::new(Expr::Starred(Rc::new(other.clone()))))
                            }
                        }
                    } else {
                        out.push(Rc::new(Expr::Starred(it)));
                    }
                }
                let e = match inst.op {
                    Op::BUILD_LIST_UNPACK => Expr::List(out),
                    Op::BUILD_SET_UNPACK => Expr::Set(out),
                    _ => Expr::Tuple(out),
                };
                self.push(Rc::new(e));
                true
            }
            Op::UNPACK_SEQUENCE => {
                // pops the iterable and pushes N items (bottom->top order)
                let value = self.pop_expr();
                let n = arg as usize;
                self.unpack_frames.push((n, n, None, value.clone()));
                self.unpack_targets.0.push(Vec::new());
                for _ in 0..n {
                    self.stack.push(Sv::E(value.clone()));
                }
                true
            }
            Op::UNPACK_EX => {
                let before = (arg & 0xFF) as usize;
                let after = ((arg >> 8) & 0xFF) as usize;
                let value = self.pop_expr();
                let n = before + after + 1;
                self.unpack_frames.push((n, n, Some(before), value.clone()));
                self.unpack_targets.0.push(Vec::new());
                for _ in 0..n {
                    self.stack.push(Sv::E(value.clone()));
                }
                true
            }

            // ---------- stack manipulation ----------
            Op::POP_TOP => {
                self.handle_pop_top();
                true
            }
            Op::ROT_TWO => {
                let n = self.stack.len();
                if n >= 2 {
                    self.stack.swap(n - 1, n - 2);
                }
                true
            }
            Op::ROT_THREE => {
                let n = self.stack.len();
                if n >= 3 {
                    let v = self.stack.remove(n - 1);
                    self.stack.insert(n - 3, v);
                }
                true
            }
            Op::ROT_FOUR => {
                let n = self.stack.len();
                if n >= 4 {
                    let v = self.stack.remove(n - 1);
                    self.stack.insert(n - 4, v);
                }
                true
            }
            Op::ROT_N => {
                let n = arg as usize;
                let len = self.stack.len();
                if len >= n && n > 1 {
                    let v = self.stack.remove(len - 1);
                    self.stack.insert(len - n, v);
                }
                true
            }
            Op::SWAP => {
                let i = arg as usize;
                let len = self.stack.len();
                if len >= i && i > 0 {
                    self.stack.swap(len - 1, len - i);
                }
                true
            }
            Op::DUP_TOP => {
                if let Some(sv) = self.stack.last().cloned() {
                    self.stack.push(sv);
                } else if self
                    .idx_of
                    .get(&inst.offset)
                    .and_then(|&ci| self.instrs.get(ci + 2))
                    .map_or(false, |x| {
                        x.op == Op::COMPARE_OP
                            && cmp_from_index(compare_op_index(
                                x.arg as u32,
                                self.version,
                            )) == CmpOp::ExceptionMatch
                    })
                {
                    // handler-entry DUP_TOP over the exception value, which
                    // we do not model: supply a placeholder so the match
                    // comparison pops two operands
                    let ph = self.name_expr("/*exc*/");
                    // py2 `except E, n`: the implicit-as store right after
                    // the prelude pops binds the exception value — inside a
                    // skipped-chain sub-walk (where the store is rendered as
                    // an assignment, not captured as the clause name) give
                    // it a real binding: sys.exc_info()[1], buried under a
                    // tb placeholder the first prelude POP_TOP consumes
                    if self.version.major == 2 && self.legacy_nest_depth > 0 {
                        self.used_exc_info = true;
                        self.push(Rc::new(Expr::Subscript {
                            value: Rc::new(Expr::Call {
                                func: Rc::new(Expr::Attribute {
                                    value: self.name_expr("sys"),
                                    attr: "exc_info".to_string(),
                                }),
                                args: vec![],
                                keywords: vec![],
                                star_args: None,
                                star_kwargs: None,
                            }),
                            index: Rc::new(Expr::Const(Rc::new(PyObject::Int(1)))),
                        }));
                        self.push(ph.clone());
                    }
                    self.push(ph);
                }
                true
            }
            Op::DUP_TOP_TWO => {
                let n = self.stack.len();
                if n >= 2 {
                    let a = self.stack[n - 2].clone();
                    let b = self.stack[n - 1].clone();
                    self.stack.push(a);
                    self.stack.push(b);
                }
                true
            }
            Op::DUP_TOPX => {
                let n = arg as usize;
                let len = self.stack.len();
                if len >= n && n > 0 {
                    let dup: Vec<Sv> = self.stack[len - n..].to_vec();
                    self.stack.extend(dup);
                }
                true
            }
            Op::COPY => {
                let n = arg as usize;
                let len = self.stack.len();
                if len >= n && n > 0 {
                    let v = self.stack[len - n].clone();
                    self.stack.push(v);
                }
                true
            }
            Op::PUSH_NULL => {
                self.stack.push(Sv::Null);
                true
            }

            // ---------- calls ----------
            Op::CALL_FUNCTION => {
                self.call_function_py(arg as usize, None, false);
                true
            }
            Op::CALL_FUNCTION_VAR => {
                self.call_function_py2_var(arg as usize);
                true
            }
            Op::CALL_FUNCTION_KW => {
                if self.version.at_least(3, 6) {
                    let names = self.pop_expr();
                    self.call_function_py(arg as usize, Some(names), false);
                } else {
                    self.call_function_py(arg as usize, None, false);
                }
                true
            }
            Op::CALL_FUNCTION_VAR_KW => {
                self.call_function_py2_varkw(arg as usize);
                true
            }
            Op::CALL_METHOD => {
                // 3.7-3.10 method call: [meth, self_or_null, args...]
                self.call_function_py(arg as usize, None, true);
                true
            }
            Op::CALL => {
                self.call_311(arg as usize, false);
                true
            }
            Op::CALL_KW => {
                let names_e = self.pop_expr();
                let names: Vec<Option<String>> = match &*names_e {
                    Expr::Const(o) => match &**o {
                        PyObject::Tuple(items) => items
                            .iter()
                            .map(|it| match &**it {
                                PyObject::Str(s) => Some(s.clone()),
                                _ => None,
                            })
                            .collect(),
                        _ => Vec::new(),
                    },
                    _ => Vec::new(),
                };
                self.call_311(arg as usize, false);
                // retrofit kw names onto the produced call: the names tuple
                // covers the TRAILING k values (like KW_NAMES), the leading
                // total-k values are positional
                if let Some(Sv::E(e)) = self.stack.last_mut() {
                    if let Expr::Call { args, keywords, .. } = Rc::make_mut(e) {
                        let total = args.len() + keywords.len();
                        let named: Vec<Option<String>> = names.clone();
                        if !named.is_empty() && named.len() <= total {
                            let pos_count = total - named.len();
                            let all_vals: Vec<ExprRef> = args
                                .drain(..)
                                .chain(keywords.drain(..).map(|(_, v)| v))
                                .collect();
                            let new_args: Vec<ExprRef> =
                                all_vals.iter().take(pos_count).cloned().collect();
                            let new_kws: Vec<(Option<String>, ExprRef)> = named
                                .into_iter()
                                .zip(all_vals.into_iter().skip(pos_count))
                                .collect();
                            *args = new_args;
                            *keywords = new_kws;
                        }
                    }
                }
                true
            }
            Op::CALL_FUNCTION_EX => {
                // Stack layouts (bottom..top):
                // * <=3.10: [callable, args(, kwargs)] — oparg bit 0 = kwargs
                // * 3.11/3.12: [NULL_or_self, callable, args(, kwargs)]
                // * 3.13: [callable, NULL_or_self, args(, kwargs)] — oparg
                //   bit 0 still selects the kwargs slot
                // * 3.14: oparg removed; a kwargs slot is ALWAYS present on
                //   top: [callable, NULL_or_self, args, kwargs_dict_or_NULL]
                // pop_expr skips NULL markers, so popping callable after
                // args consumes the 3.13+/3.14 self slot automatically.
                let kwargs_opt: Option<ExprRef> = if self.version.at_least(3, 14) {
                    match self.stack.pop() {
                        Some(Sv::E(e)) => Some(e),
                        Some(Sv::Null) => None,
                        other => {
                            if let Some(o) = other {
                                self.stack.push(o);
                            }
                            self.clean = false;
                            None
                        }
                    }
                } else if arg & 1 != 0 {
                    Some(self.pop_expr())
                } else {
                    None
                };
                let args = self.pop_expr();
                let func = self.pop_expr();
                if self.version.at_least(3, 11) && !self.version.at_least(3, 13) {
                    // 3.11/3.12: the self/NULL slot sits BELOW the callable
                    if matches!(self.stack.last(), Some(Sv::Null)) {
                        self.stack.pop();
                    }
                }
                let (pos, star) = flatten_ex_args(args);
                let star_kw = match kwargs_opt {
                    Some(kw) => {
                        let (mut keywords, star_kw) = flatten_ex_kwargs(kw);
                        let _ = &mut keywords;
                        star_kw
                    }
                    None => None,
                };
                self.push(Rc::new(Expr::Call {
                    func,
                    args: pos,
                    keywords: Vec::new(),
                    star_args: star,
                    star_kwargs: star_kw,
                }));
                true
            }
            Op::KW_NAMES => {
                let keys_e = self.const_expr(arg as usize);
                self.last_kw_names = match &*keys_e {
                    Expr::Const(o) => match &**o {
                        PyObject::Tuple(items) => items
                            .iter()
                            .map(|it| match &**it {
                                PyObject::Str(s) => Some(s.clone()),
                                _ => None,
                            })
                            .collect(),
                        _ => Vec::new(),
                    },
                    _ => Vec::new(),
                };
                true
            }

            // ---------- functions / classes ----------
            Op::MAKE_FUNCTION | Op::MAKE_CLOSURE => {
                self.make_function(inst, arg);
                true
            }
            Op::SET_FUNCTION_ATTRIBUTE => {
                self.set_function_attribute_313(arg);
                true
            }
            Op::BUILD_CLASS => {
                // py2 stack bottom..top: [name, bases_tuple, namespace_dict]
                // (the namespace is the CALL_FUNCTION result of the class
                // body function); the result is stored by the next STORE_NAME
                let methods = self.pop_expr();
                let bases = self.pop_expr();
                let name = self.pop_expr();
                self.pending_py2_class = Some((name, bases, methods));
                self.push(self.name_expr("/*class-object*/"));
                true
            }

            // ---------- imports ----------
            Op::IMPORT_NAME => {
                let fromlist = self.pop_expr();
                let level_e = self.pop_expr();
                let level = match &*level_e {
                    Expr::Const(o) => o.as_int().unwrap_or(0).max(0) as u32,
                    _ => 0,
                };
                let module = self.const_name(arg as usize);
                let fromlist = match &*fromlist {
                    Expr::Const(o) if matches!(&**o, PyObject::None) => None,
                    other => Some(Rc::new(other.clone()) as ExprRef),
                };
                self.stack.push(Sv::ImportModule {
                    level,
                    module,
                    fromlist,
                });
                true
            }
            Op::IMPORT_FROM => {
                let name = self.const_name(arg as usize);
                // 3.12+: IMPORT_FROM may copy from TOS (the module); the
                // module marker stays below.
                if let Some(Sv::ImportModule { level, module, .. }) = self.stack.last() {
                    let (level, module) = (*level, module.clone());
                    self.stack.push(Sv::ImportFrom {
                        level,
                        module,
                        name: name.clone(),
                    });
                } else {
                    self.mark_unclean();
                    self.push(self.name_expr(name));
                }
                true
            }
            Op::IMPORT_STAR => {
                if let Some(Sv::ImportModule { level, module, .. }) = self.pop() {
                    self.push_stmt(Stmt::ImportFrom {
                        module,
                        level,
                        names: vec![("*".to_string(), None)],
                    });
                } else {
                    self.mark_unclean();
                }
                true
            }

            // ---------- returns / yields ----------
            Op::RETURN_VALUE => {
                // a deferred-fold handler (3.9 POP_EXCEPT-first) ends here:
                // the return belongs to its body, so emit first, fold after
                let defer_fold = self
                    .legacy_handler
                    .as_ref()
                    .map_or(false, |h| h.pop_seen);
                let e = self.pop_expr();
                self.emit_return(Some(e));
                if defer_fold {
                    self.flush_pending_stores();
                    if let Some(h) = self.legacy_handler.take() {
                        if let Some(he) = &h.name {
                            if let Expr::Name(n) = &**he {
                                self.pending_as_cleanup = Some(n.clone());
                            }
                        }
                        if let Some(l) = self.legacy_try.as_mut() {
                            l.handlers.push(ExceptHandler {
                                type_: h.type_,
                                name: h.name,
                                body: h.body,
                            });
                        }
                    }
                    self.legacy_handler_end = None;
                }
                // at function top level a RETURN ends the meaningful stream;
                // trailing bytes are exception-table cleanup paths — unless
                // a pre-3.11 handler chain still needs to run, or an open
                // 3.12 chained-comparison link still needs its else-arm fold
                !matches!(self.blocks.last().map(|b| b.kind), Some(BlockType::Main))
                    || self.legacy_try.is_some()
                    || self.blocks.iter().any(|b| b.chain_link)
            }
            Op::YIELD_VALUE => {
                if self.await_mode {
                    // await expr: stack [coro, sent]; consume both
                    self.await_mode = false;
                    self.skip_end_send = true;
                    self.pop(); // sent value
                    // the with-exit recognizer swallowed the async-with
                    // __aexit__ call, so nothing awaitable is left — the
                    // whole protocol is desugaring residue; drop it
                    // without underflowing the value stack
                    if self.with_exit_await_drop
                        || !self.stack.iter().any(|sv| matches!(sv, Sv::E(_)))
                    {
                        self.with_exit_await_drop = false;
                        return true;
                    }
                    let coro = self.pop_expr();
                    match &*coro {
                        // async with: awaiting __aenter__/__aexit__ results
                        Expr::Name(n)
                            if n == WITH_RESULT_PLACEHOLDER || n.contains("underflow") =>
                        {
                            if n == WITH_RESULT_PLACEHOLDER {
                                self.push(coro);
                            }
                        }
                        // the __aexit__ call of an async with was swallowed
                        // by the with-exit recognizer, so the awaited value
                        // underflows to Const(None) — `await None` is never
                        // real code; drop the whole protocol value
                        Expr::Const(o) if matches!(&**o, PyObject::None) => {}
                        _ => self.push(Rc::new(Expr::Await(coro))),
                    }
                    return true;
                }
                let e = self.pop_expr();
                if self.code.is_coroutine() || self.code.is_async_generator() {
                    // inside async functions a bare yield keeps its form
                    self.push(Rc::new(Expr::Yield(Some(e))));
                } else if arg == 1 && self.version.at_least(3, 14) {
                    self.push_stmt(Stmt::Expr(Rc::new(Expr::Yield(Some(e)))));
                } else {
                    self.push(Rc::new(Expr::Yield(Some(e))));
                }
                true
            }
            Op::YIELD_FROM => {
                // stack: [iterable, sent_value]; the sent value is on top
                self.pop();
                if self.await_mode
                    && (self.with_exit_await_drop
                        || !self.stack.iter().any(|sv| matches!(sv, Sv::E(_))))
                {
                    // swallowed async-with __aexit__ call (or a 3.8
                    // WITH_CLEANUP_START whose awaited result was never
                    // modeled): desugaring residue, drop it cleanly —
                    // a real `await x` always has x on the stack
                    self.await_mode = false;
                    self.with_exit_await_drop = false;
                    self.pop();
                    return true;
                }
                let e = self.pop_expr();
                self.await_mode = false;
                // async with: the awaited value is the __aenter__ result
                // placeholder — keep it bare for the `as` store
                let is_placeholder = matches!(&*e, Expr::Name(n) if n == WITH_RESULT_PLACEHOLDER);
                if !is_placeholder && (self.code.is_coroutine() || self.code.is_async_generator())
                {
                    self.push(Rc::new(Expr::Await(e)));
                } else if is_placeholder {
                    self.push(e);
                } else {
                    self.push(Rc::new(Expr::YieldFrom(e)));
                }
                true
            }
            Op::SEND => true,
            Op::END_SEND => {
                if self.skip_end_send {
                    self.skip_end_send = false;
                } else {
                    self.pop();
                }
                true
            }
            Op::RETURN_GENERATOR => {
                // generator expression: the code object is the last code
                // constant referenced by a preceding LOAD_CONST
                let code_const = self
                    .recent_code_const
                    .clone();
                self.pending_gen_code = code_const;
                self.push(self.name_expr("/*generator*/"));
                true
            }
            Op::GET_AWAITABLE => {
                // value-preserving; materializes as `await` at the next
                // YIELD_VALUE (3.11+) or YIELD_FROM (<=3.10)
                self.await_mode = true;
                true
            }
            Op::GET_YIELD_FROM_ITER if self.version.at_least(3, 11) => {
                // 3.11+ delegation (`yield from`) / await protocol:
                //   GET_YIELD_FROM_ITER; LOAD sent; SEND loop; END_SEND
                // Emit the whole protocol as one YieldFrom/Await value or
                // statement and skip the resume machinery. (<=3.10 uses
                // the YIELD_FROM opcode and stays a plain no-op here.)
                let it = self.pop_expr();
                let is_placeholder =
                    matches!(&*it, Expr::Name(n) if n == WITH_RESULT_PLACEHOLDER);
                let expr = if is_placeholder {
                    it
                } else if self.code.is_coroutine() && !self.code.is_async_generator()
                {
                    Rc::new(Expr::Await(it))
                } else {
                    Rc::new(Expr::YieldFrom(it))
                };
                if let Some(&si) = self.idx_of.get(&inst.offset) {
                    let mut end_send = None;
                    let mut tail_pop = None;
                    let mut send_target = None;
                    let mut prev = inst.op;
                    for k in si + 1..self.instrs.len().min(si + 40) {
                        let nx = &self.instrs[k];
                        if nx.op == Op::SEND && send_target.is_none() {
                            send_target = nx.target;
                        }
                        if nx.op == Op::END_SEND {
                            end_send = Some(k);
                            break;
                        }
                        // 3.11 has no END_SEND: the protocol ends with the
                        // POP_TOP right after the resume loop
                        if nx.op == Op::POP_TOP
                            && matches!(
                                prev,
                                Op::JUMP_BACKWARD_NO_INTERRUPT
                                    | Op::SEND
                                    | Op::RESUME
                                    | Op::YIELD_VALUE
                            )
                        {
                            tail_pop = Some(k);
                            break;
                        }
                        if matches!(nx.op, Op::RETURN_VALUE | Op::RETURN_CONST) {
                            break;
                        }
                        prev = nx.op;
                    }
                    if let Some(ei) = end_send {
                        let after_pop = self
                            .instrs
                            .get(ei + 1)
                            .filter(|a| a.op == Op::POP_TOP)
                            .map(|a| a.end());
                        let end_send_end = self.instrs[ei].end();
                        if let Some(pop_end) = after_pop {
                            self.push_stmt(Stmt::Expr(expr));
                            self.skip_until = Some(pop_end);
                        } else {
                            self.push(expr);
                            self.skip_until = Some(end_send_end);
                        }
                        return true;
                    }
                    if let Some(pi) = tail_pop {
                        let pop_end = self.instrs[pi].end();
                        self.push_stmt(Stmt::Expr(expr));
                        self.skip_until = Some(pop_end);
                        return true;
                    }
                    // value form without END_SEND (3.11): the SEND's jump
                    // target is where the delegated value lands
                    if let Some(st) = send_target {
                        self.push(expr);
                        self.skip_until = Some(st);
                        return true;
                    }
                }
                self.push(expr);
                true
            }
            // <=3.10: the YIELD_FROM opcode arm models the delegation
            Op::GET_ANEXT if !self.version.at_least(3, 11) => {
                // <=3.10 async-for:
                //   SETUP_FINALLY(->END_ASYNC_FOR); GET_ANEXT; LOAD None;
                //   YIELD_FROM; POP_BLOCK; STORE target; body;
                //   JUMP_ABSOLUTE -> SETUP_FINALLY; END_ASYNC_FOR
                // The back edge targets the SETUP_FINALLY, so the block
                // starts there; skip the anext-await protocol up to the
                // target store.
                let iter = self.pop_expr();
                let mut skip_to = None;
                if let Some(&ai) = self.idx_of.get(&inst.offset) {
                    for k in ai + 1..self.instrs.len().min(ai + 8) {
                        match self.instrs[k].op {
                            Op::STORE_FAST | Op::STORE_NAME | Op::STORE_DEREF => {
                                skip_to = Some(self.instrs[k].offset);
                                break;
                            }
                            Op::YIELD_FROM | Op::POP_BLOCK | Op::LOAD_CONST => {}
                            _ => break,
                        }
                    }
                }
                // 3.5-3.7: the SETUP_EXCEPT guard recognition already opened
                // the async For block (the back edge targets the setup) —
                // just attach the iterator
                // 3.6: GET_AITER's result arrives awaited (`GET_AITER;
                // LOAD None; YIELD_FROM` before the guard) — unwrap so the
                // header renders the plain iterable
                let iter = match &*iter {
                    Expr::Await(inner) => inner.clone(),
                    _ => iter,
                };
                let joined = matches!(
                    self.blocks.last(),
                    Some(b) if b.is_async
                        && matches!(b.kind, BlockType::For)
                        && b.iter.is_none()
                );
                if joined {
                    if let Some(top) = self.blocks.last_mut() {
                        top.iter = Some(iter.clone());
                        top.cond_end = inst.end();
                    }
                } else {
                    let mut start = inst.offset;
                    if let Some(&ai) = self.idx_of.get(&inst.offset) {
                        if ai > 0 && self.instrs[ai - 1].op == Op::SETUP_FINALLY {
                            start = self.instrs[ai - 1].offset;
                        }
                    }
                    let mut exit = usize::MAX;
                    if let Some(&ai) = self.idx_of.get(&inst.offset) {
                        for ins in self.instrs.iter().skip(ai + 1) {
                            if ins.op == Op::END_ASYNC_FOR {
                                exit = ins.offset;
                                break;
                            }
                        }
                    }
                    let mut fb = Block::new(BlockType::For, start, exit);
                    fb.cond_end = inst.end();
                    fb.iter = Some(iter.clone());
                    fb.is_async = true;
                    fb.cond_set = true;
                    self.blocks.push(fb);
                }
                self.awaiting_for_target = true;
                self.push(iter);
                if let Some(st) = skip_to {
                    self.skip_until = Some(st);
                }
                true
            }
            Op::GET_ANEXT => {
                // 3.10+ async-for loop top:
                //   GET_ANEXT; LOAD sent; SEND L; YIELD_VALUE; RESUME;
                //   JUMP_BACKWARD_NO_INTERRUPT; L: END_SEND; STORE target
                // Open the async For block and skip the resume protocol;
                // the back edge (JUMP_BACKWARD to this offset) closes the
                // loop and skips the CLEANUP_THROW/END_ASYNC_FOR tail.
                let iter = self.pop_expr();
                let mut proto_end = None;
                if let Some(&ai) = self.idx_of.get(&inst.offset) {
                    for k in ai + 1..self.instrs.len().min(ai + 12) {
                        match self.instrs[k].op {
                            Op::END_SEND => {
                                proto_end = Some(self.instrs[k].end());
                                break;
                            }
                            Op::STORE_FAST
                            | Op::STORE_NAME
                            | Op::STORE_DEREF
                            | Op::YIELD_FROM => break,
                            _ => {}
                        }
                    }
                }
                // like FOR_ITER: keep the iterator on the stack so the
                // loop-target STORE pops it (awaiting_for_target reroutes
                // it into the block header) instead of underflowing. With
                // the protocol skipped the STORE is the very next executed
                // instruction; without a skip (3.11 has no END_SEND) the
                // resume ops run inline and would leak a second value.
                if proto_end.is_some() {
                    self.push(iter.clone());
                }
                let mut exit = usize::MAX;
                if let Some(&ai) = self.idx_of.get(&inst.offset) {
                    for ins in self.instrs.iter().skip(ai + 1) {
                        if ins.op == Op::END_ASYNC_FOR {
                            exit = ins.offset;
                            break;
                        }
                    }
                }
                let mut fb = Block::new(BlockType::For, inst.offset, exit);
                fb.cond_end = inst.end();
                fb.iter = Some(iter);
                fb.is_async = true;
                fb.cond_set = true;
                self.blocks.push(fb);
                self.awaiting_for_target = true;
                if let Some(pe) = proto_end {
                    self.skip_until = Some(pe);
                }
                true
            }
            Op::GET_ITER | Op::GET_YIELD_FROM_ITER | Op::GET_AITER => true,
            Op::END_ASYNC_FOR => {
                self.pop();
                true
            }
            Op::END_FOR => {
                if let Some(end) = self.inline_comp.as_ref().map(|c| c.end) {
                    // pop the exhausted iterator; on 3.14 a following
                    // POP_ITER does it instead
                    // 3.14 uses POP_ITER, 3.13 uses POP_TOP after END_FOR
                    // to remove the exhausted iterator
                    let popiter_follows = self
                        .instrs
                        .iter()
                        .find(|i| i.start >= inst.end())
                        .map(|i| matches!(i.op, Op::POP_ITER | Op::POP_TOP))
                        .unwrap_or(false);
                    if !popiter_follows {
                        // the VM keeps the iterator under the result list
                        // until END_FOR pops it
                        self.pop();
                    }
                    if inst.offset < end {
                        return true; // inner loop cleanup
                    }
                    self.finish_inline_comp();
                    return true;
                }
                self.pop();
                if self.version.at_most(3, 12) {
                    self.pop();
                }
                true
            }
            Op::POP_ITER => {
                // pops the exhausted iterator left by FOR_ITER (3.14+)
                self.pop();
                true
            }

            // ---------- control flow ----------
            Op::JUMP_FORWARD => {
                let target = inst.target.unwrap_or(inst.end());
                let over_handlers = self
                    .legacy_try
                    .as_ref()
                    .map_or(false, |l| target > l.handler_start);
                if !over_handlers && self.find_loop_exit(target).is_some() {
                    self.push_stmt(Stmt::Break);
                    self.close_inner_blocks_to_loop();
                }
                let r = self.handle_jump_forward(target);
                // <=3.10 with normal exit: the jump flies over the whole
                // exception-time cleanup handler (the SETUP_WITH /
                // SETUP_ASYNC_WITH target) — only reachable through an
                // exception, never walk it
                if target > self.cur_next
                    && self.with_handler_starts.contains(&self.cur_next)
                {
                    self.skip_until = Some(target);
                    return r;
                }
                // With no branch block open and the jumped-over region a
                // PURE VALUE arm, the region is unreachable dead code
                // (e.g. the vestigial else arm of a constant-folded
                // ternary: `LOAD 3.5; JUMP_FORWARD; LOAD 0`) — skip it so
                // it cannot pollute the value stack. Statement regions
                // (loop-else bodies after a break, if/else arms) are never
                // pure-value and keep the normal walk.
                if !over_handlers
                    && target > self.cur_offset
                    && self.find_loop_exit(target).is_none()
                    && matches!(self.blocks.last().map(|b| b.kind), Some(BlockType::Main))
                    && self.is_pure_value_region(self.cur_next, target)
                {
                    self.skip_until = Some(target);
                }
                // 3.5-3.7 async-for: the per-iteration JUMP_FORWARD flies
                // over the StopAsyncIteration guard handler into the loop
                // body — skip exactly that machinery region
                if self.skip_until.is_none()
                    && self.async_for_guard.map_or(false, |(h, _, _)| {
                        h == self.cur_next && target > h
                    })
                {
                    self.skip_until = Some(target);
                }
                r
            }
            Op::JUMP_ABSOLUTE | Op::JUMP_BACKWARD | Op::CONTINUE_LOOP => {
                let target = inst.target.unwrap_or(0);
                if let Some(comp) = &self.inline_comp {
                    if comp.for_iter_offsets.contains(&target) {
                        return true; // comprehension loop back edge
                    }
                }
                // <=3.9: `break` is JUMP_ABSOLUTE to the loop exit — but a
                // folded chain exit (jump inside an open If/Else region at
                // its boundary) must go through the folded machinery first
                if target > self.cur_offset {
                    // a forward jump flying over an enclosing loop's
                    // exhaustion exit to a continuation no other jump
                    // targets is a `break` over a for/while-else region:
                    // record the else end so the loop close can build it
                    for b in self.blocks.iter_mut().rev() {
                        if matches!(b.kind, BlockType::While | BlockType::For) {
                            if b.end < target && b.loop_else_end.is_none() {
                                let others = self
                                    .instrs
                                    .iter()
                                    .filter(|i| {
                                        i.target == Some(target)
                                            && i.offset != self.cur_offset
                                    })
                                    .count();
                                if others == 0 {
                                    b.loop_else_end = Some(target);
                                }
                            }
                            break;
                        }
                    }
                    if self.find_loop_exit(target).is_some() {
                        self.push_stmt(Stmt::Break);
                        self.close_inner_blocks_to_loop();
                        return true;
                    }
                }
                // jump-threaded folded exit: a FORWARD jump landing on the
                // loop's own back-edge instruction (the compiler threads
                // branch exits that flow into the iteration end)
                let lands_on_back_edge = target > self.cur_offset
                    && self
                        .idx_of
                        .get(&target)
                        .and_then(|&ti| self.instrs.get(ti))
                        .map_or(false, |x| {
                            x.is_backward
                                && matches!(
                                    x.op,
                                    Op::JUMP_ABSOLUTE
                                        | Op::JUMP_BACKWARD
                                        | Op::JUMP_BACKWARD_NO_INTERRUPT
                                )
                                && x.target
                                    == self
                                        .blocks
                                        .iter()
                                        .rev()
                                        .find(|b| {
                                            matches!(b.kind, BlockType::While | BlockType::For)
                                        })
                                        .map(|l| l.start)
                        });
                // degenerate `if c: break` fusion (3.12): the back edge is
                // the ENTIRE then-region of a just-opened If — let the
                // fused-continue machinery below record the Continue and
                // the close-time normalizer flip it to `if c: break`
                // 3.14 `if c: break`: the PJIT hops over a break block
                // whose head is a jump to the loop EXIT — a plain continue
                // guard's back edge targets the loop top instead and must
                // keep the fused-continue path.
                let break_hop_target = match self.idx_of.get(&self.cur_offset) {
                    Some(&bi0) => {
                        let mut bj = bi0 + 1;
                        while matches!(
                            self.instrs.get(bj).map(|x| x.op),
                            Some(Op::POP_TOP) | Some(Op::NOP) | Some(Op::NOT_TAKEN)
                        ) {
                            bj += 1;
                        }
                        match self.instrs.get(bj) {
                            Some(j)
                                if matches!(
                                    j.op,
                                    Op::JUMP_FORWARD | Op::JUMP | Op::JUMP_ABSOLUTE
                                ) && !j.is_backward =>
                            {
                                j.target
                            }
                            _ => None,
                        }
                    }
                    None => None,
                };
                let degenerate_break_fusion = self
                    .blocks
                    .last()
                    .map(|t| {
                        t.kind == BlockType::If
                            && t.stmts.is_empty()
                            && t.short_circuit.is_none()
                            && (t.start == self.cur_offset
                                || (self.padding_only_between(t.start, self.cur_offset)
                                    && break_hop_target
                                        .map_or(false, |bt| self.find_loop_exit(bt).is_some())))
                    })
                    .unwrap_or(false);
                if !degenerate_break_fusion
                    && (lands_on_back_edge || self.is_continue_jump(target))
                {
                    // folded elif/else boundary: this jump is the LAST
                    // instruction of an If/Else branch region and the target
                    // is (or threads to) the enclosing loop's back edge —
                    // the compiler fused the chain exit with the loop end.
                    // Close the branch and let the chain machinery build
                    // the else/elif at the next instruction.
                    let folded = match self.blocks.last() {
                        Some(t)
                            if matches!(t.kind, BlockType::If | BlockType::Else)
                                && t.short_circuit.is_none() =>
                        {
                            let at_end = t.end == self.cur_next
                                || t.end == self.cur_offset
                                || (t.folded_exit && t.end == usize::MAX);
                            // or the jump hops over trailing else-code that
                            // no other instruction references (the folded
                            // chain exit jumps straight to the loop top)
                            let hops_tail = t.end > self.cur_next
                                && (self.cur_offset..t.end).any(|o| self.targets.contains(&o))
                                && (self.cur_next..t.end)
                                    .all(|o| !self.targets.contains(&o));
                            // 3.8+: a real `continue` statement carries
                            // its own source line (the compiler attributes
                            // it to the loop header or the continue
                            // itself), while a fused chain exit carries the
                            // preceding statement's line, matching the
                            // branch cond jump's line in the common
                            // single-line-branch case. Empirical heuristic;
                            // <=3.7 has the distinct CONTINUE_LOOP opcode.
                            // line-based disambiguation of a fused chain
                            // exit from a real trailing `continue`:
                            // - 3.8+: a real continue carries its own line
                            //   (or the loop header's), a fused exit carries
                            //   the branch cond's line
                            // - py2/<=3.7: a fused exit shares the line of
                            //   the last statement in the branch; a real
                            //   continue starts a fresh line
                            let line_ok = t.folded_exit
                                || if self.version.at_least(3, 8) {
                                    self.instrs
                                        .iter()
                                        .find(|i| i.end() == t.start && i.target.is_some())
                                        .map_or(true, |cj| {
                                            cj.line.is_none()
                                                || inst.line.is_none()
                                                || cj.line == inst.line
                                        })
                                } else {
                                    self.idx_of
                                        .get(&self.cur_offset)
                                        .and_then(|&ci| {
                                            (ci > 0).then(|| &self.instrs[ci - 1])
                                        })
                                        .map_or(true, |prev| {
                                            prev.line.is_none()
                                                || inst.line.is_none()
                                                || prev.line == inst.line
                                        })
                                };
                            (at_end || hops_tail)
                                && line_ok
                                && (lands_on_back_edge
                                    || self
                                        .blocks
                                        .iter()
                                        .rev()
                                        .skip(1)
                                        .find(|b| {
                                            matches!(b.kind, BlockType::While | BlockType::For)
                                        })
                                        .map_or(false, |l| {
                                            l.start == target || l.cond_end == target
                                        }))
                        }
                        _ => false,
                    };
                    if folded {
                        let end = self.blocks.last().map(|t| t.end).unwrap_or(target);
                        // mark every enclosing open If/Else whose region
                        // contains this jump: the fused exit serves as the
                        // then-exit for the whole chain spine
                        for t in self.blocks.iter_mut() {
                            if matches!(t.kind, BlockType::If | BlockType::Else)
                                && t.end > self.cur_offset
                            {
                                t.folded_exit = true;
                            }
                        }
                        // close inner blocks whose region already ended,
                        // then the folded branch block itself
                        self.close_blocks_at(self.cur_offset);
                        let top_matches = self.blocks.last().map_or(false, |t| {
                            (matches!(t.kind, BlockType::If) || matches!(t.kind, BlockType::Else))
                                && t.end == end
                        });
                        if top_matches {
                            // folded chain blocks that were already open
                            // before this jump also end here (the jump is
                            // the chain end); blocks freshly opened by the
                            // close below must stay (their region follows)
                            // blocks already open before this jump end
                            // here too; identify them by start offset so a
                            // freshly opened Else (start == this position)
                            // is not collapsed
                            let spine: Vec<usize> = self
                                .blocks
                                .iter()
                                .filter(|t| {
                                    matches!(t.kind, BlockType::If | BlockType::Else)
                                        && t.folded_exit
                                        && t.end > self.cur_offset
                                })
                                .map(|t| t.start)
                                .collect();
                            self.force_close_top(end);
                            let mut guard = 0;
                            while self.blocks.last().map_or(false, |t| {
                                matches!(t.kind, BlockType::If | BlockType::Else)
                                    && t.folded_exit
                                    && spine.contains(&t.start)
                            }) && guard < 16
                            {
                                let e = self.blocks.last().map(|t| t.end).unwrap_or(end);
                                self.force_close_top(e);
                                guard += 1;
                            }
                        }
                        return true;
                    }
                    // not folded: run the deferred block close, then decide
                    // again — the branch block that ended at this jump may
                    // have been the only thing making this a nested continue.
                    // A jump landing ON the loop's back edge just flows into
                    // the iteration end (compiler fusion), never a continue.
                    self.close_blocks_at(self.cur_offset);
                    if !lands_on_back_edge && self.is_continue_jump(target) {
                        // continue of an outer loop: emit first, then close
                        // the inner blocks it jumps out of
                        self.push_stmt(Stmt::Continue);
                        self.close_inner_blocks_to_loop();
                        return true;
                    }
                }
                if target > self.cur_offset {
                    // forward absolute jump (<=3.7 else/exit jumps). Inside
                    // an If/Else block it ends a then/else body; otherwise
                    // it skips over cleanup-handler code.
                    let in_branch = matches!(
                        self.blocks.last().map(|b| b.kind),
                        Some(BlockType::If) | Some(BlockType::Else) | Some(BlockType::Try)
                    );
                    if in_branch {
                        return self.handle_jump_forward(target);
                    }
                    self.close_blocks_at(self.cur_offset);
                    self.skip_until = Some(target);
                    return true;
                }
                self.handle_jump_backward(target);
                true
            }
            Op::JUMP | Op::JUMP_NO_INTERRUPT => {
                if inst.is_backward {
                    let target = inst.target.unwrap_or(0);
                    self.handle_jump_backward(target);
                } else {
                    let target = inst.target.unwrap_or(inst.end());
                    return self.handle_jump_forward(target);
                }
                true
            }
            Op::POP_JUMP_IF_FALSE
            | Op::POP_JUMP_FORWARD_IF_FALSE
            | Op::POP_JUMP_BACKWARD_IF_FALSE => {
                let target = inst.target.unwrap_or(inst.end());
                let cond = self.pop_expr();
                self.handle_cond_jump(cond, false, target);
                true
            }
            Op::POP_JUMP_IF_TRUE
            | Op::POP_JUMP_FORWARD_IF_TRUE
            | Op::POP_JUMP_BACKWARD_IF_TRUE => {
                let target = inst.target.unwrap_or(inst.end());
                let cond = self.pop_expr();
                self.handle_cond_jump(cond, true, target);
                true
            }
            Op::POP_JUMP_IF_NONE | Op::POP_JUMP_FORWARD_IF_NONE | Op::POP_JUMP_BACKWARD_IF_NONE => {
                let target = inst.target.unwrap_or(inst.end());
                let val = self.pop_expr();
                let cond = Rc::new(Expr::Compare {
                    operands: vec![val, Rc::new(Expr::Const(Rc::new(PyObject::None)))],
                    ops: vec![CmpOp::Is],
                });
                // jumps when the comparison is TRUE
                self.handle_cond_jump(cond, true, target);
                true
            }
            Op::POP_JUMP_IF_NOT_NONE
            | Op::POP_JUMP_FORWARD_IF_NOT_NONE
            | Op::POP_JUMP_BACKWARD_IF_NOT_NONE => {
                let target = inst.target.unwrap_or(inst.end());
                let val = self.pop_expr();
                let cond = Rc::new(Expr::Compare {
                    operands: vec![val, Rc::new(Expr::Const(Rc::new(PyObject::None)))],
                    ops: vec![CmpOp::IsNot],
                });
                self.handle_cond_jump(cond, true, target);
                true
            }
            Op::JUMP_IF_TRUE_OR_POP => {
                // `or`: if truthy jump keeping value, else pop and continue
                let target = inst.target.unwrap_or(inst.end());
                self.handle_short_circuit(true, target);
                true
            }
            Op::JUMP_IF_FALSE_OR_POP => {
                // `and`
                let target = inst.target.unwrap_or(inst.end());
                self.handle_short_circuit(false, target);
                true
            }
            Op::JUMP_IF_FALSE | Op::JUMP_IF_TRUE => {
                // py2 value-preserving cond jump. Two shapes:
                //   if-stmt:  JUMP_IF_FALSE L; POP_TOP; then; JUMP_FORWARD E;
                //             L: POP_TOP; else; E:
                //   value:    JUMP_IF_FALSE L; POP_TOP; b; L:   (and/or/ternary)
                let target = inst.target.unwrap_or(inst.end());
                let jump_if_true = inst.op == Op::JUMP_IF_TRUE;
                let ci = self.idx_of.get(&inst.offset).copied();
                let next_pop = ci
                    .and_then(|i| self.instrs.get(i + 1))
                    .map(|x| x.op == Op::POP_TOP)
                    .unwrap_or(false);
                let target_pop = self
                    .idx_of
                    .get(&target)
                    .and_then(|i| self.instrs.get(*i))
                    .map(|x| x.op == Op::POP_TOP)
                    .unwrap_or(false);
                if jump_if_true && next_pop {
                    // py2 `assert cond[, msg]`: JUMP_IF_TRUE L; POP_TOP;
                    // LOAD AssertionError; ...; RAISE 1; L:
                    if let Some(msg) = self.is_assert_fallthrough(target) {
                        let cond = self.pop_expr();
                        self.push_stmt(Stmt::Assert { test: cond, msg });
                        self.skip_until = Some(target);
                        return true;
                    }
                }
                if next_pop && target_pop {
                    // py2.6 statement boolop chain: `if A and B:` / `elif
                    // C or D:` compile every link as JUMP_IF_* + POP_TOP —
                    // the same shape as the whole-statement jump. A chain
                    // is told apart by its then arm holding ANOTHER cond
                    // jump reachable through pure value ops only (the
                    // next link); statement bodies contain non-value ops.
                    // Fold the whole chain into one BoolOp condition and
                    // open the if from the final link.
                    let first = match (ci, self.stack.last()) {
                        (Some(_), Some(Sv::E(e))) => Some(e.clone()),
                        _ => None,
                    };
                    if let (Some(i0), Some(first)) = (ci, first) {
                        if let Some((cond, then_start, else_body, else_pop)) =
                            self.py26_stmt_boolop_chain(i0, first, jump_if_true, target)
                        {
                            self.pop(); // operand 0 (consumed by the fold)
                            self.py2_else_pop_at = Some(else_pop);
                            self.skip_until = Some(then_start);
                            self.handle_cond_jump(cond, false, else_body);
                            return true;
                        }
                    }
                    // if-statement shape: both paths discard the value
                    let cond = self.pop_expr();
                    let else_body = self
                        .idx_of
                        .get(&target)
                        .map(|&ti| self.instrs[ti].end())
                        .unwrap_or(target);
                    self.py2_else_pop_at = Some(target);
                    // skip the then-branch POP_TOP (cond already popped)
                    if let Some(i) = ci {
                        if let Some(pop) = self.instrs.get(i + 1) {
                            self.skip_until = Some(pop.end());
                        }
                    }
                    self.handle_cond_jump(cond, jump_if_true, else_body);
                    return true;
                }
                // short-circuit / ternary shape: the target region carries a
                // value that merges at `target`
                let cond = match self.stack.last() {
                    Some(Sv::E(e)) => e.clone(),
                    _ => self.name_expr("???"),
                };
                let c = if jump_if_true {
                    simplify_not(cond)
                } else {
                    cond
                };
                let mut blk = Block::new(BlockType::If, self.cur_next, target);
                blk.cond = Some(c);
                blk.cond_set = true;
                blk.jump_if_true = false;
                blk.value_merge = Some(if jump_if_true {
                    BoolOpKind::Or
                } else {
                    BoolOpKind::And
                });
                blk.else_end = Some(target);
                blk.stack_depth = self.stack.len();
                self.blocks.push(blk);
                true
            }
            Op::FOR_ITER => {
                if self.in_comp_region(inst.offset)
                    && !self.has_build_prologue(inst.offset)
                {
                    // additional generator of the SAME comprehension
                    // (`for x in A for y in B`)
                    self.push_nested_comp_gen();
                    return true;
                }
                if let Some(kind) = self.detect_inline_comp() {
                    self.start_inline_comp(kind, inst);
                    return true;
                }
                let target = inst.target.unwrap_or(inst.end());
                // async for: the iterable expression is an Await, or we are
                // inside an async def using GET_AITER
                let is_async = matches!(
                    self.stack.last(),
                    Some(Sv::E(e)) if matches!(&**e, Expr::Await(_))
                );
                if is_async {
                    if let Some(Sv::E(e)) = self.stack.last_mut() {
                        if let Expr::Await(inner) = &**e {
                            *e = inner.clone();
                        }
                    }
                }
                self.handle_for_iter(target, is_async);
                true
            }
            Op::FOR_LOOP => {
                if self.in_comp_region(inst.offset)
                    && !self.has_build_prologue(inst.offset)
                {
                    self.push_nested_comp_gen();
                    return true;
                }
                if let Some(kind) = self.detect_inline_comp() {
                    self.start_inline_comp(kind, inst);
                    return true;
                }
                // 3.14: FOR_LOOP with kind in low bits of arg
                let target = inst.target.unwrap_or(inst.end());
                self.handle_for_iter(target, false);
                true
            }
            Op::BREAK_LOOP => {
                self.push_stmt(Stmt::Break);
                if self.broken_loop_top.is_none() {
                    self.broken_loop_top = self
                        .blocks
                        .iter()
                        .rev()
                        .find(|b| matches!(b.kind, BlockType::While | BlockType::For))
                        .map(|b| b.start);
                }
                true
            }

            // ---------- block setup (<= 3.10 era) ----------
            Op::SETUP_LOOP => {
                let target = inst.target.unwrap_or(inst.end());
                if !self.pending_stores.is_empty() {
                    self.flushing = true;
                    self.flush_pending_stores();
                    self.flushing = false;
                }
                let mut blk = Block::new(BlockType::While, inst.end(), target);
                blk.cond_set = false;
                self.blocks.push(blk);
                true
            }
            Op::SETUP_EXCEPT => {
                // compiler-internal exception-state finally inside a
                // legacy handler body (e.g. `raise` in except on 3.8-3.10)
                if self.legacy_handler.is_some() {
                    // <=3.7: a REAL nested try inside the handler body —
                    // save the outer chain, let the nested chain parse in
                    // the single slots, restore before its Try is emitted
                    // (push_stmt then routes it into the outer handler body)
                    if !self.version.at_least(3, 8) {
                        self.begin_legacy_nest();
                    } else {
                        return true;
                    }
                }
                // 3.5-3.7 async-for per-iteration guard:
                //   SETUP_LOOP; iter; GET_AITER; SETUP_EXCEPT -> H;
                //   GET_ANEXT; LOAD None; YIELD_FROM; STORE; POP_BLOCK;
                //   JUMP_FORWARD -> body; H: DUP_TOP; LOAD StopAsyncIteration;
                //   COMPARE_OP exc-match; PJIT -> unwind; END_FINALLY;
                //   unwind: POP_TOP x3; POP_EXCEPT; POP_TOP; POP_BLOCK
                // The guard is loop machinery, not a source-level try:
                // open the async For block HERE (the back edge targets this
                // SETUP_EXCEPT) and absorb the handler when reached.
                if !self.version.at_least(3, 8) {
                    if let Some(t) = inst.target {
                        let is_guard = self
                            .idx_of
                            .get(&t)
                            .map_or(false, |&hi| {
                                self.instrs[hi].op == Op::DUP_TOP
                                    && self.instrs[hi + 1..]
                                        .iter()
                                        .take(3)
                                        .any(|x| {
                                            x.op == Op::LOAD_GLOBAL
                                                && self.const_name(x.arg as usize)
                                                    == "StopAsyncIteration"
                                        })
                            })
                            && self
                                .idx_of
                                .get(&inst.offset)
                                .map_or(false, |&si| {
                                    self.instrs[si + 1..]
                                        .iter()
                                        .take(2)
                                        .any(|x| x.op == Op::GET_ANEXT)
                                });
                        if is_guard {
                            // the exhaustion unwind tail starts at the
                            // guard handler's PJIT target; it ends at the
                            // POP_BLOCK whose next instruction is the loop
                            // continuation
                            let mut unwind = usize::MAX;
                            let mut exit = usize::MAX;
                            if let Some(&hi) = self.idx_of.get(&t) {
                                for k in hi..self.instrs.len().min(hi + 8) {
                                    if matches!(
                                        self.instrs[k].op,
                                        Op::POP_JUMP_IF_TRUE | Op::JUMP_FORWARD | Op::JUMP_ABSOLUTE
                                    ) && unwind == usize::MAX
                                        && k > hi
                                    {
                                        unwind = self.instrs[k].target.unwrap_or(usize::MAX);
                                    }
                                }
                                if unwind != usize::MAX {
                                    if let Some(&ui) = self.idx_of.get(&unwind) {
                                        for ins in self.instrs[ui..].iter().take(12) {
                                            if ins.op == Op::POP_BLOCK {
                                                if let Some(&pi) =
                                                    self.idx_of.get(&ins.offset)
                                                {
                                                    exit = self
                                                        .instrs
                                                        .get(pi + 1)
                                                        .map(|x| x.offset)
                                                        .unwrap_or(usize::MAX);
                                                }
                                                break;
                                            }
                                        }
                                    }
                                }
                            }
                            self.async_for_guard = Some((t, unwind, exit));
                            let mut fb =
                                Block::new(BlockType::For, inst.offset, usize::MAX);
                            fb.is_async = true;
                            fb.cond_set = true;
                            // a SETUP_LOOP placeholder may be open: absorb it
                            // (it would render as a bogus `while True`)
                            if let Some(top) = self.blocks.last() {
                                if matches!(top.kind, BlockType::While) && !top.cond_set {
                                    fb.for_setup_end = Some(top.end);
                                }
                            }
                            while let Some(top) = self.blocks.last() {
                                if matches!(top.kind, BlockType::While) && !top.cond_set {
                                    self.blocks.pop();
                                } else {
                                    break;
                                }
                            }
                            self.blocks.push(fb);
                            return true;
                        }
                    }
                }
                // stores before the try belong to the enclosing block
                if !self.pending_stores.is_empty() {
                    self.flushing = true;
                    self.flush_pending_stores();
                    self.flushing = false;
                }
                let target = inst.target.unwrap_or(inst.end());
                self.blocks.push(Block::new(BlockType::Try, inst.end(), target));
                true
            }
            Op::SETUP_FINALLY => {
                // 2.6 with statement: the enter result was stashed in a
                // synthetic temp and the setup targets WITH_CLEANUP:
                //   ctx; DUP_TOP; LOAD_ATTR __exit__; ROT_TWO;
                //   LOAD_ATTR __enter__; CALL 0; STORE _[N];
                //   SETUP_FINALLY -> WITH_CLEANUP; LOAD _[N]; DELETE; [STORE as]
                if self.version.major == 2
                    && inst.target.map_or(false, |t| {
                        self.idx_of
                            .get(&t)
                            .map_or(false, |&ti| self.instrs[ti].op == Op::WITH_CLEANUP)
                    })
                {
                    // the bound __exit__ sits on the stack; its receiver is
                    // the context manager. The no-as form POP_TOPs it right
                    // here instead of stashing it.
                    let exit_e = self.pop_expr();
                    let ctx_e = match &*exit_e {
                        Expr::Attribute { value, .. } => value.clone(),
                        _ => exit_e,
                    };
                    self.with_exits += 1;
                    let item = WithItem {
                        ctx: ctx_e,
                        target: None,
                    };
                    let start = inst.end();
                    let end = inst.target.unwrap_or(usize::MAX);
                    let mut wb = Block::new(BlockType::With, start, end);
                    wb.with_item = Some(item);
                    self.blocks.push(wb);
                    // the stashed enter result reloads as the placeholder
                    // so the following store becomes the `as` target
                    let ph = Sv::E(self.name_expr(WITH_RESULT_PLACEHOLDER));
                    for (_, v) in self.py26_temps.iter_mut() {
                        *v = ph.clone();
                    }
                    return true;
                }
                // <=3.10 async-for wrapper: SETUP_FINALLY targeting
                // END_ASYNC_FOR is loop machinery, not a source-level
                // try/finally — swallow it (GET_ANEXT opens the loop)
                if !self.version.at_least(3, 11) {
                    if let Some(t) = inst.target {
                        if self
                            .idx_of
                            .get(&t)
                            .map_or(false, |&ti| self.instrs[ti].op == Op::END_ASYNC_FOR)
                        {
                            return true;
                        }
                    }
                }
                // compiler-internal exception-state finally inside a
                // legacy handler body (e.g. `raise` in except on 3.8-3.10)
                if self.legacy_handler.is_some() {
                    // 3.3-3.7 wrap the implicit `as`-name cleanup in a
                    // SETUP_FINALLY whose handler is exactly
                    // `LOAD None; STORE n; DELETE n; END_FINALLY` (also
                    // around `raise ... from` inside except) — internal,
                    // swallow it; a REAL nested try/finally gets the
                    // nesting treatment
                    let as_cleanup = self
                        .idx_of
                        .get(&inst.target.unwrap_or(usize::MAX))
                        .map_or(false, |&ti| {
                            matches!(self.instrs[ti].op, Op::LOAD_CONST)
                                && self
                                    .code
                                    .consts
                                    .get(self.instrs[ti].arg as usize)
                                    .map_or(false, |c| matches!(&**c, PyObject::None))
                                && matches!(
                                    self.instrs.get(ti + 1).map(|x| x.op),
                                    Some(Op::STORE_FAST) | Some(Op::STORE_NAME) | Some(Op::STORE_DEREF)
                                )
                                && matches!(
                                    self.instrs.get(ti + 2).map(|x| x.op),
                                    Some(Op::DELETE_FAST) | Some(Op::DELETE_NAME) | Some(Op::DELETE_DEREF)
                                )
                                && matches!(
                                    self.instrs.get(ti + 3).map(|x| x.op),
                                    Some(Op::END_FINALLY)
                                )
                        });
                    if !self.version.at_least(3, 8) && !as_cleanup {
                        self.begin_legacy_nest();
                    } else {
                        if as_cleanup {
                            // record the wrapper's own END_FINALLY (inside
                            // the cleanup handler) so the chain machine
                            // does not mistake it for the chain end
                            if let Some(t) = inst.target {
                                if let Some(&ti) = self.idx_of.get(&t) {
                                    for ins in self.instrs[ti..].iter().take(6) {
                                        if ins.op == Op::END_FINALLY {
                                            self.as_cleanup_wrappers
                                                .push((inst.offset, ins.offset));
                                            break;
                                        }
                                    }
                                }
                            }
                        }
                        return true;
                    }
                }
                // stores before the try belong to the enclosing block
                if !self.pending_stores.is_empty() {
                    self.flushing = true;
                    self.flush_pending_stores();
                    self.flushing = false;
                }
                let target = inst.target.unwrap_or(inst.end());
                if self.version.at_least(3, 8) {
                    // 3.8+: also used for except handlers; the legacy chain
                    // machinery decides except-vs-finally at close time
                    let mut t = Block::new(BlockType::Try, inst.end(), target);
                    self.blocks.push(t);
                } else {
                    let mut cont = Block::new(BlockType::Container, inst.end(), usize::MAX);
                    cont.finally_target = Some(target);
                    self.blocks.push(cont);
                    let mut t = Block::new(BlockType::Try, inst.end(), target);
                    t.finally_target = Some(target);
                    self.blocks.push(t);
                }
                true
            }
            Op::SETUP_CLEANUP => {
                // compiler-internal exception-state finally inside a
                // legacy handler body (e.g. `raise` in except on 3.8-3.10)
                if self.legacy_handler.is_some() {
                    return true;
                }
                let target = inst.target.unwrap_or(inst.end());
                let mut t = Block::new(BlockType::Try, inst.end(), target);
                self.blocks.push(t);
                true
            }
            Op::SETUP_WITH => {
                self.handle_with_setup(inst.target, false);
                true
            }
            Op::SETUP_ASYNC_WITH => {
                self.handle_with_setup(inst.target, true);
                true
            }
            Op::BEFORE_ASYNC_WITH => {
                if self.version.at_least(3, 11) {
                    // 3.10+/3.11+: like BEFORE_WITH but awaits __aenter__
                    let ctx_e = self.pop_expr();
                    self.with_exits += 1;
                    let item = WithItem {
                        ctx: ctx_e,
                        target: None,
                    };
                    let start = inst.end();
                    let end = self
                        .with_regions
                        .get(&start)
                        .copied()
                        .or_else(|| {
                            // the __aenter__ await protocol (GET_AWAITABLE
                            // ..SEND..END_SEND, possibly a CLEANUP_THROW
                            // trampoline) sits between BEFORE_ASYNC_WITH and
                            // the protected body, so the body's exception
                            // entry starts AFTER inst.end() — scan forward
                            self.instrs
                                .iter()
                                .skip_while(|x| x.offset < start)
                                .take(20)
                                .find_map(|x| self.with_regions.get(&x.offset).copied())
                        })
                        .unwrap_or(usize::MAX);
                    let mut wb = Block::new(BlockType::With, start, end);
                    wb.is_async = true;
                    wb.with_item = Some(item);
                    self.blocks.push(wb);
                    self.push(self.name_expr(WITH_RESULT_PLACEHOLDER));
                } else {
                    // <=3.10: pushes the __aenter__ awaitable; the With block
                    // is opened by the following SETUP_ASYNC_WITH using the
                    // stashed context expression
                    let ctx_e = self.pop_expr();
                    self.pending_async_with_ctx = Some(ctx_e);
                    self.push(self.name_expr(WITH_RESULT_PLACEHOLDER));
                }
                true
            }
            Op::BEFORE_WITH => {
                // 3.11+: pushes __exit__ then result; block boundary comes
                // from the exception table entry that starts right after.
                let ctx_e = self.pop_expr();
                let result = self.pop_expr();
                self.with_exits += 1;
                let _ = result;
                let item = WithItem {
                    ctx: ctx_e,
                    target: None,
                };
                self.pending_with.push(vec![item]);
                self.push(self.name_expr(WITH_RESULT_PLACEHOLDER));
                // open a With block spanning the PROTECTED BODY: it ends
                // where the body ends (the inline __exit__ call and the
                // out-of-line cleanup handler follow). Using the handler
                // target here swallows sequential following statements
                // into the with body.
                let start = inst.end();
                let end = self
                    .with_regions
                    .get(&start)
                    .copied()
                    .or_else(|| {
                        self.exc_entries
                            .iter()
                            .find(|e| e.start == start || e.start == inst.end())
                            .map(|e| e.end)
                    })
                    .unwrap_or(usize::MAX);
                let mut wb = Block::new(BlockType::With, start, end);
                wb.is_async = false;
                self.blocks.push(wb);
                true
            }
            Op::POP_BLOCK => {
                if self.legacy_handler.is_none() {
                    self.handle_pop_block();
                }
                true
            }
            Op::POP_EXCEPT => {
                if let Some(top) = self.blocks.last() {
                    if top.kind == BlockType::Except {
                        let pos = inst.offset;
                        self.force_close_top(pos);
                    }
                }
                // POP_EXCEPT drops the (unmodeled) exception state. When
                // live body values sit on the simulated stack the cleanup
                // slots are already balanced out — popping would eat the
                // body value (3.9+ terminating handlers and 3.11+ computed
                // returns: `expr; SWAP; POP_EXCEPT; as-cleanup; RETURN`)
                let live_values = self.stack.iter().any(|s| matches!(s, Sv::E(_)));
                let next_returns = self
                    .idx_of
                    .get(&inst.offset)
                    .and_then(|&pi| self.instrs.get(pi + 1))
                    .map_or(false, |nx| {
                        matches!(nx.op, Op::RETURN_VALUE | Op::RETURN_CONST)
                    });
                if !next_returns && !live_values {
                    self.pop();
                }
                true
            }
            Op::END_FINALLY => {
                if self.legacy_handler.is_some() {
                    // internal cleanup inside a handler body
                    self.pop();
                    return true;
                }
                self.pop();
                self.close_finally();
                true
            }
            Op::WITH_CLEANUP => {
                // py2 / <=3.4: pops exception state + 3 exits
                self.pop();
                self.with_exits = self.with_exits.saturating_sub(1);
                self.handle_with_body_end();
                true
            }
            Op::WITH_CLEANUP_START => {
                self.with_exits = self.with_exits.saturating_sub(1);
                true
            }
            Op::WITH_CLEANUP_FINISH => {
                self.handle_with_body_end();
                true
            }
            Op::WITH_EXCEPT_START => {
                // 3.11+: result of __exit__ call on top; then POP_EXCEPT etc.
                self.pop();
                self.with_exits = self.with_exits.saturating_sub(1);
                true
            }
            Op::CHECK_EXC_MATCH => {
                let pattern = self.pop_expr();
                let exc = self.pop_expr();
                self.push(exc);
                self.push(pattern);
                true
            }
            Op::CHECK_EG_MATCH => {
                self.pop();
                self.pop();
                true
            }
            Op::RERAISE => {
                for _ in 0..=arg.min(2) {
                    self.pop();
                }
                true
            }
            Op::PREP_RERAISE_STAR => {
                self.pop();
                self.pop();
                true
            }
            Op::CLEANUP_THROW => {
                // 3.12+ await/resume protocols embed a CLEANUP_THROW
                // trampoline right before END_SEND (throw path of the
                // suspended YIELD_VALUE); the linear walk falls through
                // it and its pops would eat the protocol's live stack
                // (e.g. the async-with __aenter__ result placeholder).
                // Dead padding in that position — skip it.
                let next_is_end_send = self
                    .idx_of
                    .get(&self.cur_next)
                    .map_or(false, |&ni| self.instrs[ni].op == Op::END_SEND);
                if !(next_is_end_send && self.skip_end_send) {
                    self.pop();
                    self.pop();
                }
                true
            }
            Op::CALL_FINALLY => {
                // 3.8 alpha era
                let target = inst.target.unwrap_or(inst.end());
                if let Some(top) = self.blocks.last_mut() {
                    top.finally_target = Some(target);
                }
                self.stack.push(Sv::Null);
                true
            }
            Op::POP_FINALLY => {
                self.pop();
                self.close_finally();
                true
            }
            Op::JUMP_IF_NOT_EXC_MATCH => {
                let target = inst.target.unwrap_or(inst.end());
                let pattern = self.pop_expr();
                // the exception value comes from VM state we do not model;
                // popping an empty stack here is not an error
                let exc = match self.stack.pop() {
                    Some(Sv::E(e)) => e,
                    Some(_) | None => Rc::new(Expr::Name("__exc__".to_string())),
                };
                let cond = Rc::new(Expr::Compare {
                    operands: vec![exc, pattern],
                    ops: vec![CmpOp::ExceptionMatch],
                });
                self.handle_cond_jump(cond, true, target);
                true
            }
            Op::RAISE_VARARGS => match arg {
                0 => {
                    self.push_stmt(Stmt::Raise {
                        exc: None,
                        cause: None,
                    });
                    true
                }
                1 => {
                    let exc = self.pop_expr();
                    self.push_stmt(Stmt::Raise {
                        exc: Some(exc),
                        cause: None,
                    });
                    true
                }
                _ => {
                    if self.version.major == 2 {
                        // py2 `raise type, inst[, tb]`: inst popped first;
                        // render the py3-equivalent instantiation
                        if arg >= 3 {
                            let _tb = self.pop_expr();
                        }
                        let inst = self.pop_expr();
                        let ty = self.pop_expr();
                        let exc = Rc::new(Expr::Call {
                            func: ty,
                            args: vec![inst],
                            keywords: Vec::new(),
                            star_args: None,
                            star_kwargs: None,
                        });
                        self.push_stmt(Stmt::Raise {
                            exc: Some(exc),
                            cause: None,
                        });
                        return true;
                    }
                    let cause = self.pop_expr();
                    let exc = self.pop_expr();
                    self.push_stmt(Stmt::Raise {
                        exc: Some(exc),
                        cause: Some(cause),
                    });
                    true
                }
            },

            // ---------- py2 print / exec ----------
            Op::PRINT_ITEM => {
                let v = self.pop_expr();
                self.pending_print.push(v);
                true
            }
            Op::PRINT_ITEM_TO => {
                // 2.7: stream (DUPed) sits below the item; both are consumed
                let v = self.pop_expr();
                self.pop(); // this item's stream copy
                self.pending_print.push(v);
                true
            }
            Op::PRINT_NEWLINE => {
                let values = std::mem::take(&mut self.pending_print);
                let dest = self.pending_print_dest.take();
                self.push_stmt(Stmt::Print {
                    dest,
                    values,
                    newline: true,
                });
                true
            }
            Op::PRINT_NEWLINE_TO => {
                let values = std::mem::take(&mut self.pending_print);
                let dest = self.pop_expr();
                self.push_stmt(Stmt::Print {
                    dest: Some(dest),
                    values,
                    newline: true,
                });
                true
            }
            Op::PRINT_EXPR => {
                // interactive-mode only; treat as expression statement
                let e = self.pop_expr();
                self.push_stmt(Stmt::Expr(e));
                true
            }
            Op::EXEC_STMT => {
                let locals = self.pop_expr();
                let globals = self.pop_expr();
                let code = self.pop_expr();
                self.push_stmt(Stmt::Exec {
                    code,
                    globals: none_if_const_none(globals),
                    locals: none_if_const_none(locals),
                });
                true
            }

            // ---------- f-strings ----------
            Op::FORMAT_VALUE => {
                // oparg: bits 0-1 conversion (1=str 2=repr 3=ascii),
                // bit 2 = has format spec
                let conversion = match arg & 0x3 {
                    1 => Some('s'),
                    2 => Some('r'),
                    3 => Some('a'),
                    _ => None,
                };
                let format_spec = if arg & 0x04 != 0 {
                    Some(self.pop_expr())
                } else {
                    None
                };
                let value = self.pop_expr();
                let part = FStringPart::Value {
                    value,
                    conversion,
                    format_spec: format_spec.map(|f| Box::new(expr_to_fstring(f))),
                };
                self.push(Rc::new(Expr::FString(Box::new(FString {
                    parts: vec![part],
                }))));
                true
            }
            Op::FORMAT_SIMPLE => {
                let value = self.pop_expr();
                // 3.13+: CONVERT_VALUE already produced a single-part
                // f-string; reuse it instead of nesting
                if let Expr::FString(f) = &*value {
                    if f.parts.len() == 1 {
                        self.push(value);
                        return true;
                    }
                }
                let part = FStringPart::Value {
                    value,
                    conversion: None,
                    format_spec: None,
                };
                self.push(Rc::new(Expr::FString(Box::new(FString {
                    parts: vec![part],
                }))));
                true
            }
            Op::FORMAT_WITH_SPEC => {
                let spec = self.pop_expr();
                let value = self.pop_expr();
                // unwrap a CONVERT_VALUE single-part f-string, keeping its
                // conversion flag
                let (value, conversion) = match &*value {
                    Expr::FString(f) if f.parts.len() == 1 => {
                        match &f.parts[0] {
                            FStringPart::Value {
                                value: v,
                                conversion: c,
                                format_spec: None,
                            } => (v.clone(), *c),
                            _ => (value, None),
                        }
                    }
                    _ => (value, None),
                };
                let part = FStringPart::Value {
                    value,
                    conversion,
                    format_spec: Some(Box::new(expr_to_fstring(spec))),
                };
                self.push(Rc::new(Expr::FString(Box::new(FString {
                    parts: vec![part],
                }))));
                true
            }
            Op::CONVERT_VALUE => {
                let value = self.pop_expr();
                let conversion = match arg {
                    1 => Some('s'),
                    2 => Some('r'),
                    3 => Some('a'),
                    _ => None,
                };
                let part = FStringPart::Value {
                    value,
                    conversion,
                    format_spec: None,
                };
                self.push(Rc::new(Expr::FString(Box::new(FString {
                    parts: vec![part],
                }))));
                true
            }

            // ---------- annotations ----------
            Op::STORE_ANNOTATION => {
                // 3.6.0 only: [value?, annotation] — CPython: TOS=ann, TOS1=name
                let ann = self.pop_expr();
                let target = self.pop_expr();
                self.push_stmt(Stmt::AnnAssign {
                    target,
                    annotation: ann,
                    value: None,
                });
                true
            }

            // ---------- match (3.10+) — not yet supported ----------
            Op::GET_LEN
            | Op::MATCH_KEYS
            | Op::MATCH_MAPPING
            | Op::MATCH_SEQUENCE
            | Op::MATCH_CLASS => {
                self.unimplemented(inst, "match/case");
                true
            }
            Op::CALL_INTRINSIC_1 | Op::CALL_INTRINSIC_2 => {
                // 3.11: {1: async_gen_wrap, 2: import_star};
                // 3.12+: {2: import_star} (verified against real bytecode)
                let import_star = arg == 2;
                if import_star && inst.op == Op::CALL_INTRINSIC_1 {
                    if let Some(Sv::ImportModule { level, module, .. }) = self.pop() {
                        self.push_stmt(Stmt::ImportFrom {
                            module,
                            level,
                            names: vec![("*".to_string(), None)],
                        });
                    }
                    // the intrinsic leaves a result that POP_TOP discards
                    self.push(Rc::new(Expr::Const(Rc::new(PyObject::None))));
                }
                // all other intrinsics are value-preserving pass-throughs
                true
            }

            Op::Unknown => {
                self.unimplemented(inst, "unknown opcode");
                true
            }
            other => {
                self.unimplemented(inst, "unsupported opcode");
                let _ = other;
                true
            }
        };
        // statements flush any pending multi-store group; pure stack
        // manipulation and further stores do not
        if !is_stack_plumbing(inst.op) && !is_store_op(inst.op) {
            self.flush_pending_stores();
        }
        cont
    }

    /// Flush a group of stores that share one source line as a simultaneous
    /// assignment (`a, b = b, a + b`) or a chained assignment (`a = b = e`).
    fn group_has_swap(&self) -> bool {
        self.instrs
            .iter()
            .skip_while(|i| i.offset <= self.last_flush_offset)
            .take_while(|i| i.offset <= self.cur_offset)
            .any(|i| {
                matches!(
                    i.op,
                    Op::SWAP | Op::ROT_TWO | Op::ROT_THREE | Op::ROT_FOUR | Op::ROT_N
                )
            })
    }

    fn flush_pending_stores(&mut self) {
        if self.pending_stores.len() >= 2 {
            let group = std::mem::take(&mut self.pending_stores);
            self.last_store_line = None;
            let all_same = group.windows(2).all(|w| expr_eq(&w[0].1, &w[1].1));
            if all_same {
                let value = group[0].1.clone();
                let targets: Vec<ExprRef> = group.iter().map(|(t, _)| t.clone()).collect();
                self.push_stmt(Stmt::Assign { targets, value });
            } else {
                // simultaneous assignment from consecutive stores. Store
                // order is reversed relative to source when the compiler
                // used the ROT/SWAP-free overlapping-values trick (3.12+);
                // an explicit SWAP/ROT inside the group means the values
                // were pre-arranged and stores follow source order.
                let has_swap = self.group_has_swap();
                let (targets, values): (Vec<ExprRef>, Vec<ExprRef>) = if has_swap {
                    (
                        group.iter().map(|(t, _)| t.clone()).collect(),
                        group.iter().map(|(_, v)| v.clone()).collect(),
                    )
                } else {
                    (
                        group.iter().rev().map(|(t, _)| t.clone()).collect(),
                        group.iter().rev().map(|(_, v)| v.clone()).collect(),
                    )
                };
                self.push_stmt(Stmt::Assign {
                    targets: vec![Rc::new(Expr::Tuple(targets))],
                    value: Rc::new(Expr::Tuple(values)),
                });
            }
        } else if self.pending_stores.len() == 1 {
            let (t, v) = self.pending_stores.pop().unwrap();
            self.last_store_line = None;
            self.push_stmt(Stmt::Assign {
                targets: vec![t],
                value: v,
            });
        } else {
            self.last_store_line = None;
        }
    }
}

/// Store opcodes participate in the pending group without flushing it.
fn is_store_op(op: Op) -> bool {
    matches!(
        op,
        Op::STORE_FAST
            | Op::STORE_FAST_MAYBE_NULL
            | Op::STORE_FAST_LOAD_FAST
            | Op::STORE_FAST_STORE_FAST
            | Op::STORE_NAME
            | Op::STORE_GLOBAL
            | Op::STORE_DEREF
    )
}

/// Opcodes that only move values around and must not flush a pending
/// multi-store group.
fn is_stack_plumbing(op: Op) -> bool {
    matches!(
        op,
        Op::POP_TOP
            | Op::ROT_TWO
            | Op::ROT_THREE
            | Op::ROT_FOUR
            | Op::ROT_N
            | Op::SWAP
            | Op::DUP_TOP
            | Op::DUP_TOP_TWO
            | Op::DUP_TOPX
            | Op::COPY
            | Op::PUSH_NULL
            | Op::NOP
            | Op::CACHE
            | Op::RESUME
            | Op::RESUME_CHECK
            | Op::PRECALL
            | Op::EXTENDED_ARG
            | Op::TO_BOOL
            | Op::UNPACK_SEQUENCE
            | Op::UNPACK_EX
    )
}

// =====================  control-flow handlers  =====================

impl<'a> Ctx<'a> {
    /// Conditional jump. `jump_if_true` = the branch taken when the
    /// condition holds.
    /// py2.7 boolean-op if-conditions. `(a or b) and c` compiles to
    /// `J1: PJIT L; <a-false rhs> J0: PJIF E; L: <rhs c> J2: PJIF E; then; E:`
    /// where J1's target region also ends in a cond jump to the same E.
    /// Returns the merged (cond, then_end) when the pattern matches.
    /// 3.14 inline all/any guard: validate the fast-path shape and return
    /// the slow-path (generic call) offset. `is_all` selects the expected
    /// builtin constant index (3 = all, 4 = any).
    fn inline_all_any_slow_path(&self, is_all: bool) -> Option<usize> {
        let ci = self.idx_of.get(&self.cur_offset).copied()?;
        // guard: COPY 1 before, IS_OP 0 + forward PJIF after
        if self.instrs.get(ci.wrapping_sub(1)).map(|x| (x.op, x.arg))
            != Some((Op::COPY, 1))
        {
            return None;
        }
        let isop = self.instrs.get(ci + 1)?;
        if isop.op != Op::IS_OP || isop.arg != 0 {
            return None;
        }
        let pjif = self.instrs.get(ci + 2)?;
        if pjif.op != Op::POP_JUMP_IF_FALSE {
            return None;
        }
        let slow = pjif.target?;
        if slow <= pjif.offset {
            return None;
        }
        let &si = self.idx_of.get(&slow)?;
        if self.instrs.get(si).map(|x| x.op) != Some(Op::PUSH_NULL) {
            return None;
        }
        // slow path: PUSH_NULL; LOAD_CONST <genexpr code>; MAKE_FUNCTION;
        // <iterable>; GET_ITER; CALL 0; CALL 1
        let lc = self.instrs.get(si + 1)?;
        if lc.op != Op::LOAD_CONST {
            return None;
        }
        match self.code.consts.get(lc.arg as usize).map(|o| &**o) {
            Some(PyObject::Code(c)) if c.name == "<genexpr>" => {}
            _ => return None,
        }
        if self.instrs.get(si + 2).map(|x| x.op) != Some(Op::MAKE_FUNCTION) {
            return None;
        }
        let mut k = si + 3;
        let mut saw_get_iter = false;
        let mut call0 = None;
        while let Some(ins) = self.instrs.get(k) {
            match ins.op {
                Op::GET_ITER => saw_get_iter = true,
                Op::CALL if ins.arg == 0 => {
                    call0 = Some(k);
                    break;
                }
                op if is_pure_value_op(op) => {}
                _ => return None,
            }
            k += 1;
        }
        let c0 = call0?;
        if !saw_get_iter {
            return None;
        }
        if self.instrs.get(c0 + 1).map(|x| (x.op, x.arg)) != Some((Op::CALL, 1)) {
            return None;
        }
        // fast path [guard end, slow): must hold the inline generator loop
        let fast_start = ci + 3;
        let mut saw_for_iter = false;
        for ins in self.instrs.iter().skip(fast_start) {
            if ins.offset >= slow {
                break;
            }
            if ins.op == Op::FOR_ITER {
                saw_for_iter = true;
            }
        }
        if !saw_for_iter {
            return None;
        }
        let _ = is_all;
        Some(slow)
    }

    /// py2.6 statement boolop chain fold. Every link compiles to
    /// `JUMP_IF_* L; POP_TOP` (the peek-jump keeps the operand for the
    /// escape path, the POP drops it on fall-through):
    ///
    /// ```text
    ///   eval A; JIF Lelse; POP; eval B; JIF Lelse; POP; THEN ...
    ///   Lelse: POP; ELSE
    ///   eval C; JIT Lmerge; POP; eval D; JIF Lelse; Lmerge: POP; THEN
    /// ```
    ///
    /// `first` is operand 0 (on the live stack; the caller pops it on
    /// success). Each link's polarity combines the operand BEFORE it with
    /// the chain that follows: JIF escape = And, JIT escape = Or. The
    /// chain ends when the region after a link's POP_TOP is no longer
    /// pure-value-then-peek-jump (that region is the THEN body). Returns
    /// (merged cond, then_start, else_body_start, else_pop_offset).
    fn py26_stmt_boolop_chain(
        &self,
        i0: usize,
        first: ExprRef,
        jump_if_true: bool,
        target: usize,
    ) -> Option<(ExprRef, usize, usize, usize)> {
        // link 0's target must hold the escape-path POP_TOP
        let &t0i = self.idx_of.get(&target)?;
        if self.instrs.get(t0i).map(|x| x.op) != Some(Op::POP_TOP) {
            return None;
        }
        // pending = (operand, link polarity) pairs awaiting the tail
        let mut pending: Vec<(ExprRef, bool)> = vec![(first, jump_if_true)];
        let mut last_target = target;
        let mut k = i0 + 1;
        // POP_TOP dropping operand 0 on fall-through
        if self.instrs.get(k).map(|x| x.op) != Some(Op::POP_TOP) {
            return None;
        }
        k += 1;
        let tail;
        loop {
            // scan the next operand region: pure value ops up to a peek-jump
            let region_start = k;
            let mut link = None;
            while let Some(ins) = self.instrs.get(k) {
                if matches!(ins.op, Op::JUMP_IF_FALSE | Op::JUMP_IF_TRUE)
                    && ins.target.map_or(false, |t| t > ins.offset)
                {
                    link = Some(k);
                    break;
                }
                if !is_pure_value_op(ins.op) && ins.op != Op::POP_TOP {
                    return None;
                }
                k += 1;
            }
            let lk = link?;
            if lk == region_start {
                return None;
            }
            let operand = self.sim_value_region(region_start, lk)?;
            let lins = self.instrs[lk];
            let lt = lins.target?;
            // the link target must hold the escape POP_TOP
            let &lti = self.idx_of.get(&lt)?;
            if self.instrs.get(lti).map(|x| x.op) != Some(Op::POP_TOP) {
                return None;
            }
            let ljit = lins.op == Op::JUMP_IF_TRUE;
            // POP_TOP dropping this operand on fall-through
            k = lk + 1;
            if self.instrs.get(k).map(|x| x.op) != Some(Op::POP_TOP) {
                return None;
            }
            k += 1;
            // another link follows, or is [k, ..) the THEN body? Probe:
            // pure value ops then a forward peek-jump whose target holds
            // POP_TOP → another link. Anything else → body.
            let mut p = k;
            let mut more = false;
            while let Some(ins) = self.instrs.get(p) {
                if matches!(ins.op, Op::JUMP_IF_FALSE | Op::JUMP_IF_TRUE)
                    && ins.target.map_or(false, |t| t > ins.offset)
                {
                    if let Some(t) = ins.target {
                        if let Some(&nti) = self.idx_of.get(&t) {
                            if self.instrs.get(nti).map(|x| x.op) == Some(Op::POP_TOP) {
                                more = true;
                            }
                        }
                    }
                    break;
                }
                if !is_pure_value_op(ins.op) {
                    break;
                }
                p += 1;
            }
            if !more {
                // this link was the statement jump: its fall-through POP
                // was just consumed; the operand is the chain tail
                tail = operand;
                last_target = lt;
                break;
            }
            pending.push((operand, ljit));
        }
        // fold right-associatively from the tail: cond = tail, then each
        // pending (operand, polarity) wraps it — And for JIF, Or for JIT
        let mut cond = tail;
        for (operand, jit) in pending.into_iter().rev() {
            let kind = if jit { BoolOpKind::Or } else { BoolOpKind::And };
            let mut values = Vec::new();
            flatten_boolop(operand, kind, &mut values);
            flatten_boolop(cond, kind, &mut values);
            cond = Rc::new(Expr::BoolOp { op: kind, values });
        }
        // final link: fall-through after its POP_TOP is the THEN body;
        // the escape POP_TOP at last_target leads the ELSE body
        let then_start = self.instrs.get(k).map(|x| x.offset)?;
        let &lti = self.idx_of.get(&last_target)?;
        let else_body = self.instrs.get(lti + 1).map(|x| x.offset)?;
        Some((cond, then_start, else_body, last_target))
    }

    fn try_merge_py2_boolop(
        &self,
        cond: &ExprRef,
        jump_if_true: bool,
        target: usize,
    ) -> Option<(ExprRef, usize, usize)> {
        macro_rules! bail {
            ($why:expr) => {
                return None
            };
        }
        let instrs = &self.instrs;
        let is_value_op = |o: Op| {
            matches!(
                o,
                Op::LOAD_FAST
                    | Op::LOAD_NAME
                    | Op::LOAD_GLOBAL
                    | Op::LOAD_CONST
                    | Op::LOAD_ATTR
                    | Op::LOAD_DEREF
                    | Op::LOAD_METHOD
                    | Op::LOAD_BUILD_CLASS
                    | Op::COMPARE_OP
                    | Op::IS_OP
                    | Op::CONTAINS_OP
                    | Op::BINARY_OP
                    | Op::BINARY_SUBSCR
                    | Op::CALL
                    | Op::CALL_FUNCTION
                    | Op::CALL_METHOD
                    | Op::CALL_FUNCTION_KW
                    | Op::BUILD_TUPLE
                    | Op::BUILD_LIST
                    | Op::BUILD_MAP
                    | Op::BUILD_SET
                    | Op::BUILD_STRING
                    | Op::UNARY_NOT
                    | Op::UNARY_NEGATIVE
                    | Op::UNARY_INVERT
                    | Op::TO_BOOL
                    | Op::FORMAT_VALUE
                    | Op::GET_ITER
                    | Op::LIST_EXTEND
                    | Op::SET_ADD
                    | Op::MAP_ADD
                    | Op::COPY
                    | Op::NOP
            )
        };
        let is_cond_jump = |o: Op| {
            matches!(
                o,
                Op::POP_JUMP_IF_FALSE
                    | Op::POP_JUMP_IF_TRUE
                    | Op::POP_JUMP_FORWARD_IF_FALSE
                    | Op::POP_JUMP_FORWARD_IF_TRUE
                    | Op::POP_JUMP_BACKWARD_IF_FALSE
                    | Op::POP_JUMP_BACKWARD_IF_TRUE
            )
        };
        // scan the fall-through region [cur_next, target) for its terminating
        // cond jump; everything before it must be pure value computation
        let Some(&ci) = self.idx_of.get(&self.cur_offset) else {
            bail!("no ci");
        };
        let Some(&ti) = self.idx_of.get(&target) else {
            bail!("no ti");
        };
        if ti <= ci + 1 {
            bail!("ti too close");
        }
        let mut j0 = None;
        for k in ci + 1..ti {
            let ins = &instrs[k];
            if is_cond_jump(ins.op) && ins.target.unwrap_or(0) > target {
                j0 = Some((k, ins.target.unwrap_or(0), ins.op));
                break;
            }
            if !is_value_op(ins.op) {
                bail!(format!("lhs op {:?}", ins.op));
            }
        }
        let (j0k, e0, j0op) = match j0 { Some(x) => x, None => bail!("no j0") };
        let _ = (j0k, j0op);
        // scan the target (rhs) region [target, e0): value ops then a cond
        // jump. Shape A: that jump also targets e0 (shared exit E):
        //   (c1 OP c2) AND c3. Shape B: it targets some E != e0 (e0 is the
        //   then-body): (c1 OP c2) OR c3.
        let Some(&ei) = self.idx_of.get(&e0) else {
            bail!("no ei");
        };
        if ei <= ti {
            bail!("ei <= ti");
        }
        let mut j2 = None;
        let mut j2k = 0usize;
        let mut j2_target = 0usize;
        for k in ti..ei {
            let ins = &instrs[k];
            if is_cond_jump(ins.op) {
                if let Some(t) = ins.target {
                    if t > self.cur_offset {
                        j2 = Some(ins.op);
                        j2k = k;
                        j2_target = t;
                        break;
                    }
                }
                bail!("rhs jump backward");
            }
            if !is_value_op(ins.op) {
                bail!(format!("rhs op {:?}", ins.op));
            }
        }
        let j2op = match j2 { Some(x) => x, None => bail!("no j2") };
        let then_start = instrs[j2k].end();
        let e = j2_target;
        // J1 semantics: c1_jit=true means c1 joins when TRUE (or)
        let c1_true = jump_if_true;
        let c2_true = matches!(
            j0op,
            Op::POP_JUMP_IF_TRUE | Op::POP_JUMP_FORWARD_IF_TRUE | Op::POP_JUMP_BACKWARD_IF_TRUE
        );
        let c3_true = matches!(
            j2op,
            Op::POP_JUMP_IF_TRUE | Op::POP_JUMP_FORWARD_IF_TRUE | Op::POP_JUMP_BACKWARD_IF_TRUE
        );
        // shape validity is enforced by the region scans and target
        // relations; J0/J2 polarities decide the operators below
        // c1 and c2 combine via c1's jump polarity (both reach the rhs
        // region when "joining"). Outer: shared exit (shape A) -> And with
        // c3; J0 jumping to the then-body (shape B) -> Or with c3.
        let inner_kind = if c1_true { BoolOpKind::Or } else { BoolOpKind::And };
        let outer_kind = if j2_target == e0 {
            BoolOpKind::And
        } else {
            BoolOpKind::Or
        };
        let _ = (c2_true, c3_true);
        // simulate both operand regions on a scratch stack
        let lhs_e = match self.sim_value_region(ci + 1, j0k) { Some(x) => x, None => bail!("lhs sim") };
        let rhs_e = match self.sim_value_region(ti, j2k) { Some(x) => x, None => bail!("rhs sim") };
        let lhs = Rc::new(Expr::BoolOp {
            op: inner_kind,
            values: vec![cond.clone(), lhs_e],
        }) as ExprRef;
        let merged = Rc::new(Expr::BoolOp {
            op: outer_kind,
            values: vec![lhs, rhs_e],
        }) as ExprRef;
        Some((merged, then_start, e))
    }

    /// Detect `if a or b: body` / mixed and-chains: J1 (this jump) targets
    /// the body start; [next, target) is a pure operand region ending in an
    /// opposite-polarity cond jump J0 to the if exit; the merged If covers
    /// [target, J0.target). Returns (cond, body_start, exit).
    fn try_merge_or_cond(
        &self,
        cond: &ExprRef,
        jump_if_true: bool,
        target: usize,
    ) -> Option<(ExprRef, usize, usize)> {
        // General same-body boolop condition chains:
        //   `if a or b or c: BODY else: ELSE` compiles to a sequence of
        //   pure operand regions each terminated by a cond jump; jumps to
        //   BODY-start mean "operand joins on jump", the final jump to the
        //   if-exit means "operand joins on fall-through". Two-operand
        //   same-exit chains (`a and b`) are handled by the split-cond
        //   merge instead; require at least one body-targeting jump here.
        let is_cond_jump = |o: Op| {
            matches!(
                o,
                Op::POP_JUMP_IF_FALSE
                    | Op::POP_JUMP_IF_TRUE
                    | Op::POP_JUMP_FORWARD_IF_FALSE
                    | Op::POP_JUMP_FORWARD_IF_TRUE
            )
        };
        let jump_true =
            |o: Op| matches!(o, Op::POP_JUMP_IF_TRUE | Op::POP_JUMP_FORWARD_IF_TRUE);
        let Some(&ci) = self.idx_of.get(&self.cur_offset) else {
            return None;
        };
        let Some(&ti) = self.idx_of.get(&target) else {
            return None;
        };
        if ti <= ci + 1 || ti >= self.instrs.len() {
            return None;
        }
        // operand 1 joins via this jump
        let mut parts: Vec<ExprRef> = vec![if jump_if_true {
            cond.clone()
        } else {
            Rc::new(Expr::Unary { op: UnaryOp::Not, operand: cond.clone() })
        }];
        // J1 itself targets the body start — it is the first body jump
        let mut body_jumps = 1usize;
        let mut k = ci + 1;
        let mut exit: Option<usize> = None;
        let mut final_was_exit_jump = false;
        loop {
            // scan the next pure operand region up to its cond jump
            let region_start = k;
            let mut jidx = None;
            while k < self.instrs.len() {
                let ins = &self.instrs[k];
                if is_cond_jump(ins.op) {
                    jidx = Some(k);
                    break;
                }
                if !is_pure_value_op(ins.op) || ins.offset >= target {
                    return None;
                }
                k += 1;
            }
            let jk = jidx?;
            let operand = self.sim_value_region(region_start, jk)?;
            let jins = &self.instrs[jk];
            let jt = jump_true(jins.op);
            match jins.target {
                Some(t) if t == target => {
                    // jumps to the body: operand joins when the jump fires
                    parts.push(if jt {
                        operand
                    } else {
                        Rc::new(Expr::Unary { op: UnaryOp::Not, operand })
                    });
                    body_jumps += 1;
                    k = jk + 1;
                    if k >= ti {
                        return None; // no final operand before the body
                    }
                }
                Some(t) if t > target && self.idx_of.contains_key(&t) => {
                    // final operand: its jump skips the body (if exit) and
                    // must be the last instruction before the body starts
                    // (3.14 pads the body head with NOT_TAKEN)
                    let mut nj = jk + 1;
                    while matches!(
                        self.instrs.get(nj).map(|x| x.op),
                        Some(Op::NOT_TAKEN) | Some(Op::NOP)
                    ) {
                        nj += 1;
                    }
                    if nj != ti {
                        return None;
                    }
                    parts.push(if jt {
                        Rc::new(Expr::Unary { op: UnaryOp::Not, operand })
                    } else {
                        operand
                    });
                    exit = Some(t);
                    final_was_exit_jump = true;
                    break;
                }
                _ => return None,
            }
        }
        let exit = match exit {
            Some(e) => e,
            None => {
                // every operand jumped to the body (`not a or not b`): the
                // fall-through region between the chain and the body is the
                // ELSE; find its terminating forward jump
                if body_jumps < 2 {
                    return None;
                }
                let mut e2 = None;
                for m in k..ti {
                    let ins = &self.instrs[m];
                    if !is_pure_value_op(ins.op) {
                        if matches!(ins.op, Op::JUMP_FORWARD | Op::JUMP)
                            && ins.target.map_or(false, |t| t > target)
                            && m + 1 == ti
                        {
                            e2 = ins.target;
                        }
                        break;
                    }
                }
                e2?
            }
        };
        if body_jumps == 0 || parts.len() < 2 {
            return None;
        }
        // mixed chains combine as Or; all-body-jump chains are the De Morgan
        // dual: And of the (negated) join forms
        let op = if final_was_exit_jump {
            BoolOpKind::Or
        } else {
            BoolOpKind::And
        };
        // don't fire inside loops whose exit this might be (break shape)
        if self.find_loop_exit(exit).is_some() || self.find_loop_exit(target).is_some() {
            return None;
        }
        // rotated `while a or b:` — the body region loops back to this
        // condition; leave it to the while machinery
        if let (Some(&bi), Some(&ei)) = (self.idx_of.get(&target), self.idx_of.get(&exit)) {
            if self.instrs[bi..ei]
                .iter()
                .any(|x| x.is_backward && x.target.map_or(false, |t| t <= self.cur_offset))
            {
                return None;
            }
        }
        let merged = Rc::new(Expr::BoolOp { op, values: parts }) as ExprRef;
        Some((merged, target, exit))
    }

    /// Fused `if a or b [or c]: continue` chain (common on py2): the first
    /// operand's cond jump targets the LOOP TOP; further operands jump to
    /// the loop top as well, and the last one jumps forward over a body
    /// that is exactly a back-edge jump. Returns (cond, body_start,
    /// body_end).
    /// Polarity of the conditional jump at instruction index `ci`.
    fn jump_if_true_at_ci(&self, ci: usize) -> bool {
        matches!(
            self.instrs.get(ci).map(|i| i.op),
            Some(Op::POP_JUMP_IF_TRUE) | Some(Op::POP_JUMP_FORWARD_IF_TRUE)
        )
    }

    fn try_or_continue_chain(
        &self,
        loop_top: usize,
        first_cond: &ExprRef,
    ) -> Option<(ExprRef, usize, usize)> {

        let is_cond_jump = |o: Op| {
            matches!(
                o,
                Op::POP_JUMP_IF_FALSE
                    | Op::POP_JUMP_IF_TRUE
                    | Op::POP_JUMP_FORWARD_IF_FALSE
                    | Op::POP_JUMP_FORWARD_IF_TRUE
            )
        };
        let jump_true =
            |o: Op| matches!(o, Op::POP_JUMP_IF_TRUE | Op::POP_JUMP_FORWARD_IF_TRUE);
        let Some(&ci) = self.idx_of.get(&self.cur_offset) else {
            return None;
        };
        let mut parts: Vec<ExprRef> = vec![first_cond.clone()];
        // operands collected via jumps to the loop top, with their polarity
        let mut top_parts: Vec<ExprRef> = vec![first_cond.clone()];
        let mut top_jumps_true = true;
        let mut top_jumps_false = true;
        let mut k = ci + 1;
        let mut exit: Option<usize> = None;
        let mut body_start = 0usize;
        loop {
            let region_start = k;
            let mut jidx = None;
            while k < self.instrs.len() {
                let ins = &self.instrs[k];
                if is_cond_jump(ins.op) {
                    jidx = Some(k);
                    break;
                }
                if !is_pure_value_op(ins.op) {
                    // not an operand region any more — the body starts here
                    break;
                }
                k += 1;
            }
            let jk = match jidx {
                Some(x) => x,
                None => {
                    // no further operand jump: the body starts right here
                    // (all operands short-circuit to the loop top and the
                    // body is a bare continue/break jump)
                    let mut m = region_start;
                    let mut body_jump: Option<(usize, usize)> = None;
                    while m < self.instrs.len() {
                        let ins = &self.instrs[m];
                        if ins.op == Op::POP_TOP || ins.op == Op::NOP {
                            m += 1;
                            continue;
                        }
                        if let Some(t) = ins.target {
                            let back = ins.is_backward
                                && t == loop_top
                                && matches!(
                                    ins.op,
                                    Op::JUMP_ABSOLUTE
                                        | Op::JUMP_BACKWARD
                                        | Op::JUMP_BACKWARD_NO_INTERRUPT
                                );
                            // a forward UNCONDITIONAL jump leaving the loop
                            // block is the `break` (it may fly over a
                            // for-else region); a conditional jump here is
                            // the rotated-while's duplicated exit test
                            let fwd_exit = !ins.is_backward
                                && matches!(
                                    ins.op,
                                    Op::JUMP_ABSOLUTE
                                        | Op::JUMP_FORWARD
                                        | Op::JUMP
                                        | Op::JUMP_NO_INTERRUPT
                                )
                                && self
                                    .blocks
                                    .iter()
                                    .rev()
                                    .find(|b| {
                                        matches!(b.kind, BlockType::While | BlockType::For)
                                            && b.start == loop_top
                                    })
                                    .map_or(false, |b| t >= b.end);
                            if back || fwd_exit {
                                body_jump = Some((ins.end(), t));
                                break;
                            }
                        }
                        // mixed/plain continue-guard chain: every operand
                        // jumps to the loop top and a REAL body follows,
                        // ending at the loop's back edge. The body runs
                        // only when no jump fired: And-merge with each
                        // operand normalized by its jump polarity (PJIF
                        // guard = operand, PJIT guard = Not operand).
                        // Uniform-polarity chains keep the historical Or/And
                        // forms (corpus-verified); the And-normalization is
                        // for MIXED chains only, where no historical merge
                        // applied.
                        let first_jt = self.jump_if_true_at_ci(ci);
                        let uniform = (top_jumps_true && first_jt)
                            || (top_jumps_false && !first_jt);
                        if uniform {
                            return None;
                        }
                        let mut m = region_start;
                        let mut back_edge: Option<usize> = None;
                        let mut failed = false;
                        while m < self.instrs.len() {
                            let ins = &self.instrs[m];
                            if ins.is_backward
                                && ins.target == Some(loop_top)
                                && matches!(
                                    ins.op,
                                    Op::JUMP_ABSOLUTE
                                        | Op::JUMP_BACKWARD
                                        | Op::JUMP_BACKWARD_NO_INTERRUPT
                                )
                            {
                                back_edge = Some(ins.offset);
                                break;
                            }
                            if let Some(t) = ins.target {
                                // a break jump out of the loop ends the
                                // body region as well
                                let leaves = self
                                    .blocks
                                    .iter()
                                    .rev()
                                    .find(|b| {
                                        matches!(b.kind, BlockType::While | BlockType::For)
                                            && b.start == loop_top
                                    })
                                    .map_or(false, |b| {
                                        !ins.is_backward
                                            && self
                                                .loop_exit_offset(b)
                                                .map_or(false, |le| {
                                                    self.effective_offset(t)
                                                        == self.effective_offset(le)
                                                })
                                    });
                                if leaves {
                                    back_edge = Some(t);
                                    break;
                                }
                                failed = true;
                                break;
                            }
                            m += 1;
                        }
                        if failed {
                            return None;
                        }
                        let body_end_off = match back_edge {
                            Some(b) => b,
                            None => return None,
                        };
                        if body_end_off <= region_start {
                            return None;
                        }
                        // operand polarities: replay the chain jumps with
                        // their operand regions (a PJIF guard keeps its
                        // operand, a PJIT guard negates it)
                        let mut guard_parts: Vec<ExprRef> = Vec::new();
                        {
                            let mut region = ci + 1;
                            let mut kk = ci + 1;
                            while kk < self.instrs.len() {
                                let ins = &self.instrs[kk];
                                if is_cond_jump(ins.op) {
                                    if ins.target != Some(loop_top) {
                                        break;
                                    }
                                    match self.sim_value_region(region, kk) {
                                        Some(op) => {
                                            guard_parts.push(if jump_true(ins.op) {
                                                Rc::new(Expr::Unary {
                                                    op: UnaryOp::Not,
                                                    operand: op,
                                                })
                                            } else {
                                                op
                                            });
                                        }
                                        None => return None,
                                    }
                                    kk += 1;
                                    region = kk;
                                } else if !is_pure_value_op(ins.op) {
                                    break;
                                } else {
                                    kk += 1;
                                }
                            }
                        }
                        if guard_parts.is_empty() {
                            return None;
                        }
                        let mut values = Vec::new();
                        let first_norm = if self.jump_if_true_at_ci(ci) {
                            Rc::new(Expr::Unary {
                                op: UnaryOp::Not,
                                operand: first_cond.clone(),
                            })
                        } else {
                            first_cond.clone()
                        };
                        flatten_boolop(first_norm, BoolOpKind::And, &mut values);
                        for gp in guard_parts {
                            flatten_boolop(gp, BoolOpKind::And, &mut values);
                        }
                        if values.len() < 2 {
                            return None;
                        }
                        let merged: ExprRef = Rc::new(Expr::BoolOp {
                            op: BoolOpKind::And,
                            values,
                        });
                        let body_off = self.instrs.get(region_start).map(|i| i.offset)?;
                        return Some((merged, body_off, body_end_off));
                    }
                    let (body_end, body_t) = body_jump?;
                    let op = if top_jumps_true {
                        BoolOpKind::Or
                    } else {
                        BoolOpKind::And
                    };
                    let vals = if top_jumps_true { parts } else { top_parts };
                    let merged: ExprRef = if vals.len() >= 2 {
                        Rc::new(Expr::BoolOp { op, values: vals })
                    } else if !self.jump_if_true_at_ci(ci)
                        && body_t != loop_top
                        && !matches!(
                            self.instrs.get(ci).map(|i| i.op),
                            Some(Op::POP_JUMP_BACKWARD_IF_TRUE)
                                | Some(Op::POP_JUMP_BACKWARD_IF_FALSE)
                        )
                    {
                        // single operand `if c: break`: the PJIF jumps to
                        // the loop top (continue) and the fall-through body
                        // is the break jump. BACKWARD cond-jump variants are
                        // rotated-while re-entries, never this shape.
                        first_cond.clone()
                    } else {
                        return None;
                    };
                    let body_off = self.instrs.get(region_start).map(|i| i.offset)?;
                    return Some((merged, body_off, body_end));
                }
            };
            let operand = self.sim_value_region(region_start, jk)?;
            let jins = &self.instrs[jk];
            let jt = jump_true(jins.op);
            if jins.target == Some(loop_top) {
                // another operand short-circuiting to the loop top
                if jt {
                    // jumps to top when TRUE: `if a or ...: continue`
                    parts.push(operand.clone());
                }
                // jumps to top when FALSE: the body needs every operand
                // true (`if a and ...: break`) — raw participation
                top_parts.push(operand);
                top_jumps_true = top_jumps_true && jt;
                top_jumps_false = top_jumps_false && !jt;
                k = jk + 1;
                continue;
            }
            if let Some(t) = jins.target {
                if t > self.cur_offset && self.idx_of.contains_key(&t) {
                    parts.push(if jt {
                        Rc::new(Expr::Unary { op: UnaryOp::Not, operand })
                    } else {
                        operand
                    });
                    exit = Some(t);
                    body_start = self.instrs[jk].end();
                    break;
                }
            }
            return None;
        }
        let exit = match exit {
            Some(x) => x,
            None => return None,
        };
        if parts.len() < 2 {
            return None;
        }
        // the body between the chain and the exit must be exactly the
        // continue back edge (plus optional dead padding jumps)
        let Some(&bsi) = self.idx_of.get(&body_start) else {
            return None;
        };
        let Some(&ei) = self.idx_of.get(&exit) else {
            return None;
        };
        if ei <= bsi {
            return None;
        }
        // the body must leave the loop immediately: a back edge to the top
        // (`continue`) or a forward jump to the loop exit (`break`, which
        // 3.8 prefixes with POP_TOP), plus dead padding
        let loop_exit = self
            .blocks
            .iter()
            .rev()
            .find(|b| matches!(b.kind, BlockType::While | BlockType::For) && b.start == loop_top)
            .and_then(|b| self.loop_exit_offset(b));
        let mut saw_exit_jump = false;
        for m in bsi..ei {
            let ins = &self.instrs[m];
            if let Some(t) = ins.target {
                let back_to_top = ins.is_backward
                    && t == loop_top
                    && matches!(
                        ins.op,
                        Op::JUMP_ABSOLUTE
                            | Op::JUMP_BACKWARD
                            | Op::JUMP_BACKWARD_NO_INTERRUPT
                    );
                let fwd_to_exit = !ins.is_backward
                    && loop_exit.map_or(false, |le| {
                        self.effective_offset(t) == self.effective_offset(le)
                    });
                if back_to_top || fwd_to_exit {
                    saw_exit_jump = true;
                    continue;
                }
            }
            if matches!(ins.op, Op::JUMP_FORWARD | Op::JUMP | Op::NOP | Op::POP_TOP) {
                continue;
            }
            return None;
        }
        if !saw_exit_jump {
            return None;
        }
        let merged = Rc::new(Expr::BoolOp {
            op: BoolOpKind::Or,
            values: parts,
        }) as ExprRef;
        Some((merged, body_start, exit))
    }

    /// Evaluate a straight-line value-expression instruction region on a
    /// scratch stack (py2 boolop condition merging). Returns None when any
    /// instruction is not pure value computation.
    fn sim_value_region(&self, from_idx: usize, to_idx: usize) -> Option<ExprRef> {
        let mut st: Vec<ExprRef> = Vec::new();
        let pop1 = |st: &mut Vec<ExprRef>| st.pop().unwrap_or_else(|| self.name_expr("???"));
        for k in from_idx..to_idx {
            let ins = &self.instrs[k];
            let arg = ins.arg as usize;
            match ins.op {
                Op::LOAD_FAST | Op::LOAD_FAST_CHECK | Op::LOAD_FAST_BORROW => {
                    st.push(self.name_expr(self.local_name(arg)));
                }
                Op::LOAD_NAME | Op::LOAD_GLOBAL | Op::STORE_FAST => {
                    if ins.op == Op::STORE_FAST {
                        return None;
                    }
                    let n = if ins.op == Op::LOAD_GLOBAL && self.version.at_least(3, 11) {
                        self.const_name(arg >> 1)
                    } else {
                        self.const_name(arg)
                    };
                    st.push(self.name_expr(n));
                }
                Op::LOAD_DEREF => {
                    let n = self
                        .code
                        .deref_name(arg)
                        .unwrap_or("???")
                        .to_string();
                    st.push(self.name_expr(n));
                }
                Op::LOAD_SMALL_INT => {
                    st.push(Rc::new(Expr::Const(Rc::new(PyObject::Int(
                        ins.arg as i32,
                    )))));
                }
                Op::LOAD_CONST => {
                    st.push(Rc::new(Expr::Const(
                        self.code.consts.get(arg).cloned().unwrap_or_else(|| {
                            Rc::new(PyObject::None)
                        }),
                    )));
                }
                Op::LOAD_ATTR | Op::LOAD_METHOD => {
                    let v = pop1(&mut st);
                    let idx = if ins.op == Op::LOAD_ATTR && self.version.at_least(3, 12) {
                        arg >> 1
                    } else {
                        arg
                    };
                    let a = self.const_name(idx);
                    st.push(Rc::new(Expr::Attribute { value: v, attr: a }));
                }
                Op::COMPARE_OP => {
                    let r = pop1(&mut st);
                    let l = pop1(&mut st);
                    let op = cmp_from_index(compare_op_index(arg as u32, self.version));
                    st.push(Rc::new(Expr::Compare {
                        operands: vec![l, r],
                        ops: vec![op],
                    }));
                }
                Op::IS_OP => {
                    let r = pop1(&mut st);
                    let l = pop1(&mut st);
                    let op = if arg == 1 { CmpOp::IsNot } else { CmpOp::Is };
                    st.push(Rc::new(Expr::Compare {
                        operands: vec![l, r],
                        ops: vec![op],
                    }));
                }
                Op::CONTAINS_OP => {
                    let r = pop1(&mut st);
                    let l = pop1(&mut st);
                    let op = if arg == 1 { CmpOp::NotIn } else { CmpOp::In };
                    st.push(Rc::new(Expr::Compare {
                        operands: vec![l, r],
                        ops: vec![op],
                    }));
                }
                Op::UNARY_NOT => {
                    let v = pop1(&mut st);
                    st.push(Rc::new(Expr::Unary { op: UnaryOp::Not, operand: v }));
                }
                Op::UNARY_NEGATIVE => {
                    let v = pop1(&mut st);
                    st.push(Rc::new(Expr::Unary { op: UnaryOp::Neg, operand: v }));
                }
                Op::UNARY_INVERT => {
                    let v = pop1(&mut st);
                    st.push(Rc::new(Expr::Unary { op: UnaryOp::Invert, operand: v }));
                }
                Op::BINARY_SUBSCR => {
                    let i = pop1(&mut st);
                    let v = pop1(&mut st);
                    st.push(Rc::new(Expr::Subscript { value: v, index: i }));
                }
                Op::BINARY_OP => {
                    let r = pop1(&mut st);
                    let l = pop1(&mut st);
                    let name = binary_op_name(arg as u32, self.version)?;
                    if name.ends_with('=') {
                        return None;
                    }
                    let op = binop_from_text(name);
                    st.push(Rc::new(Expr::Binary { op, left: l, right: r }));
                }
                Op::BINARY_ADD | Op::BINARY_SUBTRACT | Op::BINARY_MULTIPLY
                | Op::BINARY_DIVIDE | Op::BINARY_TRUE_DIVIDE | Op::BINARY_FLOOR_DIVIDE
                | Op::BINARY_MODULO | Op::BINARY_POWER | Op::BINARY_LSHIFT
                | Op::BINARY_RSHIFT | Op::BINARY_OR | Op::BINARY_XOR | Op::BINARY_AND
                | Op::BINARY_MATRIX_MULTIPLY => {
                    let r = pop1(&mut st);
                    let l = pop1(&mut st);
                    let op = match ins.op {
                        Op::BINARY_ADD => BinaryOp::Add,
                        Op::BINARY_SUBTRACT => BinaryOp::Sub,
                        Op::BINARY_MULTIPLY => BinaryOp::Mult,
                        Op::BINARY_DIVIDE | Op::BINARY_TRUE_DIVIDE => BinaryOp::Div,
                        Op::BINARY_FLOOR_DIVIDE => BinaryOp::FloorDiv,
                        Op::BINARY_MODULO => BinaryOp::Mod,
                        Op::BINARY_POWER => BinaryOp::Pow,
                        Op::BINARY_LSHIFT => BinaryOp::LShift,
                        Op::BINARY_RSHIFT => BinaryOp::RShift,
                        Op::BINARY_OR => BinaryOp::BitOr,
                        Op::BINARY_XOR => BinaryOp::BitXor,
                        Op::BINARY_AND => BinaryOp::BitAnd,
                        _ => BinaryOp::MatMult,
                    };
                    st.push(Rc::new(Expr::Binary { op, left: l, right: r }));
                }
                Op::BUILD_TUPLE | Op::BUILD_LIST | Op::BUILD_SET => {
                    let n = arg.min(st.len());
                    let items: Vec<ExprRef> = st.split_off(st.len() - n);
                    let e = match ins.op {
                        Op::BUILD_TUPLE => Expr::Tuple(items),
                        Op::BUILD_LIST => Expr::List(items),
                        _ => Expr::Set(items),
                    };
                    st.push(Rc::new(e));
                }
                Op::CALL_FUNCTION | Op::CALL | Op::CALL_METHOD => {
                    let n = if ins.op == Op::CALL_FUNCTION && !self.version.at_least(3, 6) {
                        arg & 0xFF
                    } else {
                        arg
                    };
                    let n = n.min(st.len());
                    let args: Vec<ExprRef> = st.split_off(st.len() - n);
                    let func = pop1(&mut st);
                    st.push(Rc::new(Expr::Call {
                        func,
                        args,
                        keywords: Vec::new(),
                        star_args: None,
                        star_kwargs: None,
                    }));
                }
                Op::TO_BOOL
                | Op::NOP
                | Op::NOT_TAKEN
                | Op::COPY
                | Op::PUSH_NULL
                | Op::PRECALL
                | Op::RESUME => {}
                _ => return None,
            }
        }
        if st.len() == 1 {
            st.pop()
        } else {
            None
        }
    }

    /// 3.14+ continue-guard chain inside a loop: each test jumps FORWARD
    /// to the next test (or the body) when it passes, and falls through
    /// to `NOT_TAKEN; JUMP_BACKWARD loop_top` (an inline continue) when
    /// it fails. Merge the guards into one And condition over the body.
    fn try_guard_chain(&self, cond: &ExprRef, jump_if_true: bool, target: usize)
        -> Option<(ExprRef, usize, usize)>
    {
        let is_cond_jump = |o: Op| {
            matches!(
                o,
                Op::POP_JUMP_IF_FALSE
                    | Op::POP_JUMP_IF_TRUE
                    | Op::POP_JUMP_FORWARD_IF_FALSE
                    | Op::POP_JUMP_FORWARD_IF_TRUE
            )
        };
        // the enclosing loop top: the trampoline's back-jump target
        let ci = *self.idx_of.get(&self.cur_offset)?;
        if !matches!(self.instrs.get(ci + 1).map(|x| x.op), Some(Op::NOT_TAKEN)) {
            return None;
        }
        let mut t = ci + 1;
        while matches!(self.instrs.get(t).map(|x| x.op), Some(Op::NOT_TAKEN) | Some(Op::NOP)) {
            t += 1;
        }
        let tramp = self.instrs.get(t)?;
        if !tramp.is_backward
            || !matches!(
                tramp.op,
                Op::JUMP_BACKWARD | Op::JUMP_ABSOLUTE | Op::JUMP_BACKWARD_NO_INTERRUPT
            )
        {
            return None;
        }
        let loop_top = tramp.target?;
        if !self.blocks.iter().any(|b| {
            matches!(b.kind, BlockType::While | BlockType::For)
                && (b.start == loop_top
                    || (b.cond_end != usize::MAX && b.cond_end == loop_top))
        }) {
            return None;
        }
        // walk the guard chain
        let mut values: Vec<ExprRef> = Vec::new();
        let first = if jump_if_true {
            cond.clone()
        } else {
            Rc::new(Expr::Unary { op: UnaryOp::Not, operand: cond.clone() })
        };
        flatten_boolop(first, BoolOpKind::And, &mut values);
        let mut next = target;
        let mut body_start;
        loop {
            let Some(&ni) = self.idx_of.get(&next) else {
                return None;
            };
            // scan the operand region up to its cond jump
            let region_start = ni;
            let mut jk = ni;
            while jk < self.instrs.len() {
                let ins = &self.instrs[jk];
                if is_cond_jump(ins.op) {
                    break;
                }
                if !is_pure_value_op(ins.op) {
                    // not another guard: `next` is the body start
                    break;
                }
                jk += 1;
            }
            if jk >= self.instrs.len() || !is_cond_jump(self.instrs[jk].op) {
                body_start = next;
                break;
            }
            // the guard's fall-through must be the continue trampoline
            // (NOT_TAKEN padding then the back jump)
            if !matches!(self.instrs.get(jk + 1).map(|x| x.op), Some(Op::NOT_TAKEN)) {
                return None;
            }
            let mut ft = jk + 1;
            while matches!(self.instrs.get(ft).map(|x| x.op), Some(Op::NOT_TAKEN) | Some(Op::NOP)) {
                ft += 1;
            }
            let ftramp = self.instrs.get(ft)?;
            if !ftramp.is_backward
                || ftramp.target != Some(loop_top)
                || !matches!(
                    ftramp.op,
                    Op::JUMP_BACKWARD | Op::JUMP_ABSOLUTE | Op::JUMP_BACKWARD_NO_INTERRUPT
                )
            {
                // no trampoline: this jump heads to the body
                body_start = self.instrs[jk].target?;
                // the operand region belongs to the body, not a guard —
                // only accept when nothing was consumed as an operand
                if jk != region_start {
                    return None;
                }
                break;
            }
            let operand = match self.sim_value_region(region_start, jk) {
                            Some(o) => o,
                            None => {
                                return None;
                            }
                        };
            let jins = &self.instrs[jk];
            let jt = matches!(
                jins.op,
                Op::POP_JUMP_IF_TRUE | Op::POP_JUMP_FORWARD_IF_TRUE
            );
            values.push(if jt {
                operand
            } else {
                Rc::new(Expr::Unary { op: UnaryOp::Not, operand })
            });
            next = jins.target?;
        }
        if values.is_empty() {
            return None;
        }
        // the body ends at its back edge to the loop top (or a break)
        let Some(&bi) = self.idx_of.get(&body_start) else {
            return None;
        };
        let mut body_end = None;
        for ins in self.instrs[bi..].iter() {
            if ins.offset >= body_start {
                if let Some(t) = ins.target {
                    if ins.is_backward
                        && t == loop_top
                        && matches!(
                            ins.op,
                            Op::JUMP_BACKWARD
                                | Op::JUMP_ABSOLUTE
                                | Op::JUMP_BACKWARD_NO_INTERRUPT
                        )
                    {
                        body_end = Some(ins.offset);
                        break;
                    }
                    // a break jump out of the loop lives inside the body;
                    // the body ends at the following back edge
                    let leaves = self
                        .blocks
                        .iter()
                        .rev()
                        .find(|b| {
                            matches!(b.kind, BlockType::While | BlockType::For)
                                && (b.start == loop_top
                                    || (b.cond_end != usize::MAX && b.cond_end == loop_top))
                        })
                        .map_or(false, |b| {
                            !ins.is_backward
                                && self
                                    .loop_exit_offset(b)
                                    .map_or(false, |le| {
                                        self.effective_offset(t) == self.effective_offset(le)
                                    })
                        });
                    if leaves {
                        continue;
                    }
                    // any other jump target inside the body is fine, but a
                    // forward jump past the loop means a break to a merged
                    // exit we cannot bound — bail
                    if !ins.is_backward {
                        let inside = self
                            .blocks
                            .iter()
                            .rev()
                            .find(|b| {
                                matches!(b.kind, BlockType::While | BlockType::For)
                                    && (b.start == loop_top
                                        || (b.cond_end != usize::MAX
                                            && b.cond_end == loop_top))
                            })
                            .map_or(false, |b| t < b.end);
                        if !inside {
                            return None;
                        }
                    }
                }
            }
        }
        let body_end = match body_end {
            Some(b) => b,
            None => {
                return None;
            }
        };
        if body_end <= body_start {
            return None;
        }
        let merged = Rc::new(Expr::BoolOp {
            op: BoolOpKind::And,
            values,
        });
        Some((merged as ExprRef, body_start, body_end))
    }

    fn handle_cond_jump(&mut self, cond: ExprRef, jump_if_true: bool, target: usize) {
        // 3.14+ continue-guard chain: pass-jumps forward, fail falls into
        // a NOT_TAKEN; JUMP_BACKWARD loop-top trampoline. The NOT_TAKEN
        // padding is mandatory: pre-3.14 `if c: continue` shapes have a
        // bare back jump after the operand jump and belong to the
        // historical machinery.
        if self.version.at_least(3, 12) {
            if let Some((merged, body_start, body_end)) =
                self.try_guard_chain(&cond, jump_if_true, target)
            {
                let mut blk = Block::new(BlockType::If, body_start, body_end);
                blk.cond = Some(merged);
                blk.cond_set = true;
                blk.jump_if_true = false;
                blk.stack_depth = self.stack.len();
                self.blocks.push(blk);
                self.skip_until = Some(body_start);
                return;
            }
        }
        // py2-style boolop if-conditions: `(a or b) and c` merges into one
        // BoolOp cond + a single If block. Skipped when this jump is an
        // uninitialized loop's condition (SETUP_LOOP era) or a rotated-while
        // back-edge candidate.
        let while_top = self.blocks.last().map_or(false, |b| {
            matches!(b.kind, BlockType::While)
                && (!b.cond_set || b.cond_end != usize::MAX)
        });
        if !while_top {
            // `if a or b:` (and mixed-polarity and-chains): this cond jump
            // targets the BODY start; the region up to it is the second
            // operand ending in an opposite-polarity cond jump to the if's
            // exit. Merge into one BoolOp cond over [target, exit).
            if let Some((merged_cond, body_start, exit)) =
                self.try_merge_or_cond(&cond, jump_if_true, target)
            {
                let mut blk = Block::new(BlockType::If, body_start, exit);
                blk.cond = Some(merged_cond);
                blk.cond_set = true;
                blk.jump_if_true = false;
                blk.stack_depth = self.stack.len();
                self.blocks.push(blk);
                self.skip_until = Some(body_start);
                return;
            }
            if let Some((merged, then_start, e)) =
                self.try_merge_py2_boolop(&cond, jump_if_true, target)
            {
                let mut blk = Block::new(BlockType::If, then_start, e);
                blk.cond = Some(merged);
                blk.cond_set = true;
                blk.jump_if_true = false;
                blk.stack_depth = self.stack.len();
                self.blocks.push(blk);
                // the operand regions were consumed by the scratch sim
                self.skip_until = Some(then_start);
                return;
            }
        }
        // inline comprehension filter: `... if cond`
        if let Some(comp) = &mut self.inline_comp {
            if self.cur_offset < comp.end {
                let c = if jump_if_true {
                    Rc::new(Expr::Unary {
                        op: UnaryOp::Not,
                        operand: cond,
                    })
                } else {
                    cond
                };
                if let Some(cur) = &mut comp.cur {
                    cur.ifs.push(simplify_not(c));
                }
                return;
            }
        }
        // 0) a cond jump whose target is the end of an open Else block and
        // which is NOT an elif condition closes the else body first. The
        // elif test would create a nested If at the same target, so keep
        // the Else open in that case.
        if let Some(top) = self.blocks.last() {
            if matches!(top.kind, BlockType::Else | BlockType::TryElse)
                && top.end == target
                && !top.is_elif
                && self.cur_offset != top.start
            {
                self.close_blocks_at(target);
            }
        }

        // 1) short-circuit merge: a JUMP_IF_*_OR_POP block ending here
        if let Some(top) = self.blocks.last() {
            if matches!(top.kind, BlockType::If) && top.short_circuit.is_some() && top.end == target
            {
                let or_form = top.short_circuit.unwrap();
                let left = top.cond.clone().unwrap();
                let mut b = self.blocks.pop().unwrap();
                let _ = &mut b;
                let right = self.pop_expr();
                let kind = if or_form {
                    BoolOpKind::Or
                } else {
                    BoolOpKind::And
                };
                let merged = Rc::new(Expr::BoolOp {
                    op: kind,
                    values: vec![left, right],
                });
                self.push(merged);
                return;
            }
        }

        // 2) rotated while: duplicated cond jump to the same exit — ignore.
        // Only matches the loop cond's own polarity; an opposite-polarity
        // jump to the loop exit is an `if c: break`.
        if let Some(top) = self.blocks.last() {
            if matches!(top.kind, BlockType::While)
                && top.cond_set
                && top.jump_if_true == jump_if_true
                && top.end == target
                && top.cond_end != usize::MAX
                && top.cond_end < self.cur_offset
            {
                return;
            }
        }

        // 3) BoolOp merge inside an open If whose end == target — only for
        // split conditions (`if a and b:` = two cond jumps over a pure
        // value region); a second independent if inside the body whose
        // exit happens to coincide must stay nested
        let split_cond = self.blocks.last().map_or(false, |top| {
            matches!(top.kind, BlockType::If)
                && top.end == target
                && top.cond_set
                && top.short_circuit.is_none()
                && top.jump_if_true == jump_if_true
                && top.stmts.is_empty()
                && self.is_pure_value_region(top.start, self.cur_offset)
        });
        if split_cond {
            if let Some(top) = self.blocks.last_mut() {
                let prev = top.cond.take().unwrap();
                // two same-target cond jumps always AND: the body runs only
                // when NEITHER jump is taken (`if a and b` = two PJIFs,
                // `if not a and not b` = two PJITs)
                let kind = BoolOpKind::And;
                // `top.cond` stores the branch-taken polarity; the second
                // jump's operand must be normalized the same way (`if not a
                // and not b` compiles to two PJITs and must merge to
                // And(Not a, Not b))
                let c2 = if jump_if_true {
                    // branch-taken polarity: negate, cancelling a double
                    // negation when the operand is itself `not x`
                    match &*cond {
                        Expr::Unary { op: UnaryOp::Not, operand } => {
                            operand.clone()
                        }
                        _ => Rc::new(Expr::Unary {
                            op: UnaryOp::Not,
                            operand: cond,
                        }),
                    }
                } else {
                    cond
                };
                let mut values = Vec::new();
                flatten_boolop(prev, kind, &mut values);
                flatten_boolop(c2, kind, &mut values);
                top.cond = Some(Rc::new(Expr::BoolOp { op: kind, values }));
                return;
            }
        }

        // 3) uninitialized While block (SETUP_LOOP era): the first cond
        // jump is the loop condition only when its target region contains
        // the body back edge (`while True:` has no cond jump at all, and a
        // backward cond jump is handled below as the `if c: break` shape)
        let while_end = self
            .blocks
            .last()
            .filter(|b| matches!(b.kind, BlockType::While) && !b.cond_set)
            .map(|b| b.end);
        let cond_like = match (
            self.idx_of.get(&self.cur_offset),
            self.idx_of.get(&target),
            while_end.and_then(|e| self.idx_of.get(&e).copied()),
        ) {
            (Some(&ci), Some(&ti), Some(wei)) if ci < ti => {
                // the body must loop back to the top
                let region = &self.instrs[ci..ti];
                let back = region.iter().any(|i| i.is_backward);
                if !back {
                    false
                } else if Some(target) == while_end
                    || while_end.map_or(false, |we| self.is_pop_block_before(target, we))
                {
                    // PJIF straight to the loop exit (or its POP_BLOCK, the
                    // SETUP_LOOP-era exit shape): canonical `while c:`
                    true
                } else if wei > ti {
                    // while/else candidate: the else region [target, loop
                    // end) must contain no back edge, break, or return
                    let else_region = &self.instrs[ti..wei];
                    !else_region.iter().any(|i| {
                        i.is_backward
                            || i.op == Op::BREAK_LOOP
                            || matches!(i.op, Op::RETURN_VALUE | Op::RETURN_CONST)
                    }) && !region.iter().any(|i| i.op == Op::BREAK_LOOP)
                } else {
                    false
                }
            }
            _ => false,
        };
        let pop_block_equiv = self
            .blocks
            .last()
            .map_or(false, |b| self.is_pop_block_before(target, b.end));
        if let Some(top) = self.blocks.last_mut() {
            if matches!(top.kind, BlockType::While) && !top.cond_set && cond_like {
                let c = if jump_if_true {
                    Rc::new(Expr::Unary {
                        op: UnaryOp::Not,
                        operand: cond,
                    })
                } else {
                    cond
                };
                top.cond = Some(c);
                top.cond_set = true;
                top.jump_if_true = jump_if_true;
                if target != top.end && !pop_block_equiv {
                    // exit target differs from SETUP_LOOP end -> while/else
                    top.loop_else_end = Some(target);
                } else if pop_block_equiv && target < top.end {
                    // py2.6/2.7 while-else: the exit target IS the
                    // POP_BLOCK; code between it and the SETUP_LOOP target
                    // is the else body. End the loop at the POP_BLOCK so
                    // its close separates the else region.
                    if let Some(&pi) = self.idx_of.get(&target) {
                        let pb_end = self.instrs[pi].end();
                        top.loop_else_end = Some(top.end);
                        top.end = pb_end;
                    }
                }
                return;
            }
        }

        // 4) except-block matching (3.10+ CHECK_EXC_MATCH style)
        if let Expr::Compare { operands, ops } = &*cond {
            if ops.len() == 1 && matches!(ops[0], CmpOp::ExceptionMatch) {
                let pattern = operands[1].clone();
                self.open_except_block(target, Some(pattern));
                return;
            }
        }

        // 5) assert detection. Canonical shape (all versions):
        //   <cond>; PJIT L; LOAD AssertionError; [<msg>; CALL 1]; RAISE 1; L:
        // i.e. the raise block is the jump's fall-through and the target
        // lands right after it.
        if jump_if_true {
            if let Some(msg) = self.is_assert_fallthrough(target) {
                self.push_stmt(Stmt::Assert { test: cond, msg });
                self.skip_until = Some(target);
                return;
            }
        }
        // `if not cond: raise AssertionError` written as a statement: the
        // raise block is the jump target
        if !jump_if_true && self.is_assert_target(target) {
            let msg = self.try_extract_assert_msg(target);
            self.push_stmt(Stmt::Assert {
                test: cond,
                msg,
            });
            self.skip_until = Some(target);
            return;
        }

        // 5.5) backward conditional jumps inside loops
        if target < self.cur_offset {
            let n = self.blocks.len();
            for i in (0..n).rev() {
                if matches!(self.blocks[i].kind, BlockType::While | BlockType::For) {
                    let b = &self.blocks[i];
                    let matches_loop = b.start == target
                        || b.cond_end == target
                        || (b.start <= target && target < b.cond_end);
                    if !matches_loop {
                        continue;
                    }
                    // fused `if a or b: continue` chain: this jump carries
                    // the first operand straight to the loop top; the
                    // remaining operands and the continue body follow
                    if let Some((merged, body_start, body_end)) =
                        self.try_or_continue_chain(target, &cond)
                    {
                        let mut blk = Block::new(BlockType::If, body_start, body_end);
                        blk.cond = Some(merged);
                        blk.cond_set = true;
                        blk.stack_depth = self.stack.len();
                        self.blocks.push(blk);
                        self.skip_until = Some(body_start);
                        return;
                    }
                    if jump_if_true && self.blocks[i].cond_set {
                        // 3.10+ rotated while back edge: closes the loop
                        while self.blocks.len() > i {
                            self.force_close_top(target);
                        }
                        return;
                    }
                    // backward cond jump to the loop top (`if c: break` /
                    // `if not c: break` shape): the then-body runs until
                    // THIS loop's unconditional back edge (not a nested
                    // loop's)
                    let loop_start = self.blocks[i].start;
                    if let Some(&ci) = self.idx_of.get(&self.cur_offset) {
                        for inst in self.instrs.iter().skip(ci + 1) {
                            if inst.is_backward
                                && inst.target == Some(loop_start)
                                && matches!(
                                    inst.op,
                                    Op::JUMP_ABSOLUTE
                                        | Op::JUMP_BACKWARD
                                        | Op::JUMP_BACKWARD_NO_INTERRUPT
                                )
                            {
                                let mut blk =
                                    Block::new(BlockType::If, self.cur_next, inst.start);
                                let c = if jump_if_true {
                                    Rc::new(Expr::Unary {
                                        op: UnaryOp::Not,
                                        operand: cond.clone(),
                                    })
                                } else {
                                    cond.clone()
                                };
                                blk.cond = Some(c);
                                blk.cond_set = true;
                                self.blocks.push(blk);
                                return;
                            }
                            // a RETURN may sit inside the then region —
                            // 3.8/3.9 jump-threading leaves the loop's
                            // (dead) back edge AFTER it; only stop at a
                            // forward escape out of the loop
                            if inst.target.map_or(false, |t| {
                                t > inst.offset && self.find_loop_exit(t).is_some()
                            }) {
                                break;
                            }
                        }
                    }
                    return;
                }
            }
        }

        // 6) while loop (3.8+): a backward jump inside the jump-target
        // region that lands at the current instruction offset marks a loop.
        let cur = self.cur_offset;
        if let (Some(&ci), Some(&ti)) = (self.idx_of.get(&cur), self.idx_of.get(&target)) {
            if ti > ci {
                for inst in &self.instrs[ci..ti] {
                    if let Some(t) = inst.target {
                        // back edge to the cond jump itself or to the start
                        // of the condition expression (rotated while loops:
                        // the back edge skips the duplicated initial cond)
                        if inst.is_backward
                            && t < target
                            && (t == cur
                                || t == self.cur_next
                                || (t < cur && self.is_cond_expr_top(t, cur)))
                        {
                            let cond_end = self.instrs[ci].end();
                            let mut blk = Block::new(BlockType::While, t, target);
                            blk.cond = Some(if jump_if_true {
                                Rc::new(Expr::Unary {
                                    op: UnaryOp::Not,
                                    operand: cond,
                                })
                            } else {
                                cond
                            });
                            blk.cond_set = true;
                            blk.cond_end = cond_end;
                            blk.jump_if_true = jump_if_true;
                            self.blocks.push(blk);
                            return;
                        }
                    }
                }
            }
        }

        // 3.14+: `if c: break` compiles to a conditional jump straight to
        // the loop exit with the back edge as fall-through
        if self.find_loop_exit(target).is_some() {
            let c = if jump_if_true {
                cond
            } else {
                Rc::new(Expr::Unary {
                    op: UnaryOp::Not,
                    operand: cond,
                })
            };
            self.push_stmt(Stmt::If {
                cond: c,
                body: vec![Stmt::Break],
                orelse: Vec::new(),
            });
            return;
        }

        // py2/<=3.7: `if cond: stmt` at the END of a loop body compiles the
        // false-jump straight to the loop top (fusing skip and continue):
        // [PJIF loop_top; stmts; JUMP_ABS loop_top; JUMP_ABS loop_top]. The
        // then-body ends at the first backward jump to the loop top.
        if !jump_if_true {
            let loop_top = self
                .blocks
                .iter()
                .rev()
                .find(|b| matches!(b.kind, BlockType::While | BlockType::For))
                .map(|b| b.start);
            if let Some(lt) = loop_top {
                if target == lt {
                    let mut then_end = None;
                    if let Some(&ci) = self.idx_of.get(&self.cur_offset) {
                        for ins in self.instrs.iter().skip(ci + 1) {
                            if ins.is_backward && ins.target == Some(lt) {
                                then_end = Some(ins.offset);
                                break;
                            }
                            if matches!(ins.op, Op::RETURN_VALUE | Op::RETURN_CONST) {
                                break;
                            }
                            if ins.offset >= lt && lt > self.cur_offset {
                                break;
                            }
                        }
                    }
                    if let Some(te) = then_end {
                        let mut blk = Block::new(BlockType::If, self.cur_next, te);
                        blk.cond = Some(cond);
                        blk.cond_set = true;
                        blk.jump_if_true = false;
                        blk.stack_depth = self.stack.len();
                        self.blocks.push(blk);
                        return;
                    }
                }
            }
        }

        // close inner blocks that end at the current instruction before
        // opening the new one
        self.close_blocks_at(self.cur_offset);

        // 7) regular if statement: the fall-through region [next, target)
        // is the then-body. With POP_JUMP_IF_TRUE the fall-through runs when
        // the condition is false, so negate.
        let c = if jump_if_true {
            Rc::new(Expr::Unary {
                op: UnaryOp::Not,
                operand: cond,
            })
        } else {
            cond
        };
        // COPY/TO_BOOL + cond jump = value-preserving branch (3.12+ and/or
        // chains, chained comparisons); plain statements are guarded at
        // close time by requiring an empty body and a live stack value
        // TO_BOOL only marks a value-preserving branch when the jump
        // target holds the chain else-arm (SWAP 2; POP_TOP) — a plain
        // `if x:` in 3.13+ also carries TO_BOOL and must stay a statement
        // 3.13 value-form boolops interpose TO_BOOL between the COPY and
        // the cond jump — look through it via the instruction index
        let copy_to_bool_before = self
            .idx_of
            .get(&self.cur_offset)
            .map_or(false, |&bi| {
                bi >= 2
                    && self.instrs[bi - 1].op == Op::TO_BOOL
                    && self.instrs[bi - 2].op == Op::COPY
            });
        let value_merge = (matches!(self.prev_op_at_exec, Some(Op::COPY))
            || (matches!(self.prev_op_at_exec, Some(Op::TO_BOOL))
                && (copy_to_bool_before
                    || self.is_chain_else_arm(target)
                    || self.is_chain_else_arm_rot(target))))
        .then(|| {
                if jump_if_true {
                    BoolOpKind::Or
                } else {
                    BoolOpKind::And
                }
            });
        // 3.12+ chained comparison: the then arm recomputes the next link
        // and merges at its own end (a consuming instruction or a forward
        // jump), NOT at the else arm (`SWAP 2; POP_TOP`) — closing there
        // would let the consumer eat the un-merged link value. A nested
        // link's arm holds another cond jump: keep the else-arm end so the
        // inner block closes first and the outer merges with its result.
        let chain_merge = match &value_merge {
            Some(BoolOpKind::And) if self.is_chain_else_arm(target) => {
                self.chain_then_merge(target)
            }
            _ => None,
        };
        let blk_end = chain_merge.unwrap_or(target);
        let mut blk = Block::new(BlockType::If, self.cur_next, blk_end);
        blk.value_merge = value_merge;
        blk.chain_link = matches!(&value_merge, Some(BoolOpKind::And))
            && self.is_chain_else_arm(target);
        blk.cond = Some(c);
        blk.cond_set = true;
        blk.jump_if_true = jump_if_true;
        blk.stack_depth = self.stack.len();
        self.blocks.push(blk);
    }


    /// Detect the canonical `assert` raise block as the fall-through of a
    /// cond jump: returns Some(msg_option) when [cur_next, target) is
    /// exactly `LOAD AssertionError; [<msg expr>; CALL 1]; RAISE_VARARGS 1`.
    fn is_assert_fallthrough(&self, target: usize) -> Option<Option<ExprRef>> {
        let &i0 = self.idx_of.get(&self.cur_offset)?;
        let mut k = i0 + 1;
        loop {
            let skip = matches!(
                self.instrs.get(k).map(|x| x.op),
                Some(Op::TO_BOOL) | Some(Op::COPY) | Some(Op::NOP)
            ) || (!self.version.at_least(3, 0)
                && matches!(self.instrs.get(k).map(|x| x.op), Some(Op::POP_TOP)));
            if !skip {
                break;
            }
            k += 1;
        }
        let err_load = match self.instrs.get(k) {
            Some(ins) if ins.op == Op::LOAD_ASSERTION_ERROR => true,
            Some(ins) if matches!(ins.op, Op::LOAD_GLOBAL | Op::LOAD_NAME) => {
                let idx = if ins.op == Op::LOAD_GLOBAL && self.version.at_least(3, 10) {
                    (ins.arg as usize) >> 1
                } else {
                    ins.arg as usize
                };
                self.const_name(idx) == "AssertionError"
            }
            _ => false,
        };
        if !err_load {
            return None;
        }
        let msg_start = k + 1;
        // find the terminating RAISE_VARARGS 1; jumps (other than in msg
        // expressions we don't expect) invalidate the shape
        let mut raise_idx = None;
        let mut call_idx = None;
        let mut j = msg_start;
        while j < self.instrs.len() && j <= i0 + 60 {
            let ins = &self.instrs[j];
            if ins.op == Op::RAISE_VARARGS && ins.arg == 1 {
                raise_idx = Some(j);
                break;
            }
            if matches!(ins.op, Op::CALL | Op::CALL_FUNCTION) && ins.arg <= 1 {
                call_idx = Some(j);
            }
            if ins.target.is_some()
                && !matches!(ins.op, Op::CALL | Op::CALL_FUNCTION | Op::FOR_ITER)
            {
                return None;
            }
            if matches!(ins.op, Op::RETURN_VALUE | Op::RETURN_CONST) {
                return None;
            }
            j += 1;
        }
        let ri = raise_idx?;
        // the raise must land on `target`, possibly through dead padding
        // jumps (py2 emits JUMP_FORWARD 0 after the raise)
        let mut off = self.instrs[ri].end();
        loop {
            if self.effective_offset(off) == self.effective_offset(target) {
                break;
            }
            let advanced = match self.idx_of.get(&off) {
                Some(&pi) => {
                    let p = &self.instrs[pi];
                    if matches!(p.op, Op::JUMP_FORWARD | Op::JUMP | Op::JUMP_ABSOLUTE)
                        && p.target == Some(target)
                    {
                        let nxt = p.end();
                        off = nxt;
                        true
                    } else {
                        false
                    }
                }
                None => false,
            };
            if !advanced {
                return None;
            }
        }
        let msg = match call_idx {
            Some(ci2) if ci2 > msg_start && ci2 < ri => {
                self.sim_value_region(msg_start, ci2)
            }
            _ => None,
        };
        Some(msg)
    }

    /// True when every instruction in [from, to) is pure value computation.
    fn is_pure_value_region(&self, from: usize, to: usize) -> bool {
        let Some(&fi) = self.idx_of.get(&from) else {
            return false;
        };
        for ins in self.instrs.iter().skip(fi) {
            if ins.offset >= to {
                return true;
            }
            if !is_pure_value_op(ins.op) {
                return false;
            }
        }
        true
    }

    /// 3.12+ chained-comparison else arm: `SWAP 2; POP_TOP` at the jump
    /// target (keeps the comparison result, drops the shared operand).
    fn is_chain_else_arm(&self, target: usize) -> bool {
        let Some(&i) = self.idx_of.get(&target) else {
            return false;
        };
        matches!(self.instrs.get(i).map(|x| x.op), Some(Op::SWAP))
            && matches!(self.instrs.get(i + 1).map(|x| x.op), Some(Op::POP_TOP))
    }

    /// <=3.11 chained-comparison else arm: `ROT_TWO; POP_TOP` at the
    /// JUMP_IF_FALSE_OR_POP target.
    fn is_chain_else_arm_rot(&self, target: usize) -> bool {
        let Some(&i) = self.idx_of.get(&target) else {
            return false;
        };
        matches!(self.instrs.get(i).map(|x| x.op), Some(Op::ROT_TWO))
            && matches!(self.instrs.get(i + 1).map(|x| x.op), Some(Op::POP_TOP))
    }

    /// True when every instruction in [from, to) is compiler padding
    /// (NOT_TAKEN/NOP/CACHE) — 3.14 pads `if c: break` trampolines with
    /// NOT_TAKEN between the block start and its back edge.
    fn padding_only_between(&self, from: usize, to: usize) -> bool {
        if from >= to {
            return false;
        }
        let (Some(&a), Some(&b)) = (self.idx_of.get(&from), self.idx_of.get(&to)) else {
            return false;
        };
        (a..b).all(|k| {
            matches!(
                self.instrs[k].op,
                Op::NOT_TAKEN | Op::NOP | Op::CACHE
            )
        })
    }

    /// Arm a skip for a value-merge block's false-path region. py2.6
    /// chained comparisons close at (or after) the else arm's own offset,
    /// leaving `skip_until = else_end` stale — the `ROT_TWO; POP_TOP`
    /// cleanup would still run and eat the merged chain value. When the
    /// arm starts at or behind the current position, skip past it.
    fn skip_chain_else_arm(&mut self, else_end: usize) {
        let mut skip = else_end;
        if else_end <= self.cur_offset
            && (self.is_chain_else_arm_rot(else_end) || self.is_chain_else_arm(else_end))
        {
            if let Some(&i) = self.idx_of.get(&else_end) {
                if let Some(pop) = self.instrs.get(i + 1) {
                    skip = pop.end();
                }
            }
        }
        self.skip_until = Some(skip);
    }

    /// Merge offset of a chained-comparison then arm: scan pure value ops
    /// from `from` — a closing jump gives its target, any consuming op is
    /// the merge itself. `None` when the arm holds a nested link (a
    /// conditional jump): the nested block closes first and the outer
    /// link falls back to the shared else-arm offset.
    fn chain_then_merge_from(&self, from: usize, target: usize) -> Option<usize> {
        let ci = self.idx_of.get(&from).copied()?;
        for ins in self.instrs.iter().skip(ci) {
            if ins.offset >= target {
                return None;
            }
            if matches!(ins.op, Op::NOT_TAKEN | Op::NOP | Op::CACHE) {
                continue;
            }
            match ins.op {
                Op::JUMP_FORWARD | Op::JUMP => return ins.target,
                Op::POP_JUMP_IF_FALSE
                | Op::POP_JUMP_IF_TRUE
                | Op::POP_JUMP_FORWARD_IF_FALSE
                | Op::POP_JUMP_FORWARD_IF_TRUE
                | Op::POP_JUMP_BACKWARD_IF_FALSE
                | Op::POP_JUMP_BACKWARD_IF_TRUE
                | Op::JUMP_IF_FALSE_OR_POP
                | Op::JUMP_IF_TRUE_OR_POP
                | Op::JUMP_IF_FALSE
                | Op::JUMP_IF_TRUE => return None,
                // stack shuffles inside the arm (a nested link sets its
                // operands up with SWAP/COPY) are not consumers
                Op::SWAP
                | Op::ROT_TWO
                | Op::ROT_THREE
                | Op::ROT_FOUR
                | Op::ROT_N
                | Op::DUP_TOP
                | Op::DUP_TOP_TWO => continue,
                // consumers of the link value end the arm right here —
                // CALL is value-pure in general but eats the chain result
                // as an argument, so it must not be scanned past
                Op::CALL
                | Op::CALL_FUNCTION
                | Op::CALL_METHOD
                | Op::CALL_FUNCTION_KW
                | Op::CALL_FUNCTION_EX
                | Op::POP_TOP
                | Op::RETURN_VALUE
                | Op::RETURN_CONST
                | Op::YIELD_VALUE
                | Op::STORE_NAME
                | Op::STORE_FAST
                | Op::STORE_DEREF
                | Op::STORE_ATTR
                | Op::STORE_SUBSCR
                | Op::STORE_GLOBAL => return Some(ins.offset),
                op if is_pure_value_op(op) => continue,
                _ => return Some(ins.offset),
            }
        }
        None
    }

    /// 3.12+ chain then-arm: starts with the POP_TOP that drops the
    /// retained link value, then the next link's computation. 3.14 pads
    /// the arm head with NOT_TAKEN.
    fn chain_then_merge(&self, target: usize) -> Option<usize> {
        let mut ci = self.idx_of.get(&self.cur_next).copied()?;
        while matches!(
            self.instrs.get(ci).map(|x| x.op),
            Some(Op::NOT_TAKEN) | Some(Op::NOP) | Some(Op::CACHE)
        ) {
            ci += 1;
        }
        if self.instrs.get(ci)?.op != Op::POP_TOP {
            return None;
        }
        self.chain_then_merge_from(self.instrs[ci].end(), target)
    }

    /// True when the code at `target` immediately raises AssertionError.
    fn is_assert_target(&self, target: usize) -> bool {
        let Some(&i) = self.idx_of.get(&target) else {
            return false;
        };
        // 3.10+: [TO_BOOL?] LOAD_ASSERTION_ERROR RAISE_VARARGS 1
        // <=3.9: LOAD_ASSERTION_ERROR RAISE_VARARGS 1
        let instrs = &self.instrs;
        let mut k = i;
        // skip harmless prologue ops
        while matches!(
            instrs.get(k).map(|x| x.op),
            Some(Op::TO_BOOL) | Some(Op::COPY) | Some(Op::POP_TOP)
        ) {
            k += 1;
        }
        if instrs.get(k).map(|x| x.op) != Some(Op::LOAD_ASSERTION_ERROR) {
            return false;
        }
        k += 1;
        // optional: message expression then RAISE_VARARGS 2
        matches!(instrs.get(k).map(|x| (x.op, x.arg)), Some((Op::RAISE_VARARGS, 1)))
            || self.scan_to_raise2(k)
    }

    fn scan_to_raise2(&self, from: usize) -> bool {
        let mut k = from;
        let mut steps = 0;
        while let Some(inst) = self.instrs.get(k) {
            match inst.op {
                Op::RAISE_VARARGS => return inst.arg == 2,
                Op::LOAD_ASSERTION_ERROR | Op::POP_JUMP_IF_FALSE | Op::POP_JUMP_IF_TRUE => {
                    return false
                }
                _ => {
                    k += 1;
                    steps += 1;
                    if steps > 16 {
                        return false;
                    }
                }
            }
        }
        false
    }

    /// Simulate the message expression between LOAD_ASSERTION_ERROR and
    /// RAISE_VARARGS 2 (constant messages only, which is the common case).
    fn try_extract_assert_msg(&self, target: usize) -> Option<ExprRef> {
        let &i = self.idx_of.get(&target)?;
        let instrs = &self.instrs;
        let mut k = i;
        while matches!(instrs.get(k).map(|x| x.op), Some(Op::TO_BOOL) | Some(Op::COPY)) {
            k += 1;
        }
        if instrs.get(k).map(|x| x.op) != Some(Op::LOAD_ASSERTION_ERROR) {
            return None;
        }
        k += 1;
        // expect: LOAD_CONST <msg>; RAISE_VARARGS 2
        if instrs.get(k).map(|x| x.op) == Some(Op::LOAD_CONST)
            && instrs.get(k + 1).map(|x| (x.op, x.arg)) == Some((Op::RAISE_VARARGS, 2))
        {
            let idx = instrs[k].arg as usize;
            return self.code.consts.get(idx).map(|o| Rc::new(Expr::Const(o.clone())));
        }
        None
    }

    fn open_except_block(&mut self, target: usize, pattern: Option<ExprRef>) {
        if self.legacy_try.is_some() {
            // handler body collects into the legacy handler, not a block
            self.legacy_handler = Some(LegacyHandler {
                type_: pattern,
                name: None,
                body: Vec::new(),
                block_depth: self.blocks.len(),
                pop_seen: false,
            });
            // a previous handler's unconfirmed cleanup marker must not
            // swallow this handler's `as` name store
            self.pending_as_cleanup = None;
            self.held_cleanup_store = None;
            self.legacy_handler_end = Some(target);
            self.in_handler_prelude = true;
            return;
        }
        // The Try block on the stack ends at the handler start (== where we
        // are now). Open an Except block ending at `target` (the jump out of
        // the handler).
        let start = self.blocks.last().map(|b| b.end).unwrap_or(0);
        let mut eb = Block::new(BlockType::Except, start, target);
        eb.handler_type = pattern;
        self.blocks.push(eb);
    }

    /// JUMP_IF_TRUE_OR_POP / JUMP_IF_FALSE_OR_POP: begin a short-circuit
    /// region. The value stays on the stack; at the target we merge.
    fn handle_short_circuit(&mut self, or_form: bool, target: usize) {
        // pycdc-style: mark a pending merge by pushing an If block whose
        // "cond" is the left operand; closing merges into BoolOp.
        let left = self.pop_expr();
        // <=3.11 chained comparison: the else arm at `target` is
        // ROT_TWO/POP_TOP (<=3.10) or SWAP 2/POP_TOP (3.11) and the then
        // arm's consumer (CALL/STORE/...) is the real merge — end the
        // block there so the value merges before the consumer runs.
        // Without this the else-arm SWAP executes against the live stack
        // (rotating the enclosing call's operands) before the close skips
        // its POP_TOP.
        let chain = !or_form
            && (self.is_chain_else_arm_rot(target) || self.is_chain_else_arm(target));
        let blk_end = if chain {
            self.chain_then_merge_from(self.cur_next, target)
                .unwrap_or(target)
        } else {
            target
        };
        let mut blk = Block::new(BlockType::If, self.cur_next, blk_end);
        blk.cond = Some(left);
        blk.cond_set = true;
        blk.short_circuit = Some(or_form);
        blk.chain_link = chain;
        blk.stack_depth = self.stack.len();
        self.blocks.push(blk);
    }

    fn handle_jump_forward(&mut self, target: usize) -> bool {
        self.close_blocks_at(self.cur_offset);
        // a forward jump flying over an OPEN (non-top) If block's end
        // boundary implies an else region [end, target) for that block
        for b in self.blocks.iter_mut().rev().skip(1) {
            if matches!(b.kind, BlockType::If)
                && b.short_circuit.is_none()
                && b.else_end.is_none()
                && b.end < target
                && b.end > self.cur_offset
            {
                b.else_end = Some(target);
            }
        }
        if let Some(top) = self.blocks.last() {
            match top.kind {
                BlockType::If if top.else_end.is_none() && top.short_circuit.is_none() => {
                    if target > top.end {
                        // end of then-body jumping over the else branch
                        if let Some(t) = self.blocks.last_mut() {
                            t.else_end = Some(target);
                        }
                        return true;
                    }
                    if target == top.end {
                        // dead-code skip: then-body complete, no else clause
                        // — close now so an enclosing block can transition
                        // to its own else region at the next instruction.
                        // A 3.12 chained-comparison merge (value_merge)
                        // ends here: close folds the links, and the jump
                        // skips the dead `SWAP 2; POP_TOP` else arm.
                        let is_chain_merge = self
                            .blocks
                            .last()
                            .map_or(false, |b| b.value_merge.is_some());
                        self.force_close_top(self.cur_next);
                        if is_chain_merge {
                            self.skip_until = Some(target);
                        }
                        return true;
                    }
                    return true;
                }
                BlockType::If if top.short_circuit.is_some() => {
                    if target >= top.end && top.chain_link {
                        // 3.10/3.11 chained comparison: the then arm jumps
                        // straight to the merge, over the else arm whose
                        // ROT_TWO/POP_TOP cleanup would swap the merged
                        // value with the stack below it — close (folding
                        // the links) and skip the dead cleanup
                        let end = top.end;
                        self.force_close_top(end);
                        self.skip_until = Some(target);
                        return true;
                    }
                    // value-merge region: remember where the false path ends
                    if let Some(t) = self.blocks.last_mut() {
                        t.else_end = Some(target);
                    }
                    return true;
                }
                BlockType::Else | BlockType::Except => {
                    // jump out of an else/except body: close it now; when an
                    // Else block was created from an elif region mark it so
                    // the closer can rebuild the chain
                    self.close_blocks_at(top.end);
                    return true;
                }
                BlockType::While | BlockType::For if target > top.end => {
                    // jump over the loop-else region: mark it now so the
                    // upcoming close creates the Else block
                    if let Some(t) = self.blocks.last_mut() {
                        t.loop_else_end = Some(target);
                    }
                    return true;
                }
                BlockType::Try => {
                    // try body finished; else clause runs to target, then finally
                    let finally_target = top.finally_target;
                    let end = top.end;
                    if let Some(t) = self.blocks.last_mut() {
                        t.loop_else_end = Some(target);
                    }
                    let _ = (finally_target, end);
                    return true;
                }
                _ => {}
            }
        }
        true
    }

    /// elif detection: `elif c:` and `else: if c:` compile identically, so
    /// we canonicalize — if the first jump inside the else region is a
    /// conditional jump, treat the region as an elif continuation.
    fn starts_with_cond_jump(&self, pos: usize, limit: usize) -> bool {
        for inst in self.instrs.iter() {
            if inst.start < pos {
                continue;
            }
            if inst.start >= limit {
                return false;
            }
            if inst.op == Op::CACHE {
                continue;
            }
            if inst.target.is_some() {
                return matches!(
                    inst.op,
                    Op::POP_JUMP_IF_FALSE
                        | Op::POP_JUMP_IF_TRUE
                        | Op::POP_JUMP_FORWARD_IF_FALSE
                        | Op::POP_JUMP_FORWARD_IF_TRUE
                        | Op::POP_JUMP_BACKWARD_IF_FALSE
                        | Op::POP_JUMP_BACKWARD_IF_TRUE
                );
            }
            if matches!(inst.op, Op::RETURN_VALUE | Op::RETURN_CONST | Op::RAISE_VARARGS) {
                return false;
            }
        }
        false
    }

    /// The end of an else region is the earlier of its JUMP_FORWARD target
    /// and the first boundary that a jump INSIDE the region exits to (the
    /// compiler may leave the else body with a conditional jump instead of
    /// falling through). Targets of jumps internal to nested structures
    /// (with/try/loop cleanup) must not truncate the region.
    fn next_boundary(&self, from: usize, limit: usize) -> usize {
        let mut best = limit;
        // a target t is INTERNAL when some jump inside [from, t) lands in
        // (from, t] — with/try/loop cleanup targets must not truncate the
        // region; genuine early exits (jumps from before the region or
        // unconditional back edges out of it) still do
        for &t in &self.targets {
            if t <= from || t >= best {
                continue;
            }
            let internal = self
                .instrs
                .iter()
                .skip_while(|i| i.offset < from)
                .take_while(|i| i.offset < t)
                .any(|i| i.target.map_or(false, |it| it > from && it <= t));
            if !internal {
                best = t;
            }
        }
        best
    }

    /// If `target` is an exit point of some enclosing loop (the offset
    /// right after its back edge / a FOR_ITER exit), return its block index.
    fn find_loop_exit(&self, target: usize) -> Option<usize> {
        let te = self.effective_offset(target);
        for (i, b) in self.blocks.iter().enumerate() {
            if !matches!(b.kind, BlockType::While | BlockType::For) {
                continue;
            }
            if let Some(exit) = self.loop_exit_offset(b) {
                if self.effective_offset(exit) == te {
                    return Some(i);
                }
                // a break flying over a for/while-else region: any offset
                // strictly between the exhaustion exit and the else end is
                // also a loop exit
                if let Some(le) = b.loop_else_end {
                    if exit < target && target <= le {
                        return Some(i);
                    }
                }
                // for-else detected at close time may not be recorded yet:
                // accept a forward jump that lands past the block end on an
                // instruction no jump targets (post-else continuation)
                if target > b.end && !self.targets.contains(&target) {
                    return Some(i);
                }
                // a break jumping over the loop epilogue (END_FOR and the
                // iterator-drop POP_TOPs) lands on the real continuation
                if target > b.end {
                    if let Some(&ei) = self.idx_of.get(&b.end) {
                        let epilogue = self.instrs[ei..]
                            .iter()
                            .take_while(|x| x.offset < target)
                            .all(|x| {
                                matches!(
                                    x.op,
                                    Op::END_FOR
                                        | Op::POP_TOP
                                        | Op::POP_ITER
                                        | Op::NOP
                                        | Op::NOT_TAKEN
                                )
                            })
                            && self.instrs.get(ei).map_or(false, |x| x.offset < target);
                        if epilogue {
                            return Some(i);
                        }
                    }
                }
            }
        }
        None
    }

    /// Skip NOP/NOT_TAKEN padding so jump targets that differ only by
    /// padding compare equal.
    fn effective_offset(&self, mut off: usize) -> usize {
        loop {
            let Some(&i) = self.idx_of.get(&off) else {
                return off;
            };
            let ins = &self.instrs[i];
            if ins.offset != off {
                return off;
            }
            if matches!(ins.op, Op::NOP | Op::NOT_TAKEN | Op::CACHE) {
                off = ins.end();
                continue;
            }
            return off;
        }
    }

    fn loop_exit_offset(&self, b: &Block) -> Option<usize> {
        match b.kind {
            BlockType::For => Some(b.end),
            BlockType::While => {
                if b.cond_end != usize::MAX && b.start < b.end {
                    // rotated while: exit = target of the cond jump, i.e.
                    // the instruction whose end == cond_end
                    self.instrs
                        .iter()
                        .find(|i| i.end() == b.cond_end && i.target.is_some())?
                        .target
                } else if b.end < usize::MAX && b.start < b.end {
                    // SETUP_LOOP era: the block end IS the loop exit
                    Some(b.end)
                } else {
                    // 3.8+ `while True`: no SETUP_LOOP and no cond jump;
                    // back edge jumps to b.start, the following instruction
                    // offset is the exit
                    self.back_edge_exit(b.start)
                }
            }
            _ => None,
        }
    }

    /// True when `off` is a POP_BLOCK whose end reaches `end` (the
    /// SETUP_LOOP-era cond jump targets the loop's POP_BLOCK, one byte
    /// before the block end).
    fn is_pop_block_before(&self, off: usize, end: usize) -> bool {
        self.idx_of
            .get(&off)
            .and_then(|&i| self.instrs.get(i))
            .map_or(false, |x| x.op == Op::POP_BLOCK && x.end() <= end)
    }

    /// 3.8+ for-else: when the For closes at the FOR_ITER exhaustion exit,
    /// a following unconditional jump over untargeted code marks an else
    /// region [pos, jump_target). Plain loops have no such jump (the next
    /// statement follows directly or a nested structure intervenes).
    fn probe_for_else(&self, pos: usize) -> Option<usize> {
        let Some(&pi) = self.idx_of.get(&pos) else {
            return None;
        };
        for ins in self.instrs.iter().skip(pi) {
            if let Some(t) = ins.target {
                if matches!(
                    ins.op,
                    Op::JUMP_ABSOLUTE
                        | Op::JUMP_FORWARD
                        | Op::JUMP
                        | Op::JUMP_BACKWARD
                        | Op::JUMP_BACKWARD_NO_INTERRUPT
                ) && t > pos
                    && !self.targets.contains(&t)
                {
                    return Some(t);
                }
                // any other targeted jump: nested structure, no for-else
                return None;
            }
            if matches!(ins.op, Op::NOP | Op::NOT_TAKEN | Op::CACHE | Op::POP_TOP) {
                continue;
            }
            // plain statement code with no jump: no else region
            return None;
        }
        None
    }

    fn back_edge_exit(&self, loop_start: usize) -> Option<usize> {
        for inst in self.instrs.iter() {
            if inst.is_backward && inst.target == Some(loop_start) {
                return self.instrs.iter().find(|i| i.start > inst.end()).map(|i| i.start);
            }
        }
        None
    }

    /// True when [top, cur) contains only condition-evaluation instructions
    /// (loads/constants/compares), meaning `top` is the start of the cond
    /// expression of a rotated while loop.
    fn is_cond_expr_top(&self, top: usize, cur: usize) -> bool {
        if top == cur {
            return true;
        }
        let Some(&ti) = self.idx_of.get(&top) else {
            return false;
        };
        let Some(&ci) = self.idx_of.get(&cur) else {
            return false;
        };
        if ti >= ci {
            return false;
        }
        let mut prev: Option<Op> = None;
        let mut prev_arg = 0u32;
        let ok = self.instrs[ti..ci].iter().all(|inst| {
            let good = match inst.op {
                Op::RETURN_VALUE
                | Op::RETURN_CONST
                | Op::POP_TOP
                | Op::STORE_SUBSCR
                | Op::STORE_ATTR => false,
                Op::STORE_FAST | Op::STORE_NAME | Op::STORE_GLOBAL | Op::STORE_DEREF => {
                    // walrus: the value was duplicated right before
                    matches!(prev, Some(Op::DUP_TOP))
                        || (prev == Some(Op::COPY) && prev_arg == 1)
                }
                // value-producing calls are fine inside conditions
                Op::CALL
                | Op::CALL_FUNCTION
                | Op::CALL_METHOD
                | Op::CALL_FUNCTION_KW
                | Op::CALL_FUNCTION_EX => true,
                _ => match inst.target {
                    // value-level branch (ternary/boolop): self-contained
                    // when every target stays inside the region
                    Some(t) => t >= top && t <= cur,
                    None => true,
                },
            };
            prev = Some(inst.op);
            prev_arg = inst.arg;
            good
        });
        ok
    }

    /// True when a backward jump targets an enclosing loop's top while
    /// inner blocks (ifs or nested loops) are still open — a `continue`.
    /// The final back edge of a loop arrives with the loop as the topmost
    /// block and closes it instead.
    fn is_continue_jump(&self, target: usize) -> bool {
        let mut depth = 0usize;
        for b in self.blocks.iter().rev() {
            if matches!(b.kind, BlockType::Main) {
                break;
            }
            if matches!(b.kind, BlockType::While | BlockType::For)
                && b.end != usize::MAX
                && b.end <= self.cur_offset
            {
                // layout-exhausted loop awaiting its close: transparent
                continue;
            }
            if !matches!(b.kind, BlockType::While | BlockType::For) {
                depth += 1;
                continue;
            }
            if matches!(b.kind, BlockType::While | BlockType::For) {
                if b.start == target
                    || (b.cond_end != usize::MAX
                        && (b.cond_end == target
                            || (b.start <= target && target < b.cond_end)))
                {
                    return depth > 0;
                }
                if b.start < target && target < b.end {
                    return depth > 0;
                }
                depth += 1;
            }
        }
        false
    }

    fn close_inner_blocks_to_loop(&mut self) {
        // find innermost enclosing loop and close everything above it
        let n = self.blocks.len();
        for i in (0..n).rev() {
            if matches!(self.blocks[i].kind, BlockType::While | BlockType::For) {
                while self.blocks.len() > i + 1 {
                    let pos = self.blocks.last().map(|b| b.start).unwrap_or(0);
                    self.force_close_top(pos);
                }
                return;
            }
        }
    }

    /// 3.8+ has no SETUP_LOOP: a `while True:` body ends with an
    /// unconditional backward jump and has no cond jump at its top.
    /// Register those loops so the block opens when execution reaches the
    /// top and closes at the back edge.
    fn prescan_while_true(&mut self) {
        if !self.version.at_least(3, 8) || self.inline_comp.is_some() {
            return;
        }
        let is_back_jump = |i: &Instruction| {
            i.is_backward
                && matches!(
                    i.op,
                    Op::JUMP_ABSOLUTE
                        | Op::JUMP_BACKWARD
                        | Op::JUMP_BACKWARD_NO_INTERRUPT
                )
        };
        let is_cond_jump = |o: Op| {
            matches!(
                o,
                Op::POP_JUMP_IF_FALSE
                    | Op::POP_JUMP_IF_TRUE
                    | Op::POP_JUMP_FORWARD_IF_FALSE
                    | Op::POP_JUMP_FORWARD_IF_TRUE
                    | Op::JUMP_IF_FALSE_OR_POP
                    | Op::JUMP_IF_TRUE_OR_POP
                    | Op::POP_JUMP_IF_NONE
                    | Op::POP_JUMP_IF_NOT_NONE
            )
        };
        // loop tops claimed by rotated-while cond jumps (section 6 handles
        // those), by FOR_ITER loops, and by SETUP_* blocks
        let mut claimed: Vec<usize> = Vec::new();
        let back_ops = |o: Op| {
            matches!(
                o,
                Op::JUMP_ABSOLUTE
                    | Op::JUMP_BACKWARD
                    | Op::JUMP_BACKWARD_NO_INTERRUPT
            )
        };
        // rotated whiles whose exit test PRECEDES the back edge in layout
        // (3.14 walrus-while: `<cond expr>; PJIF_NONE exit; NOT_TAKEN;
        // <body>; JUMP_BACKWARD top`): the back edge lies outside [cj, t),
        // so scan the region BEFORE the exit jump as well
        for (ci, cj) in self.instrs.iter().enumerate() {
            if !is_cond_jump(cj.op) || cj.target.map_or(true, |t| t <= cj.offset) {
                continue;
            }
            for ins in &self.instrs[..ci] {
                if ins.is_backward
                    && back_ops(ins.op)
                    && ins.target.map_or(false, |bt| {
                        bt < ins.offset && self.is_cond_expr_top(bt, cj.offset)
                    })
                {
                    if let Some(bt) = ins.target {
                        claimed.push(bt);
                    }
                }
            }
        }
        for (ci, cj) in self.instrs.iter().enumerate() {
            if !is_cond_jump(cj.op) {
                continue;
            }
            let Some(t) = cj.target else { continue };
            if t <= cj.offset {
                continue;
            }
            let Some(&ti) = self.idx_of.get(&t) else {
                continue;
            };
            // back edges between this cond jump and its target:
            // * target starts a pure cond-expr region ending at this jump
            //   -> rotated while, claim its top (block while-True synthesis)
            // * otherwise this is a 3.14-style `if c: break` flying over
            //   the ENCLOSING loop's own back edge — that loop's top must
            //   stay unclaimed, and this region claims nothing
            let straddle: Vec<usize> = self.instrs[ci..ti]
                .iter()
                .filter(|ins| ins.is_backward && back_ops(ins.op))
                .filter_map(|ins| ins.target)
                .collect();
            if !straddle.is_empty() {
                for bt in straddle {
                    if self.is_cond_expr_top(bt, cj.offset) {
                        claimed.push(bt);
                    }
                }
                continue;
            }
            for ins in &self.instrs[ci..ti] {
                if let Some(bt) = ins.target {
                    if ins.is_backward && bt <= cj.offset {
                        claimed.push(bt);
                    }
                }
            }
        }
        for ins in &self.instrs {
            if matches!(
                ins.op,
                Op::FOR_ITER | Op::FOR_LOOP | Op::SETUP_LOOP | Op::SETUP_FINALLY | Op::SETUP_EXCEPT
            ) {
                if let Some(t) = ins.target {
                    claimed.push(t);
                }
                if matches!(ins.op, Op::FOR_ITER | Op::FOR_LOOP) {
                    claimed.push(ins.offset);
                }
            }
        }
        let mut found: Vec<(usize, usize)> = Vec::new();
        for (bi, bj) in self.instrs.iter().enumerate() {
            if !is_back_jump(bj) {
                continue;
            }
            let Some(t) = bj.target else { continue };
            if claimed.contains(&t) || found.iter().any(|(ft, _)| *ft == t) {
                continue;
            }
            // the region [t, bj) must be straight-line loop body: every
            // jump inside stays within the region (or is a dead duplicate
            // back edge); breaks out of it disqualify the shape
            let Some(&ti) = self.idx_of.get(&t) else {
                continue;
            };
            if ti > bi {
                continue;
            }
            // reject back edges that belong to an out-of-line handler
            // cleanup: scanning back from the jump, a PUSH_EXC_INFO comes
            // before any inner back edge (a real loop body would show its
            // nested loops' back edges first). Such jumps are suppressed
            // -exception continuations (with/try), not `while True` edges.
            let mut handler_origin = false;
            for k in (ti..bi).rev() {
                let ins = &self.instrs[k];
                if ins.op == Op::PUSH_EXC_INFO {
                    handler_origin = true;
                    break;
                }
                if ins.is_backward
                    && matches!(
                        ins.op,
                        Op::JUMP_ABSOLUTE
                            | Op::JUMP_BACKWARD
                            | Op::JUMP_BACKWARD_NO_INTERRUPT
                            | Op::FOR_ITER
                            | Op::FOR_LOOP
                    )
                {
                    break;
                }
            }
            if handler_origin {
                continue;
            }
            // generator/async resume machinery is never a source loop:
            // JUMP_BACKWARD_NO_INTERRUPT is exclusively the yield-resume
            // edge; a bare back edge directly after YIELD_VALUE/RESUME or
            // inside a SEND/CLEANUP_THROW region belongs to the protocol.
            // A real `while True` body may CONTAIN yields — its back edge
            // sits after body statements, not the resume point.
            let prev_op = if bi > 0 { Some(self.instrs[bi - 1].op) } else { None };
            let prev2_op = if bi > 1 { Some(self.instrs[bi - 2].op) } else { None };
            // direct yield-resume edge: YIELD_VALUE; [RESUME;] back-jump
            // (a lone RESUME follows every 3.11+ CALL — not a signal)
            let resume_edge = matches!(prev_op, Some(Op::YIELD_VALUE))
                || (matches!(prev_op, Some(Op::RESUME))
                    && matches!(prev2_op, Some(Op::YIELD_VALUE)));
            if bj.op == Op::JUMP_BACKWARD_NO_INTERRUPT
                || resume_edge
                || self.instrs[ti..bi].iter().any(|ins| {
                    matches!(
                        ins.op,
                        Op::YIELD_FROM
                            | Op::SEND
                            | Op::GET_YIELD_FROM_ITER
                            | Op::CLEANUP_THROW
                    )
                })
            {
                continue;
            }
            let mut breaks: Vec<usize> = Vec::new();
            let clean = self.instrs[ti..bi].iter().all(|ins| {
                ins.target.map_or(true, |it| {
                    if (it >= t && it <= bj.offset) || (ins.is_backward && it == t) {
                        true
                    } else if !ins.is_backward && it > bj.offset {
                        // a `break` flying to the loop exit
                        breaks.push(it);
                        true
                    } else {
                        false
                    }
                })
            });
            if !clean {
                continue;
            }
            let uniform_exit = breaks.first().copied().and_then(|e| {
                if breaks.iter().all(|b| *b == e) {
                    Some(e)
                } else {
                    None
                }
            });
            match uniform_exit {
                Some(e) => found.push((t, e)),
                None => found.push((t, bj.end())),
            }
        }
        self.while_true_loops = found;
    }

    fn handle_jump_backward(&mut self, target: usize) {
        // dead back-edge padding: the loop owning this top already closed
        if self
            .closed_loop_tops
            .iter()
            .any(|t| self.effective_offset(*t) == self.effective_offset(target))
        {
            return;
        }
        // back edge at the end of the try body or inside the handler chain
        // (`continue`-equivalent): not the loop's own back edge, ignore it
        // so the loop stays open for the handler chain / else region that
        // follows; the chain machinery emits the Try at the real back edge
        if self.legacy_try.as_ref().map_or(false, |l| {
            (self.cur_offset >= l.handler_start
                && l.else_start.map_or(true, |es| self.cur_offset < es))
                || (l.handlers.is_empty()
                    && l.else_start.is_none()
                    && self.cur_offset < l.handler_start)
        }) {
            if self.legacy_handler.is_some() && !self.in_handler_prelude {
                // handler still open (past its prelude): an explicit
                // `continue` in the handler body — the implicit post-handler
                // back edge comes after POP_EXCEPT/END_FINALLY folded it.
                // py2 emits dead duplicate back edges after the continue;
                // only the first is real.
                let already = self
                    .legacy_handler
                    .as_ref()
                    .map_or(false, |h| matches!(h.body.last(), Some(Stmt::Continue)));
                if !already
                    && self
                        .blocks
                        .iter()
                        .any(|b| matches!(b.kind, BlockType::While | BlockType::For) && b.start == target)
                {
                    self.push_stmt(Stmt::Continue);
                }
            }
            return;
        }
        self.close_blocks_at(self.cur_offset);
        let n = self.blocks.len();
        for i in (0..n).rev() {
            if matches!(self.blocks[i].kind, BlockType::While | BlockType::For) {
                let b = &self.blocks[i];
                // rotated while back edge: jumps to the body top right after
                // the cond evaluation — pure loop continuation, no-op
                if b.cond_end != usize::MAX && target == b.cond_end && b.start < target {
                    return;
                }
                // 3.12+: the then-branch of an if/else inside a loop can
                // end with JUMP_BACKWARD straight to the loop top (the
                // compiler fuses "skip else" and "continue"). Close the
                // then-part, open the Else region ending at the loop's own
                // back edge, and let that back edge close everything.
                if b.start == target || b.cond_end == target {
                    let top_is_pending_if = matches!(
                        self.blocks.last(),
                        Some(t) if t.kind == BlockType::If
                            && t.else_end.is_none()
                            && t.short_circuit.is_none()
                            && t.end > self.cur_offset
                    );
                    if top_is_pending_if {
                        // degenerate fusion: the back edge IS the whole
                        // then-region (`if c: break` with fall-through
                        // continue) — record the continue and close; the
                        // Else region holds the break block and the close
                        // normalizer flips the polarity back
                        if self.blocks.last().map(|t| t.start) == Some(self.cur_offset) {
                            let end = self.blocks.last().unwrap().end;
                            let t = self.blocks.last_mut().unwrap();
                            t.stmts.push(Stmt::Continue);
                            self.force_close_top(end);
                            return;
                        }
                        let else_end = self
                            .instrs
                            .iter()
                            .filter(|x| {
                                x.is_backward
                                    && x.target == Some(target)
                                    && x.offset > self.cur_offset
                            })
                            .map(|x| x.offset)
                            .next()
                            .unwrap_or(b.end);
                        let t = self.blocks.last_mut().unwrap();
                        t.else_end = Some(else_end);
                        let end = t.end;
                        self.force_close_top(end);
                        return;
                    }
                }
                if b.start == target || b.end == target {
                    // SETUP_LOOP-era while: every continue and the final
                    // back edge target the loop top; the loop closes only
                    // when its POP_BLOCK follows this jump
                    let is_setup_era = !self.version.at_least(3, 8)
                        && b.cond_end == usize::MAX
                        && b.end < usize::MAX
                        && self.idx_of.contains_key(&b.end);
                    if is_setup_era {
                        // py2.7+ exits straight into POP_BLOCK; py2.6's
                        // peek-jump condition retains its value, so the
                        // exit is `POP_TOP; POP_BLOCK` — the loop-end back
                        // edge must not be mistaken for a `continue`.
                        let next_is_pop_block =
                            match self.idx_of.get(&self.cur_offset) {
                                Some(&ci) => match self.instrs.get(ci + 1) {
                                    Some(x) if x.op == Op::POP_BLOCK => true,
                                    Some(x) if x.op == Op::POP_TOP => self
                                        .instrs
                                        .get(ci + 2)
                                        .map_or(false, |y| {
                                            y.op == Op::POP_BLOCK
                                        }),
                                    _ => false,
                                },
                                None => false,
                            };
                        if !next_is_pop_block {
                            self.push_stmt(Stmt::Continue);
                            return;
                        }
                    }
                    self.closed_loop_tops.push(b.start);
                    // async-for: the back edge is followed by the
                    // CLEANUP_THROW paths and END_ASYNC_FOR — dead for the
                    // linear walk, skip to the continuation
                    let is_async_for = b.is_async
                        && matches!(b.kind, BlockType::For);
                    if is_async_for {
                        if let Some(&ci) = self.idx_of.get(&self.cur_offset) {
                            for ins in self.instrs.iter().skip(ci + 1) {
                                if ins.op == Op::END_ASYNC_FOR {
                                    self.skip_until = Some(ins.end());
                                    break;
                                }
                                if !matches!(
                                    ins.op,
                                    Op::CLEANUP_THROW
                                        | Op::JUMP_BACKWARD
                                        | Op::JUMP_BACKWARD_NO_INTERRUPT
                                        | Op::JUMP_ABSOLUTE
                                        | Op::POP_TOP
                                        | Op::NOP
                                        | Op::NOT_TAKEN
                                ) {
                                    break;
                                }
                            }
                        }
                    }
                    // close everything above the loop, then the loop itself
                    // exactly once — its close may push a continuation block
                    // (ForElse) that must stay open for the following region
                    while self.blocks.len() > i + 1 {
                        let p = self.blocks.last().map(|x| x.start).unwrap_or(target);
                        self.force_close_top(p);
                    }
                    self.force_close_top(target);
                    return;
                }
                if b.start < target && target < b.end {
                    // back edge into the middle of this loop
                    while self.blocks.len() > i + 1 {
                        self.force_close_top(target);
                    }
                    self.push_stmt(Stmt::Continue);
                    return;
                }
            }
        }
        // backward jump that matches no open loop: only emit `continue`
        // when one is actually on the block stack
        if self
            .blocks
            .iter()
            .any(|b| matches!(b.kind, BlockType::While | BlockType::For))
        {
            self.push_stmt(Stmt::Continue);
        } else if self.broken_loop_top == Some(target) {
            // dead back-edge padding after a `break` closed the loop
        } else if self
            .closed_loop_tops
            .iter()
            .any(|t| self.effective_offset(*t) == self.effective_offset(target))
        {
            // dead back-edge padding after the loop already closed
        } else {
            self.mark_unclean();
        }
    }

    fn handle_for_iter(&mut self, target: usize, is_async: bool) {
        if !self.pending_stores.is_empty() {
            self.flushing = true;
            self.flush_pending_stores();
            self.flushing = false;
        }
        let iter = self.pop_expr();
        // FOR_ITER leaves the iterator and pushes the next item; the item is
        // consumed by the following STORE (the loop target), so keep the
        // iterator on the stack and let emit_store swallow it.
        self.push(iter.clone());
        self.awaiting_for_target = true;
        // Reuse an open uninitialized While block (SETUP_LOOP era) or open
        // a fresh For block (3.8+).
        let mut convert = false;
        if let Some(top) = self.blocks.last_mut() {
            if matches!(top.kind, BlockType::While) && !top.cond_set {
                convert = true;
            }
        }
        if convert {
            let top = self.blocks.last_mut().unwrap();
            top.kind = BlockType::For;
            // back edges target the FOR_ITER instruction itself, so the
            // block must start there (matches the fresh-For path below)
            top.start = self.cur_offset;
            top.iter = Some(iter);
            top.target = None;
            top.is_async = is_async;
            top.cond_set = true;
            // the FOR_ITER exhaustion exit differs from the SETUP_LOOP
            // target exactly when a for-else region sits between the two:
            // lower the block end to the exit and remember the loop pop
            if target < top.end {
                top.for_setup_end = Some(top.end);
                top.end = target;
            }
        } else {
            // start = FOR_ITER offset so the back edge matches it
            let mut fb = Block::new(BlockType::For, self.cur_offset, target);
            fb.cond_end = self.cur_next;
            fb.iter = Some(iter);
            fb.is_async = is_async;
            fb.cond_set = true;
            self.blocks.push(fb);
        }
    }

    fn handle_pop_block(&mut self) {
        // POP_BLOCK ends Try (no finally) or With or loop bodies (<=3.7).
        if let Some(top) = self.blocks.last() {
            match top.kind {
                BlockType::Try => {
                    let end = top.end;
                    self.force_close_top(end);
                }
                BlockType::With => {
                    let end = top.end;
                    self.force_close_top(end);
                }
                BlockType::Container => {
                    // try/finally container closed at END_FINALLY; ignore
                }
                BlockType::While | BlockType::For
                    if top.end == self.cur_next && top.cond_set =>
                {
                    // SETUP_LOOP-era loop whose end is exactly this
                    // POP_BLOCK: close here so a following else region
                    // (loop_else_end) opens as WhileElse/ForElse
                    let end = top.end;
                    self.force_close_top(end);
                }
                _ => {}
            }
        }
    }

    fn handle_with_setup(&mut self, handler_target: Option<usize>, is_async: bool) {
        let ctx_e = match self.pending_async_with_ctx.take() {
            Some(c) => {
                // <=3.10: consume the awaited __aenter__ placeholder left
                // by BEFORE_ASYNC_WITH + YIELD_FROM
                let _ = self.pop_expr();
                c
            }
            None => self.pop_expr(),
        };
        // SETUP_WITH pushes the bound __exit__ (and 3.2+ two more dummies)
        self.with_exits += 1;
        if let Some(h) = handler_target {
            self.with_handler_starts.insert(h);
        }
        let item = WithItem {
            ctx: ctx_e,
            target: None,
        };
        // the SETUP_WITH* jump target is the exception-time cleanup handler;
        // the normal-exit POP_BLOCK usually sits right before it
        let start = self.cur_next;
        let end = self
            .with_regions
            .get(&start)
            .copied()
            .or(handler_target)
            .unwrap_or(usize::MAX);
        let mut wb = Block::new(BlockType::With, start, end);
        wb.is_async = is_async;
        wb.with_item = Some(item);
        self.blocks.push(wb);
        // The interpreter pushes __exit__ bound methods plus the __enter__
        // result; model the result with a placeholder expression: the
        // following STORE_* turns into the `as` target, POP_TOP discards it.
        self.push(self.name_expr(WITH_RESULT_PLACEHOLDER));
    }

    fn handle_with_body_end(&mut self) {
        // WITH_CLEANUP(_FINISH) / WITH_EXCEPT_START: close the With block
        if let Some(top) = self.blocks.last() {
            if top.kind == BlockType::With {
                let pos = top.start.max(1);
                self.force_close_top(pos);
            }
        }
    }

    fn close_finally(&mut self) {
        // END_FINALLY / POP_FINALLY closes Finally (and Container) blocks
        if let Some(top) = self.blocks.last() {
            if top.kind == BlockType::Finally {
                let pos = top.start;
                self.force_close_top(pos);
            }
        }
        if let Some(top) = self.blocks.last() {
            if top.kind == BlockType::Container {
                let pos = top.start;
                self.force_close_top(pos);
            }
        }
    }

    fn handle_slice_ops(&mut self, inst: &Instruction) {
        let mk = |start: Option<ExprRef>, stop: Option<ExprRef>| -> ExprRef {
            Rc::new(Expr::Slice(Box::new(SliceExpr {
                start,
                stop,
                step: None,
            })))
        };
        match inst.op {
            Op::SLICE_0 => {
                let seq = self.pop_expr();
                self.push(Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(None, None),
                }));
            }
            Op::SLICE_1 => {
                let start = self.pop_expr();
                let seq = self.pop_expr();
                self.push(Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(Some(start), None),
                }));
            }
            Op::SLICE_2 => {
                let stop = self.pop_expr();
                let seq = self.pop_expr();
                self.push(Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(None, Some(stop)),
                }));
            }
            Op::SLICE_3 => {
                let stop = self.pop_expr();
                let start = self.pop_expr();
                let seq = self.pop_expr();
                self.push(Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(Some(start), Some(stop)),
                }));
            }
            // py2 STORE_SLICE+n: the assigned VALUE is pushed FIRST —
            // stack bottom..top is [value, seq, start?, stop?]
            Op::STORE_SLICE_0 => {
                let seq = self.pop_expr();
                let val = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(None, None),
                });
                self.emit_store(target, val);
            }
            Op::STORE_SLICE_1 => {
                let start = self.pop_expr();
                let seq = self.pop_expr();
                let val = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(Some(start), None),
                });
                self.emit_store(target, val);
            }
            Op::STORE_SLICE_2 => {
                let stop = self.pop_expr();
                let seq = self.pop_expr();
                let val = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(None, Some(stop)),
                });
                self.emit_store(target, val);
            }
            Op::STORE_SLICE_3 => {
                let stop = self.pop_expr();
                let start = self.pop_expr();
                let seq = self.pop_expr();
                let val = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(Some(start), Some(stop)),
                });
                self.emit_store(target, val);
            }
            Op::STORE_SLICE => {
                // 3.12+: the value is pushed FIRST — stack bottom..top is
                // [value, seq, start, stop], so stop pops first
                let stop = self.pop_expr();
                let start = self.pop_expr();
                let seq = self.pop_expr();
                let val = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(none_if_const_none(start), none_if_const_none(stop)),
                });
                self.emit_store(target, val);
            }
            Op::DELETE_SLICE_0 => {
                let seq = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(None, None),
                });
                self.emit_delete(target);
            }
            Op::DELETE_SLICE_1 => {
                let start = self.pop_expr();
                let seq = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(Some(start), None),
                });
                self.emit_delete(target);
            }
            Op::DELETE_SLICE_2 => {
                let stop = self.pop_expr();
                let seq = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(None, Some(stop)),
                });
                self.emit_delete(target);
            }
            Op::DELETE_SLICE_3 => {
                let stop = self.pop_expr();
                let start = self.pop_expr();
                let seq = self.pop_expr();
                let target = Rc::new(Expr::Subscript {
                    value: seq,
                    index: mk(Some(start), Some(stop)),
                });
                self.emit_delete(target);
            }
            _ => self.mark_unclean(),
        }
    }
}

/// Value-level equality of constant operands — 3.14's LOAD_SMALL_INT
/// rebuilds small ints per instruction, so pointer equality is not enough
/// for the shared operand of a chained comparison.
fn const_value_eq(a: &PyObject, b: &PyObject) -> bool {
    match (a, b) {
        (PyObject::Int(x), PyObject::Int(y)) => x == y,
        (PyObject::Float(x, _), PyObject::Float(y, _)) => x == y,
        (PyObject::Str(x), PyObject::Str(y)) => x == y,
        (PyObject::Bytes(x), PyObject::Bytes(y)) => x == y,
        (PyObject::None, PyObject::None)
        | (PyObject::True, PyObject::True)
        | (PyObject::False, PyObject::False) => true,
        _ => false,
    }
}

/// Merge `a op1 b` + `b op2 c` (sharing operand b) into a chained
/// comparison `a op1 b op2 c`.
fn merge_chain_compare(cond: &ExprRef, v: &ExprRef) -> Option<ExprRef> {
    let Expr::Compare { operands, ops } = &**cond else {
        return None;
    };
    if operands.len() != 2 || ops.len() != 1 {
        return None;
    }
    let Expr::Compare { operands: o2, ops: ops2 } = &**v else {
        return None;
    };
    // the else arm keeps `cond` itself: the chain ends here
    if o2.len() == 2 && ops2.len() == 1 && expr_eq(cond, v) {
        return Some(cond.clone());
    }
    // `v` may already be a merged chain (nested links close inner-first)
    if o2.len() < 2 || ops2.len() + 1 != o2.len() {
        return None;
    }
    let shared = match (&*operands[1], &*o2[0]) {
        (Expr::Name(a), Expr::Name(b)) => a == b,
        (Expr::Const(c1), Expr::Const(c2)) => Rc::ptr_eq(c1, c2) || const_value_eq(c1, c2),
        (Expr::Attribute { value: v1, attr: a1 }, Expr::Attribute { value: v2, attr: a2 }) => {
            a1 == a2 && expr_eq(v1, v2)
        }
        _ => false,
    };
    if !shared {
        return None;
    }
    let mut merged_ops = ops.clone();
    merged_ops.extend(ops2.iter().copied());
    let mut merged_operands = vec![operands[0].clone()];
    merged_operands.extend(o2.iter().cloned());
    Some(Rc::new(Expr::Compare {
        operands: merged_operands,
        ops: merged_ops,
    }))
}

fn keywords_empty(_args: &[ExprRef]) -> bool {
    true
}

/// Sentinel used by the comprehension mini-simulator for the NULL/self slot.
fn null_marker() -> ExprRef {
    Rc::new(Expr::Name("\u{0}null".to_string()))
}

fn is_null_marker(e: &ExprRef) -> bool {
    matches!(&**e, Expr::Name(n) if n.starts_with('\u{0}'))
}

fn star_args_none(_args: &[ExprRef]) -> bool {
    true
}

/// CALL_FUNCTION_EX args come as one tuple, possibly assembled by
/// BUILD_TUPLE_UNPACK(_WITH_CALL): flatten it into positional args plus an
/// optional trailing *args.
fn flatten_ex_args(e: ExprRef) -> (Vec<ExprRef>, Option<ExprRef>) {
    let mut pos = Vec::new();
    let mut star = None;
    let items: Vec<ExprRef> = match &*e {
        Expr::Tuple(v) => v.clone(),
        // a bare (non-tuple) operand is the whole unpacked iterable:
        // `f(*args)` pushes args directly with no BUILD_TUPLE
        other => return (Vec::new(), Some(Rc::new(other.clone()))),
    };
    for it in items {
        match &*it {
            Expr::Starred(inner) => {
                if star.is_none() {
                    star = Some(inner.clone());
                } else if let Some(prev) = star.take() {
                    // multiple stars: keep them as positional Starred items
                    pos.push(Rc::new(Expr::Starred(prev)));
                    star = Some(inner.clone());
                }
            }
            Expr::Tuple(inner) if star.is_none() => {
                // BUILD_TUPLE group of plain positional args
                pos.extend(inner.iter().cloned());
            }
            other => pos.push(Rc::new(other.clone())),
        }
    }
    (pos, star)
}

fn flatten_ex_kwargs(e: ExprRef) -> (Vec<(Option<String>, ExprRef)>, Option<ExprRef>) {
    match &*e {
        Expr::Dict(entries) => {
            let mut kws = Vec::new();
            let mut star = None;
            for (k, v) in entries {
                if let Expr::Starred(inner) = &**k {
                    star = Some(inner.clone());
                    continue;
                }
                let name = match &**k {
                    Expr::Const(o) => match &**o {
                        PyObject::Str(s) => Some(s.clone()),
                        PyObject::Bytes(b) => {
                            Some(String::from_utf8_lossy(b).into_owned())
                        }
                        _ => None,
                    },
                    _ => None,
                };
                kws.push((name, v.clone()));
            }
            (kws, star)
        }
        Expr::Starred(inner) => (Vec::new(), Some(inner.clone())),
        other => (Vec::new(), Some(Rc::new(other.clone()))),
    }
}

fn is_comp_callable(e: &ExprRef) -> bool {
    match &**e {
        Expr::Function(fd) => matches!(
            fd.code.name.as_str(),
            "<listcomp>" | "<setcomp>" | "<dictcomp>" | "<genexpr>"
        ),
        Expr::Name(n) => n == "/*generator*/",
        _ => false,
    }
}

fn flatten_boolop(e: ExprRef, kind: BoolOpKind, out: &mut Vec<ExprRef>) {
    match &*e {
        Expr::BoolOp { op, values } if *op == kind => {
            for v in values {
                flatten_boolop(v.clone(), kind, out);
            }
        }
        _ => out.push(e),
    }
}

const WITH_RESULT_PLACEHOLDER: &str = "/*with-result*/";

/// Shallow structural equality used for augmented-assign target matching.
fn expr_eq(a: &ExprRef, b: &ExprRef) -> bool {
    match (&**a, &**b) {
        (Expr::Name(x), Expr::Name(y)) => x == y,
        (Expr::Attribute { value: v1, attr: a1 }, Expr::Attribute { value: v2, attr: a2 }) => {
            a1 == a2 && expr_eq(v1, v2)
        }
        (Expr::Subscript { value: v1, index: i1 }, Expr::Subscript { value: v2, index: i2 }) => {
            expr_eq(v1, v2) && expr_eq(i1, i2)
        }
        _ => Rc::ptr_eq(a, b),
    }
}

/// Pure value-computation opcodes (no statements, no control flow):
/// a region of only these between two cond jumps means the second jump
/// is part of the same condition, not a nested statement.
impl<'a> Ctx<'a> {
    /// 3.8+ walrus: the value expression was duplicated (DUP_TOP <=3.10,
    /// COPY 1 on 3.11+) right before this store, and the next instruction
    /// is NOT another store (that would be a chained `a = b = v`).
    fn walrus_at_name(&self, inst: &Instruction, name: &str) -> bool {
        // the class-cell idiom (`LOAD __class__; DUP_TOP; STORE_NAME
        // __classcell__`) looks exactly like a walrus — exclude the
        // compiler-generated cell names
        if name.starts_with("__class")
            || name.starts_with("__firstlineno")
            || name.starts_with("__static_attributes")
        {
            return false;
        }
        self.walrus_at(inst)
    }

    fn walrus_at(&self, inst: &Instruction) -> bool {
        if !self.version.at_least(3, 8) {
            return false;
        }
        let Some(&ci) = self.idx_of.get(&inst.offset) else {
            return false;
        };
        if ci == 0 {
            return false;
        }
        let prev = &self.instrs[ci - 1];
        let dup =
            prev.op == Op::DUP_TOP || (prev.op == Op::COPY && prev.arg == 1);
        if !dup {
            return false;
        }
        !matches!(
            self.instrs.get(ci + 1).map(|x| x.op),
            Some(Op::STORE_FAST)
                | Some(Op::STORE_NAME)
                | Some(Op::STORE_DEREF)
                | Some(Op::STORE_GLOBAL)
                | Some(Op::STORE_FAST_MAYBE_NULL)
        )
    }
}

fn is_pure_value_op(op: Op) -> bool {
    matches!(
        op,
        Op::PUSH_NULL
            | Op::PRECALL
            | Op::LOAD_FAST
            | Op::LOAD_FAST_CHECK
            | Op::LOAD_FAST_BORROW
            | Op::LOAD_FAST_LOAD_FAST
            | Op::LOAD_FAST_BORROW_LOAD_FAST_BORROW
            | Op::LOAD_SMALL_INT
            | Op::LOAD_COMMON_CONSTANT
            | Op::LOAD_SUPER_ATTR
            | Op::LOAD_NAME
            | Op::LOAD_GLOBAL
            | Op::LOAD_CONST
            | Op::LOAD_ATTR
            | Op::LOAD_DEREF
            | Op::LOAD_METHOD
            | Op::LOAD_BUILD_CLASS
            | Op::LOAD_CLOSURE
            | Op::LOAD_CLASSDEREF
            | Op::COMPARE_OP
            | Op::IS_OP
            | Op::CONTAINS_OP
            | Op::BINARY_OP
            | Op::BINARY_SUBSCR
            | Op::CALL
            | Op::CALL_FUNCTION
            | Op::CALL_METHOD
            | Op::CALL_FUNCTION_KW
            | Op::BUILD_TUPLE
            | Op::BUILD_LIST
            | Op::BUILD_MAP
            | Op::BUILD_SET
            | Op::BUILD_STRING
            | Op::UNARY_NOT
            | Op::UNARY_NEGATIVE
            | Op::UNARY_POSITIVE
            | Op::UNARY_INVERT
            | Op::TO_BOOL
            | Op::FORMAT_VALUE
            | Op::COPY
            | Op::NOP
            | Op::NOT_TAKEN
            | Op::CACHE
            | Op::EXTENDED_ARG
    )
}

fn simplify_not(e: ExprRef) -> ExprRef {
    match &*e {
        Expr::Unary {
            op: UnaryOp::Not,
            operand,
        } => operand.clone(),
        _ => e,
    }
}

/// 3.14: extended slices arrive as `slice(a, b, c)` calls or marshalled
/// slice constants; normalize both to Expr::Slice.
fn normalize_slice_call(idx: ExprRef) -> ExprRef {
    match &*idx {
        Expr::Call { func, args, keywords, star_args: None, star_kwargs: None }
            if keywords.is_empty()
                && matches!(&**func, Expr::Name(n) if n == "slice")
                && (2..=3).contains(&args.len()) =>
        {
            Rc::new(Expr::Slice(Box::new(SliceExpr {
                start: none_if_const_none(args[0].clone()),
                stop: none_if_const_none(args[1].clone()),
                step: args.get(2).cloned().and_then(none_if_const_none),
            })))
        }
        Expr::Const(o) => match &**o {
            PyObject::Slice(a, b, c) => Rc::new(Expr::Slice(Box::new(SliceExpr {
                start: none_if_const_const(a.clone()),
                stop: none_if_const_const(b.clone()),
                step: none_if_const_const(c.clone()),
            }))),
            _ => idx,
        },
        _ => idx,
    }
}

fn none_if_const_const(o: ObjectRef) -> Option<ExprRef> {
    if matches!(&*o, PyObject::None) {
        None
    } else {
        Some(Rc::new(Expr::Const(o)))
    }
}

fn none_if_const_none(e: ExprRef) -> Option<ExprRef> {
    match &*e {
        Expr::Const(o) if matches!(&**o, PyObject::None) => None,
        _ => Some(e),
    }
}

fn expr_to_fstring(e: ExprRef) -> FString {
    match &*e {
        Expr::FString(f) => f.as_ref().clone(),
        // a plain constant spec string is literal spec text
        Expr::Const(o) => match &**o {
            PyObject::Str(s) => FString {
                parts: vec![FStringPart::Literal(s.clone())],
            },
            PyObject::Bytes(b) => FString {
                parts: vec![FStringPart::Literal(
                    String::from_utf8_lossy(b).into_owned(),
                )],
            },
            _ => FString {
                parts: vec![FStringPart::Value {
                    value: e,
                    conversion: None,
                    format_spec: None,
                }],
            },
        },
        other => FString {
            parts: vec![FStringPart::Value {
                value: Rc::new(other.clone()),
                conversion: None,
                format_spec: None,
            }],
        },
    }
}

fn cmp_from_index(idx: usize) -> CmpOp {
    match idx {
        0 => CmpOp::Lt,
        1 => CmpOp::LtE,
        2 => CmpOp::Eq,
        3 => CmpOp::NotEq,
        4 => CmpOp::Gt,
        5 => CmpOp::GtE,
        6 => CmpOp::In,
        7 => CmpOp::NotIn,
        8 => CmpOp::Is,
        9 => CmpOp::IsNot,
        10 => CmpOp::ExceptionMatch,
        _ => CmpOp::Eq,
    }
}

// =====================  stack events, calls, functions, classes  =====================

impl<'a> Ctx<'a> {
    fn handle_pop_top(&mut self) {
        // `return v` inside a loop: `SWAP 2; POP_TOP` (3.12+) or
        // `ROT_TWO; POP_TOP` (3.8-3.11) before the RETURN drops the loop
        // iterator, which the VM keeps below the value but our simulation
        // does not — swallow the pop. Legacy handler preludes reuse the
        // same ops for exception bookkeeping: never no-op inside them.
        if matches!(self.prev_op_at_exec, Some(Op::SWAP) | Some(Op::ROT_TWO))
            && self.legacy_handler.is_none()
            && self.legacy_try.is_none()
        {
            let next_returns = self
                .idx_of
                .get(&self.cur_offset)
                .and_then(|&pi| self.instrs.get(pi + 1))
                .map_or(false, |nx| {
                    matches!(nx.op, Op::RETURN_VALUE | Op::RETURN_CONST)
                });
            if next_returns {
                return;
            }
        }
        // py2 if-statement: the else branch starts with a POP_TOP that
        // discards the cond value we already popped at the JUMP_IF_*
        if self.py2_else_pop_at == Some(self.cur_offset) {
            self.py2_else_pop_at = None;
            return;
        }
        // handler-entry prelude pops (exception bookkeeping we do not model)
        if self.legacy_handler.is_some() && self.in_handler_prelude {
            self.pop();
            return;
        }
        // inside an inline comprehension, POP_TOP is iterator/cleanup
        // bookkeeping (3.13 pairs END_FOR with POP_TOP), never a statement
        if self.inline_comp.is_some() {
            self.pop();
            return;
        }
        // 3.12+ and/or chains: COPY duplicates the value before the cond
        // jump; the POP_TOP right after the jump discards the original.
        if matches!(
            self.prev_op_at_exec,
            Some(Op::POP_JUMP_IF_FALSE)
                | Some(Op::POP_JUMP_IF_TRUE)
                | Some(Op::POP_JUMP_FORWARD_IF_FALSE)
                | Some(Op::POP_JUMP_FORWARD_IF_TRUE)
                | Some(Op::POP_JUMP_BACKWARD_IF_FALSE)
                | Some(Op::POP_JUMP_BACKWARD_IF_TRUE)
                | Some(Op::JUMP_IF_FALSE_OR_POP)
                | Some(Op::JUMP_IF_TRUE_OR_POP)
                | Some(Op::JUMP_IF_FALSE)
                | Some(Op::JUMP_IF_TRUE)
                | Some(Op::TO_BOOL)
                | Some(Op::END_FOR)
        ) {
            self.pop();
            return;
        }
        // py2 chained imports end with POP_TOP of the module marker
        if let Some(Sv::ImportModule { .. }) = self.stack.last() {
            if self.finalize_from_import() {
                return;
            }
        }
        let sv = self.pop();
        match sv {
            Some(Sv::E(e)) => {
                if let Expr::Yield(_) | Expr::YieldFrom(_) = &*e {
                    self.push_stmt(Stmt::Expr(e));
                    return;
                }
                // 2.6 `with ctx:` (no as): the enter result is POP_TOPped
                // right before the with's SETUP_FINALLY — the With block
                // already represents the statement
                if self.version.major == 2 {
                    let is_enter_call = matches!(&*e, Expr::Call { func, .. }
                        if matches!(&**func, Expr::Attribute { attr, .. } if attr == "__enter__"));
                    if is_enter_call {
                        let next_is_with_setup = self
                            .idx_of
                            .get(&self.cur_offset)
                            .and_then(|&pi| self.instrs.get(pi + 1))
                            .map_or(false, |nx| {
                                nx.op == Op::SETUP_FINALLY
                                    && nx.target.map_or(false, |t| {
                                        self.idx_of.get(&t).map_or(false, |&ti| {
                                            self.instrs[ti].op == Op::WITH_CLEANUP
                                        })
                                    })
                            });
                        if next_is_with_setup {
                            return;
                        }
                    }
                }
                // a with-result value discarded: `with ctx:` without as
                if let Expr::Name(n) = &*e {
                    if n == WITH_RESULT_PLACEHOLDER || n == "/*generator*/" {
                        return;
                    }
                }
                self.push_stmt(Stmt::Expr(e));
            }
            Some(Sv::ImportModule { module, level, fromlist }) => {
                if !self.import_names.is_empty() {
                    // `from module import a, b` finished
                    let names = std::mem::take(&mut self.import_names);
                    self.import_module = None;
                    self.push_stmt(Stmt::ImportFrom { module, level, names });
                } else if fromlist.is_none() {
                    self.push_stmt(Stmt::Import {
                        names: vec![(module, None)],
                    });
                } else {
                    let _ = fromlist;
                }
            }
            Some(Sv::ImportFrom { .. }) => {
                // leftover single from-import name (import without store?)
                self.finalize_from_import();
            }
            Some(Sv::Null) => {}
            None => {}
        }
    }

    /// Fold consecutive ImportFrom markers on the stack into one
    /// `from module import a, b` statement. Returns true when handled.
    fn finalize_from_import(&mut self) -> bool {
        // count trailing ImportFrom markers with the same module
        let n = self.stack.len();
        let mut count = 0usize;
        let mut module: Option<(u32, String)> = None;
        while count < n {
            match &self.stack[n - 1 - count] {
                Sv::ImportFrom { level, module: m, .. } => {
                    let key = (*level, m.clone());
                    match &module {
                        None => module = Some(key),
                        Some(k) if *k == key => {}
                        _ => break,
                    }
                    count += 1;
                }
                Sv::ImportModule { level, module: m, .. } if count > 0 => {
                    let key = (*level, m.clone());
                    if module.as_ref() == Some(&key) {
                        // consume the module marker too
                        count += 1;
                        let drain = self.stack.split_off(n - count);
                        let names: Vec<(String, Option<String>)> = drain
                            .into_iter()
                            .filter_map(|sv| match sv {
                                Sv::ImportFrom { name, .. } => Some((name, None)),
                                _ => None,
                            })
                            .collect();
                        let (level, module) = module.unwrap();
                        self.push_stmt(Stmt::ImportFrom {
                            module,
                            level,
                            names,
                        });
                        return true;
                    }
                    break;
                }
                _ => break,
            }
        }
        false
    }

    /// Pop a raw stack value for STORE_* instructions so that import
    /// markers are handled without going through pop_expr.
    fn pop_store_value(&mut self) -> Sv {
        loop {
            match self.stack.pop() {
                Some(Sv::Null) => continue,
                Some(other) => return other,
                None => {
                    // inside legacy handler preludes the VM stack carries
                    // phantom exception values we do not model; an empty
                    // simulation stack there is not an error
                    if self.legacy_handler.is_none() {
                        self.clean = false;
                    }
                    return Sv::E(Rc::new(Expr::Const(Rc::new(PyObject::None))));
                }
            }
        }
    }

    /// Store routing that understands import markers.
    fn emit_store_sv(&mut self, target: ExprRef, sv: Sv) {
        if matches!(sv, Sv::ImportFrom { .. } | Sv::ImportModule { .. }) {
            // an import store is not the handler's `as` name
            self.legacy_handler_name_store = false;
        }
        match sv {
            Sv::E(val) => self.emit_store(target, val),
            Sv::ImportFrom { level, module, name } => {
                let asname = match &*target {
                    Expr::Name(t) if *t != name => Some(t.clone()),
                    _ => None,
                };
                self.import_names.push((name, asname));
                match &self.import_module {
                    Some((l, m)) if *l == level && *m == module => {}
                    _ => self.import_module = Some((level, module)),
                }
                if !matches!(self.stack.last(), Some(Sv::ImportFrom { .. })) {
                    self.flush_import();
                }
            }
            Sv::ImportModule { module, fromlist, .. } => {
                if let Some(fromlist_e) = fromlist {
                    // from module import *  stored to a name? (py2 star)
                    let names = match &*fromlist_e {
                        Expr::Const(o) => match &**o {
                            PyObject::Tuple(items) => items
                                .iter()
                                .filter_map(|it| match &**it {
                                    PyObject::Str(s) => Some((s.clone(), None)),
                                    _ => None,
                                })
                                .collect(),
                            _ => Vec::new(),
                        },
                        _ => Vec::new(),
                    };
                    if names.len() == 1 {
                        let asname = match &*target {
                            Expr::Name(t) if *t != names[0].0 => Some(t.clone()),
                            _ => None,
                        };
                        self.push_stmt(Stmt::ImportFrom {
                            module,
                            level: 0,
                            names: vec![(names[0].0.clone(), asname)],
                        });
                        return;
                    }
                    self.push_stmt(Stmt::ImportFrom {
                        module,
                        level: 0,
                        names,
                    });
                } else {
                    // `import a.b` binds the top module (STORE a);
                    // `import a.b as c` stores c
                    let asname = match &*target {
                        Expr::Name(t) => {
                            let top = module.split('.').next().unwrap_or(&module);
                            if t.as_str() != top && dotted_last(module.as_str()) != t.as_str() {
                                Some(t.clone())
                            } else if t.as_str() != top {
                                // stored the leaf name for a dotted module:
                                // plain `import a.b` form
                                None
                            } else {
                                None
                            }
                        }
                        _ => None,
                    };
                    self.push_stmt(Stmt::Import {
                        names: vec![(module, asname)],
                    });
                }
            }
            Sv::Null => {
                self.clean = false;
            }
        }
    }

    /// Common path for every store instruction: unpack bookkeeping,
    /// import stores, function/class def detection, else plain assignment.
    fn emit_store(&mut self, target: ExprRef, val: ExprRef) {
        if self.legacy_handler_cleanup {
            self.legacy_handler_cleanup = false;
            return;
        }
        // post-handler `as`-name cleanup: hold `name = None` until the
        // matching `del name` confirms it; anything else flushes it as a
        // real assignment. Inside a handler-body region walk no `del`
        // statement output is wanted — swallow the hold outright (the
        // region ends before the exception-path duplicate anyway).
        if let Expr::Name(n) = &*target {
            if self.pending_as_cleanup.as_deref() == Some(n.as_str())
                && matches!(&*val, Expr::Const(o) if matches!(&**o, PyObject::None))
            {
                if matches!(self.blocks.last().map(|b| b.kind), Some(BlockType::Main))
                    && self.blocks.len() == 1
                {
                    return;
                }
                self.held_cleanup_store = Some((target, val));
                return;
            }
        }
        if self.legacy_handler_name_store {
            self.legacy_handler_name_store = false;
            if matches!(&*target, Expr::Name(_)) {
                if let Some(h) = self.legacy_handler.as_mut() {
                    if h.name.is_none() {
                        h.name = Some(target);
                        return;
                    }
                }
            }
            // not a valid as-name (attribute/subscript store): fall through
            // and emit it as a normal assignment
        }
        // post-comprehension restore of a cleared outer variable
        if let Expr::Name(n) = &*target {
            if let Some(pos) = self.pending_restore_vars.iter().position(|v| v == n) {
                self.pending_restore_vars.remove(pos);
                return;
            }
        }
        // inline comprehension: the first store after each FOR_ITER is the
        // loop target; later stores of cleared variables are the post-loop
        // restores (not statements)
        if let Some(comp) = &mut self.inline_comp {
            if !comp.target_seen && self.unpack_frames.is_empty() {
                if let Some(cur) = &mut comp.cur {
                    cur.target = Some(target);
                }
                comp.target_seen = true;
                self.awaiting_for_target = false;
                return;
            }
            // post-loop restore swallow: only when no unpack frame is
            // collecting — an in-loop tuple-target store (`for k, v in`)
            // also hits a cleared var but must complete the frame
            if self.unpack_frames.is_empty() {
                if let Expr::Name(n) = &*target {
                    if comp.cleared_vars.contains(n) {
                        return;
                    }
                }
            }
        }
        // FOR_ITER just executed: this store is the loop target (unless a
        // tuple target is being unpacked, handled at frame completion)
        if self.awaiting_for_target && self.unpack_frames.is_empty() {
            self.awaiting_for_target = false;
            if let Some(top) = self.blocks.last_mut() {
                if matches!(top.kind, BlockType::For) {
                    // value is the iterator expression itself (we pushed it
                    // back in handle_for_iter); don't emit an assignment
                    top.target = Some(target);
                    return;
                }
            }
        }
        // `with ctx as target:` — the stored value is the __enter__ result
        if let Expr::Name(n) = &*val {
            if n == WITH_RESULT_PLACEHOLDER {
                for blk in self.blocks.iter_mut().rev() {
                    if blk.kind == BlockType::With {
                        if let Some(item) = blk.with_item.as_mut() {
                            item.target = Some(target);
                            return;
                        }
                    }
                }
                if let Some(items) = self.pending_with.last_mut() {
                    if let Some(item) = items.last_mut() {
                        item.target = Some(target);
                        return;
                    }
                }
            }
        }
        // drop stale exhausted frames (stores rerouted elsewhere)
        while matches!(self.unpack_frames.last(), Some((0, _, _, _))) {
            self.unpack_frames.pop();
            self.unpack_targets.0.pop();
        }
        if let Some(frame) = self.unpack_frames.last_mut() {
            frame.0 -= 1;
            let done = frame.0 == 0;
            let (count, star_at) = (frame.1, frame.2);
            let index = count - 1 - frame.0;
            let starred = star_at == Some(index);
            if let Some(targets) = self.unpack_targets.0.last_mut() {
                targets.push((target, starred));
            }
            if done {
                let (_, _, _, value) = self.unpack_frames.pop().unwrap();
                let targets = self.unpack_targets.0.pop().unwrap();
                let tuple: ExprRef = Rc::new(Expr::Tuple(
                    targets
                        .into_iter()
                        .map(|(t, star)| {
                            if star {
                                Rc::new(Expr::Starred(t))
                            } else {
                                t
                            }
                        })
                        .collect(),
                ));
                if self.unpack_frames.is_empty() {
                    self.assign_or_for_target(tuple, value);
                } else {
                    // nested: the completed tuple is the parent's next target
                    let parent = self.unpack_frames.last_mut().unwrap();
                    parent.0 -= 1;
                    let pdone = parent.0 == 0;
                    let (pcount, pstar) = (parent.1, parent.2);
                    let pindex = pcount - 1 - parent.0;
                    let pstarred = pstar == Some(pindex);
                    if let Some(targets) = self.unpack_targets.0.last_mut() {
                        targets.push((tuple, pstarred));
                    }
                    if pdone {
                        let (_, _, _, pvalue) = self.unpack_frames.pop().unwrap();
                        let ptargets = self.unpack_targets.0.pop().unwrap();
                        let ptuple: ExprRef = Rc::new(Expr::Tuple(
                            ptargets
                                .into_iter()
                                .map(|(t, star)| {
                                    if star {
                                        Rc::new(Expr::Starred(t))
                                    } else {
                                        t
                                    }
                                })
                                .collect(),
                        ));
                        self.assign_or_for_target(ptuple, pvalue);
                    }
                }
            }
            return;
        }
        self.emit_assign_single(target, val);
    }

    /// Route a completed (possibly tuple) store: either it is the target of
    /// the for loop we just opened, or a normal assignment.
    fn assign_or_for_target(&mut self, target: ExprRef, value: ExprRef) {
        if self.awaiting_for_target {
            self.awaiting_for_target = false;
            if let Some(top) = self.blocks.last_mut() {
                if matches!(top.kind, BlockType::For) {
                    top.target = Some(target);
                    return;
                }
            }
        }
        // inline comprehension whose loop target was an unpacked tuple
        if let Some(comp) = &mut self.inline_comp {
            if !comp.target_seen {
                if let Some(cur) = &mut comp.cur {
                    cur.target = Some(target);
                }
                comp.target_seen = true;
                return;
            }
        }
        self.emit_assign_single(target, value);
    }

    fn emit_assign_single(&mut self, target: ExprRef, val: ExprRef) {
        // py2 class creation: BUILD_CLASS result stored to a name
        if self.pending_py2_class.is_some() {
            if let (Some((name_e, bases_e, methods)), Expr::Name(cname)) =
                (self.pending_py2_class.take(), &*target)
            {
                let _ = name_e;
                let bases = match &*bases_e {
                    Expr::Tuple(v) => v.clone(),
                    // py2 `class X:` pushes the empty bases as a CONST tuple
                    Expr::Const(o) => match &**o {
                        PyObject::Tuple(items) => items
                            .iter()
                            .map(|i| Rc::new(Expr::Const(i.clone())) as ExprRef)
                            .collect(),
                        _ => vec![bases_e.clone()],
                    },
                    other => vec![Rc::new(other.clone())],
                };
                // the class body is the MAKE_FUNCTION'd code object that
                // CALL_FUNCTION executed into the namespace dict (`methods`),
                // not the stored BUILD_CLASS result; py2 stores it either as
                // a bare Function or as the zero-arg Call of that Function
                let extract_code = |e: &ExprRef| -> Option<Rc<CodeObject>> {
                    match &**e {
                        Expr::Function(fd) => Some(fd.code.clone()),
                        Expr::Call { func, args, keywords, .. }
                            if args.is_empty() && keywords.is_empty() =>
                        {
                            match &**func {
                                Expr::Function(fd) => Some(fd.code.clone()),
                                _ => None,
                            }
                        }
                        _ => None,
                    }
                };
                let body_src = extract_code(&methods).or_else(|| extract_code(&val));
                let mut body = match body_src {
                    Some(code) => self
                        .decompile_class_body(&code, cname)
                        .unwrap_or_else(|| vec![Stmt::Pass]),
                    None => vec![Stmt::Pass],
                };
                // py2 class bodies end with `return locals()` (the namespace
                // the CALL_FUNCTION consumed) — not real source
                while matches!(
                    body.last(),
                    Some(Stmt::Return(Some(e)))
                        if matches!(&**e, Expr::Name(n) if n == "locals()")
                ) {
                    body.pop();
                }
                if body.is_empty() {
                    body.push(Stmt::Pass);
                }
                let decorators = std::mem::take(&mut self.pending_class_decorators);
                self.push_stmt(Stmt::ClassDef {
                    name: cname.clone(),
                    bases,
                    keywords: Vec::new(),
                    star_args: None,
                    star_kwargs: None,
                    decorators,
                    body,
                });
                return;
            }
        }
        // augmented assignment: `x += 1` compiled to a binary op whose LHS is
        // the target, followed by a store back into the same target
        if let Some((aug_target, op)) = self.pending_aug.take() {
            if expr_eq(&aug_target, &target) {
                if let Expr::Binary { right, .. } = &*val {
                    self.push_stmt(Stmt::AugAssign {
                        target,
                        op,
                        value: right.clone(),
                    });
                    return;
                }
            } else {
                // stale marker
                self.pending_aug = Some((aug_target, op));
                self.pending_aug = None;
            }
        }
        // function definition
        if let Expr::Function(fd) = &*val {
            if let Expr::Name(fname) = &*target {
                let fd = fd;
                let name = fname.clone();
                let mut body = self
                    .decompile_function(&fd.code)
                    .unwrap_or_else(|| vec![Stmt::Pass]);
                let mut fd2 = (**fd).clone();
                fd2.name = name;
                fd2.returns = fd2.params.returns_annotation.take();
                fd2.is_async = fd2.code.is_coroutine() || fd2.code.is_async_generator();
                fold_py2_tuple_params(&mut fd2.params, &fd.code.varnames, &mut body);
                let fdef = Rc::new(fd2);
                self.push_stmt(Stmt::FuncDef(fdef, body));
                return;
            }
        }
        // decorated class (3.11+): the stored value is deco(build_class(...))
        let mut class_decorators: Vec<ExprRef> = Vec::new();
        let mut val = val;
        loop {
            let peeled = match &*val {
                Expr::Call { func, args, keywords, star_args: None, star_kwargs: None }
                    if args.len() == 1 && keywords.is_empty() =>
                {
                    match &*args[0] {
                        Expr::Call { func: f2, .. }
                            if matches!(&**f2, Expr::Name(n) if n == "__build_class__") =>
                        {
                            Some((func.clone(), args[0].clone()))
                        }
                        _ => None,
                    }
                }
                _ => None,
            };
            match peeled {
                Some((deco, inner)) => {
                    class_decorators.push(deco);
                    val = inner;
                }
                None => break,
            }
        }
        // class definition (py3): __build_class__ call result stored
        if let Expr::Call { func, args, keywords, .. } = &*val {
            if let Expr::Name(fn_name) = &**func {
                if fn_name == "__build_class__" {
                    if let Expr::Name(cname) = &*target {
                        if args.len() >= 2 {
                            let func_e = args[0].clone();
                            let name_e = args[1].clone();
                            let bases = args[2..].to_vec();
                            let kws: Vec<(Option<String>, ExprRef)> =
                                keywords.iter().cloned().collect();
                            if let Expr::Function(fd) = &*func_e {
                                let class_name = match &*name_e {
                                    Expr::Const(o) => match &**o {
                                        PyObject::Str(s) => s.clone(),
                                        _ => cname.clone(),
                                    },
                                    _ => cname.clone(),
                                };
                                let body = self
                                    .decompile_class_body(&fd.code, &class_name)
                                    .unwrap_or_else(|| vec![Stmt::Pass]);
                                let mut star_args = None;
                                let mut star_kwargs = None;
                                let mut real_bases = Vec::new();
                                let mut real_kws = Vec::new();
                                for b in bases {
                                    match &*b {
                                        Expr::Starred(e) => {
                                            if star_args.is_none() {
                                                star_args = Some(e.clone());
                                            } else {
                                                star_kwargs = Some(e.clone());
                                            }
                                        }
                                        other => real_bases.push(Rc::new(other.clone())),
                                    }
                                }
                                for (k, v) in kws {
                                    match k {
                                        Some(kn) => real_kws.push((Some(kn), v)),
                                        None => match &*v {
                                            Expr::Starred(e) => star_kwargs = Some(e.clone()),
                                            _ => real_kws.push((None, v)),
                                        },
                                    }
                                }
                                let mut decorators = class_decorators;
                                decorators
                                    .extend(std::mem::take(&mut self.pending_class_decorators));
                                self.push_stmt(Stmt::ClassDef {
                                    name: class_name,
                                    bases: real_bases,
                                    keywords: real_kws,
                                    star_args,
                                    star_kwargs,
                                    decorators,
                                    body,
                                });
                                return;
                            }
                        }
                    }
                }
            }
        }
        // plain assignment — may be part of a same-line store group
        // (`a, b = b, a` or `a = b = expr`)
        let same_group = self.last_store_line == self.cur_line && self.cur_line.is_some();
        if !same_group {
            self.flush_pending_stores();
            self.group_start = self.cur_offset;
        }
        self.last_store_line = self.cur_line;
        self.pending_stores.push((target, val));
    }

    fn flush_import(&mut self) {
        let module = self.import_module.take();
        if !self.import_names.is_empty() {
            if let Some((level, module)) = module {
                let names = std::mem::take(&mut self.import_names);
                self.push_stmt(Stmt::ImportFrom { module, level, names });
                return;
            }
        }
        self.import_names.clear();
    }

    fn emit_delete(&mut self, target: ExprRef) {
        if self.legacy_handler_cleanup {
            self.legacy_handler_cleanup = false;
            return;
        }
        if let Expr::Name(n) = &*target {
            if self.pending_as_cleanup.as_deref() == Some(n.as_str()) {
                self.pending_as_cleanup = None;
                self.held_cleanup_store = None;
                return;
            }
        }
        // drop stale exhausted frames (stores rerouted elsewhere)
        while matches!(self.unpack_frames.last(), Some((0, _, _, _))) {
            self.unpack_frames.pop();
            self.unpack_targets.0.pop();
        }
        if let Some(frame) = self.unpack_frames.last_mut() {
            frame.0 -= 1;
            let done = frame.0 == 0;
            if let Some(targets) = self.unpack_targets.0.last_mut() {
                targets.push((target, false));
            }
            if done {
                self.unpack_frames.pop();
                let targets = self.unpack_targets.0.pop().unwrap();
                let list: Vec<ExprRef> = targets.into_iter().map(|(t, _)| t).collect();
                self.push_stmt(Stmt::Delete(list));
            }
            return;
        }
        if let Some(last) = self.blocks.last_mut() {
            if let Some(Stmt::Delete(v)) = last.stmts.last_mut() {
                v.push(target);
                return;
            }
        }
        self.push_stmt(Stmt::Delete(vec![target]));
    }

    fn emit_return(&mut self, e: Option<ExprRef>) {
        // 3.8-3.10 function-tail try/finally: the inline finally body ends
        // with LOAD None; RETURN — the epilogue return. Flush the collected
        // try/finally first (the walk ends here), drop the return, and skip
        // the out-of-line finally copy that follows.
        let epilogue_none = match &e {
            None => true,
            Some(v) => matches!(&**v, Expr::Const(o) if matches!(&**o, PyObject::None)),
        };
        if epilogue_none
            && self.legacy_handler.is_none()
            && self.legacy_try.as_ref().map_or(false, |l| {
                l.has_finally
                    && l.else_start
                        .map_or(false, |es| self.cur_offset >= es && self.cur_offset <= l.else_stop)
            })
        {
            let l = self.legacy_try.take().unwrap();
            self.flush_pending_stores();
            self.restore_legacy_nest();
            self.push_stmt(Stmt::Try {
                body: l.body,
                handlers: l.handlers,
                orelse: l.orelse,
                finalbody: l.finalbody,
            });
            self.skip_until = Some(usize::MAX);
            return;
        }
        let value = match e {
            Some(v) => match &*v {
                Expr::Const(o) if matches!(&**o, PyObject::None) => None,
                _ => Some(v),
            },
            None => None,
        };
        // module-level implicit `return None` is synthetic (3.12+ even emits
        // RETURN_CONST None at the end of every top-level branch)
        if value.is_none() && self.code.name == "<module>" {
            // When it terminates an if-branch, it replaces the classic
            // JUMP_FORWARD-over-else: mark the else region as running to
            // the end of the module stream.
            if let Some(top) = self.blocks.last_mut() {
                if matches!(top.kind, BlockType::If) && top.else_end.is_none() {
                    let code_end = self.instrs.last().map(|i| i.end()).unwrap_or(0);
                    top.else_end = Some(code_end);
                }
            }
            return;
        }
        self.push_stmt(Stmt::Return(value));
    }

    fn apply_binary(&mut self, op_text: &str) {
        let rhs = self.pop_expr();
        let lhs = self.pop_expr();
        let op = binop_from_text(op_text);
        self.push(Rc::new(Expr::Binary { op, left: lhs, right: rhs }));
    }

    /// In-place operators: CPython emits DUP + load target + value +
    /// BINARY_OP(+arg>=13 in 3.11 BINARY_OP) + ROT + STORE. We detect the
    /// pending augmented store and emit AugAssign directly.
    fn apply_inplace(&mut self, op_text: &str, raw_arg: u32) {
        let _ = raw_arg;
        let rhs = self.pop_expr();
        let lhs = self.pop_expr();
        let op = binop_from_text(op_text);
        // Look ahead: next instructions should store back into lhs.
        let e: ExprRef = Rc::new(Expr::Binary {
            op,
            left: lhs.clone(),
            right: rhs,
        });
        // The augmented-assign store is recognized in emit_store via the
        // pending_aug flag when the target matches lhs.
        self.pending_aug = Some((lhs, op));
        self.push(e);
    }

    fn call_function_py(
        &mut self,
        argc: usize,
        names_tuple: Option<ExprRef>,
        is_method: bool,
    ) {
        // Python 2 / 3.0-3.5 CALL_FUNCTION: low byte = positional count,
        // high byte = keyword count. 3.6+ CALL_FUNCTION_KW pushes a names
        // tuple and argc counts positional + keyword together.
        let kw_names: Vec<Option<String>> = match &names_tuple {
            Some(e) => match &**e {
                Expr::Const(o) => match &**o {
                    PyObject::Tuple(items) => items
                        .iter()
                        .map(|it| match &**it {
                            PyObject::Str(s) => Some(s.clone()),
                            _ => None,
                        })
                        .collect(),
                    _ => Vec::new(),
                },
                _ => Vec::new(),
            },
            None => Vec::new(),
        };
        let (npos, nkw) = if names_tuple.is_some() {
            (argc.saturating_sub(kw_names.len()), kw_names.len())
        } else if self.version.at_least(3, 6) {
            (argc, 0)
        } else {
            ((argc & 0xFF) as usize, ((argc >> 8) & 0xFF) as usize)
        };
        let args;
        let mut keywords = Vec::new();
        if names_tuple.is_none() && nkw > 0 && !self.version.at_least(3, 6) {
            // pre-3.6 kwargs sit on top as (name_const, value) pairs
            for _ in 0..nkw {
                let v = self.pop_expr();
                let ke = self.pop_expr();
                let k = match &*ke {
                    Expr::Const(o) => match &**o {
                        PyObject::Str(s) => Some(s.clone()),
                        PyObject::Bytes(b) => Some(String::from_utf8_lossy(b).into_owned()),
                        _ => None,
                    },
                    _ => None,
                };
                keywords.push((k, v));
            }
            keywords.reverse();
            args = self.pop_n_exprs(npos);
        } else if nkw > 0 {
            // 3.6+ CALL_FUNCTION_KW: keyword values sit on top (source
            // order), positionals below them
            let vals = self.pop_n_exprs(nkw);
            for (i, v) in vals.into_iter().enumerate() {
                keywords.push((kw_names.get(i).cloned().flatten(), v));
            }
            args = self.pop_n_exprs(npos);
        } else {
            args = self.pop_n_exprs(npos);
        }
        // CALL_METHOD (3.7-3.10): LOAD_METHOD pushed a self/NULL marker
        // above the method; pop it between the args and the callable.
        let marker = if is_method { self.pop() } else { None };
        // <=3.10 async-with inline __aexit__ call: the exit callable was
        // never modeled, so the stack is already empty here — swallow the
        // desugared call without an underflowing pop_callable
        if self.with_exits > 0
            && self.stack.is_empty()
            && keywords.is_empty()
            && star_args_none(&args)
            && args.iter().all(|a| matches!(&**a, Expr::Const(o) if matches!(&**o, PyObject::None)))
        {
            self.with_exits -= 1;
            let next_awaitable = self
                .idx_of
                .get(&self.cur_offset)
                .map_or(false, |&ci| {
                    self.instrs[ci + 1..]
                        .iter()
                        .take(3)
                        .any(|nx| nx.op == Op::GET_AWAITABLE)
                });
            if next_awaitable {
                self.with_exit_await_drop = true;
            }
            return;
        }
        let func = self.pop_callable();
        // normal with exit (<=3.10): __exit__(None, None, None) where the
        // exit callable is not modeled on our stack
        let none_args = star_args_none(&args)
            && args.iter().all(|a| matches!(&**a, Expr::Const(o) if matches!(&**o, PyObject::None)));
        let func_is_exit_slot = matches!(&*func, Expr::Const(o) if matches!(&**o, PyObject::None))
            || matches!(&*func, Expr::Name(n) if n.contains("underflow"));
        if self.with_exits > 0 && keywords.is_empty() && none_args && func_is_exit_slot {
            self.with_exits -= 1;
            // async with (<=3.10): the __aexit__ result is awaited right
            // after the swallowed call — drop that protocol cleanly
            let next_awaitable = self
                .idx_of
                .get(&self.cur_offset)
                .map_or(false, |&ci| {
                    self.instrs[ci + 1..]
                        .iter()
                        .take(3)
                        .any(|nx| nx.op == Op::GET_AWAITABLE)
                });
            if next_awaitable {
                self.with_exit_await_drop = true;
            }
            return;
        }
        // decorator application via CALL_FUNCTION (<=3.10)
        if args.len() == 1 && keywords.is_empty() {
            if let Expr::Function(fd) = &*args[0] {
                let mut fd = (**fd).clone();
                // decorators apply bottom-up; the renderer prints source
                // order (top-down), so each newly applied (outer) decorator
                // goes to the front
                fd.decorators.insert(0, func.clone());
                self.push(Rc::new(Expr::Function(Rc::new(fd))));
                return;
            }
            // py2 decorated class: the decorator call wraps the BUILD_CLASS
            // marker — record it for the pending class and pass the marker
            // through to the store
            if self.pending_py2_class.is_some()
                && matches!(&*args[0], Expr::Name(n) if n == "/*class-object*/")
            {
                self.pending_class_decorators.insert(0, func.clone());
                self.push(args.into_iter().next().unwrap());
                return;
            }
        }
        let call_e: ExprRef = Rc::new(Expr::Call {
            func,
            args,
            keywords,
            star_args: None,
            star_kwargs: None,
        });
        match self.try_make_comprehension(&call_e, marker) {
            Some(comp) => self.push(comp),
            None => self.push(call_e),
        }
    }

    fn call_function_py2_var(&mut self, argc: usize) {
        // py2: CALL_FUNCTION_VAR — starargs on top
        let star = self.pop_expr();
        let (npos, nkw) = (argc & 0xFF, (argc >> 8) & 0xFF);
        let args = self.pop_n_exprs(npos as usize);
        let mut keywords = Vec::new();
        for _ in 0..nkw {
            let v = self.pop_expr();
            let k = self.pop_expr();
            let ks = match &*k {
                Expr::Const(o) => match &**o {
                    PyObject::Str(s) => Some(s.clone()),
                    PyObject::Bytes(b) => Some(String::from_utf8_lossy(b).into_owned()),
                    _ => None,
                },
                _ => None,
            };
            keywords.push((ks, v));
        }
        keywords.reverse();
        let func = self.pop_callable();
        self.push(Rc::new(Expr::Call {
            func,
            args,
            keywords,
            star_args: Some(star),
            star_kwargs: None,
        }));
    }

    fn call_function_py2_varkw(&mut self, argc: usize) {
        let kwargs = self.pop_expr();
        let star = self.pop_expr();
        let (npos, nkw) = (argc & 0xFF, (argc >> 8) & 0xFF);
        let args = self.pop_n_exprs(npos as usize);
        let mut keywords = Vec::new();
        for _ in 0..nkw {
            let v = self.pop_expr();
            let k = self.pop_expr();
            let ks = match &*k {
                Expr::Const(o) => match &**o {
                    PyObject::Str(s) => Some(s.clone()),
                    PyObject::Bytes(b) => Some(String::from_utf8_lossy(b).into_owned()),
                    _ => None,
                },
                _ => None,
            };
            keywords.push((ks, v));
        }
        keywords.reverse();
        let func = self.pop_callable();
        self.push(Rc::new(Expr::Call {
            func,
            args,
            keywords,
            star_args: Some(star),
            star_kwargs: Some(kwargs),
        }));
    }

    /// 3.11+ CALL (and 3.7-3.10 CALL_METHOD share the same pop order):
    /// stack is `[marker, callable, args...]`, so pop args, then the
    /// callable, then the self/NULL marker. The callable expression for a
    /// method is already `Attribute { value: receiver }`, so the marker is
    /// only validated, not consumed into the AST.
    fn call_311(&mut self, argc: usize, _is_method: bool) {
        let args = self.pop_n_exprs(argc);
        // CALL slot layouts differ by callee kind:
        // * plain call:            [NULL, callable, args...]  (PUSH_NULL)
        // * method (LOAD_ATTR/METHOD): [self, callable, args...]
        // * genexpr instantiation: [callable, iterable] with argc==0 —
        //   the iterable sits ABOVE the function and becomes the marker
        // Peek before popping to choose the right order.
        let n = self.stack.len();
        let genexpr_case = n >= 2
            && matches!(&self.stack[n - 1], Sv::E(_))
            && matches!(&self.stack[n - 2], Sv::E(f) if is_comp_callable(f));
        let (callable, marker) = if self.version.at_least(3, 14) || genexpr_case {
            // 3.14+: [callable, self_or_null, args...] — marker pops first.
            // genexpr instantiation (<=3.13): [genfunc, iterable].
            let marker = self.pop_expr_raw();
            let callable = self.pop_expr();
            (callable, marker)
        } else {
            // 3.11-3.13: NULL may sit above the callable (PUSH_NULL after
            // the load, 3.13 style) — a skipped NULL IS the marker, so only
            // pop a second slot when nothing was skipped
            let (callable, skipped_null) = self.pop_expr_skipped();
            let marker = if skipped_null {
                None
            } else {
                self.pop_expr_raw()
            };
            (callable, marker)
        };

        // The callable expression for a method is already
        // Attribute { value: receiver }; the marker is only needed for
        // comprehension detection.
        let func = callable;

        let kw_names = std::mem::take(&mut self.last_kw_names);
        let (pos_args, keywords) = if !kw_names.is_empty() && kw_names.len() <= args.len() {
            // 3.11/3.12 KW_NAMES names the TRAILING k args of the call;
            // the leading ones are positional
            let npos = args.len() - kw_names.len();
            let mut it = args.into_iter();
            let pos: Vec<ExprRef> = it.by_ref().take(npos).collect();
            let kws: Vec<(Option<String>, ExprRef)> =
                it.zip(kw_names.into_iter()).map(|(a, k)| (k, a)).collect();
            (pos, kws)
        } else {
            (args, Vec::new())
        };

        // decorator application: calling with a Function object argument
        // (3.12+ uses CALL 0 with the decorator *below* the function)
        if pos_args.len() == 1 && keywords.is_empty() {
            if let Expr::Function(fd) = &*pos_args[0] {
                let mut fd = (**fd).clone();
                fd.decorators.insert(0, func.clone());
                self.push(Rc::new(Expr::Function(Rc::new(fd))));
                return;
            }
        }
        // 3.12 decorated CLASS: `LOAD deco; ...build_class...; CALL n;
        // CALL 0` leaves the built class as the callable and the decorator
        // in the marker slot; rebuild deco(build_class(...)) so the
        // store-time class recognition can peel the decorator
        if pos_args.is_empty() && keywords.is_empty() {
            if let Expr::Call { func: f2, .. } = &*func {
                if matches!(&**f2, Expr::Name(n) if n == "__build_class__") {
                    if let Some(Sv::E(deco)) = &marker {
                        self.push(Rc::new(Expr::Call {
                            func: deco.clone(),
                            args: vec![func],
                            keywords: Vec::new(),
                            star_args: None,
                            star_kwargs: None,
                        }));
                        return;
                    }
                }
            }
        }
        // comprehension instantiation takes precedence over decorator shapes
        let comp_callable = is_comp_callable(&func);
        if !comp_callable {
            if let Expr::Function(fd) = &*func {
                if pos_args.is_empty() && keywords.is_empty() {
                    if let Some(Sv::E(deco)) = marker.clone() {
                        let mut fd = (**fd).clone();
                        fd.decorators.insert(0, deco);
                        self.push(Rc::new(Expr::Function(Rc::new(fd))));
                        return;
                    }
                }
            }
            // 3.14 decorator shape: marker slot holds the function, callable
            // is the decorator (`deco(func)` via CALL 0)
            if pos_args.is_empty() && keywords.is_empty() {
                if let Some(Sv::E(m)) = &marker {
                    if let Expr::Function(fd) = &**m {
                        let mut fd = (**fd).clone();
                        fd.decorators.insert(0, func.clone());
                        self.push(Rc::new(Expr::Function(Rc::new(fd))));
                        return;
                    }
                    // decorated class via CALL 0: the built class sits in
                    // the marker slot — rebuild deco(build_class(...))
                    if let Expr::Call { func: f2, .. } = &**m {
                        if matches!(&**f2, Expr::Name(n) if n == "__build_class__") {
                            self.push(Rc::new(Expr::Call {
                                func,
                                args: vec![m.clone()],
                                keywords: Vec::new(),
                                star_args: None,
                                star_kwargs: None,
                            }));
                            return;
                        }
                    }
                }
            }
        }

        // normal with exit: the compiler calls the stored __exit__ with
        // (None, None, None); our model does not keep __exit__ on the stack,
        // so recognize and swallow the call
        let none_args =
            pos_args.iter().all(|a| matches!(&**a, Expr::Const(o) if matches!(&**o, PyObject::None)));
        let func_is_none = matches!(&*func, Expr::Const(o) if matches!(&**o, PyObject::None));
        let func_is_underflow =
            matches!(&*func, Expr::Name(n) if n.contains("underflow"));
        let marker_is_none_slot = match &marker {
            None | Some(Sv::Null) => true,
            Some(Sv::E(m)) => matches!(&**m, Expr::Const(o) if matches!(&**o, PyObject::None)),
            Some(_) => false,
        };
        if self.with_exits > 0
            && keywords.is_empty()
            && marker_is_none_slot
            && none_args
            && (func_is_none || func_is_underflow)
        {
            self.with_exits -= 1;
            // async with (3.11+): the __aexit__ result is awaited right
            // after the swallowed call — the protocol has no awaitable on
            // our modeled stack, so drop it cleanly (no underflow)
            let next_awaitable = self
                .idx_of
                .get(&self.cur_offset)
                .map_or(false, |&ci| {
                    self.instrs[ci + 1..]
                        .iter()
                        .take(3)
                        .any(|nx| nx.op == Op::GET_AWAITABLE)
                });
            if next_awaitable {
                self.with_exit_await_drop = true;
            }
            return;
        }

        let call_e: ExprRef = Rc::new(Expr::Call {
            func,
            args: pos_args,
            keywords,
            star_args: None,
            star_kwargs: None,
        });
        match self.try_make_comprehension(&call_e, marker) {
            Some(comp) => self.push(comp),
            None => self.push(call_e),
        }
    }

    /// Pop the callable for py2-style CALL_FUNCTION, skipping a NULL marker.
    fn pop_callable(&mut self) -> ExprRef {
        self.pop_expr()
    }

    fn make_function(&mut self, inst: &Instruction, flags: u32) {
        // Stack layout by era:
        //  py2-3.2: [defaults..., code] (MAKE_CLOSURE inserts closure tuple
        //           below code)
        //  3.3-3.10: [..., code, qualname] — qualname on top (PEP 3155)
        //  3.11+: qualname lives in the code object; code on top
        let code_e = if self.version.at_least(3, 3) && !self.version.at_least(3, 11) {
            let qualname = self.pop_expr();
            let _ = qualname;
            self.pop_expr()
        } else {
            self.pop_expr()
        };
        let code_obj = match &*code_e {
            Expr::Const(o) => match &**o {
                PyObject::Code(c) => c.clone(),
                _ => {
                    self.mark_unclean();
                    return;
                }
            },
            _ => {
                self.mark_unclean();
                return;
            }
        };

        let params;
        let returns: Option<ExprRef> = None;

        if self.version.at_least(3, 6) {
            // flags in argument order on stack: annotations(3.6-3.12),
            // kwdefaults, defaults, closure — pushed as:
            // stack bottom..top: [closure?, defaults?, kwdefaults?, annotations?, qualname, code]
            // MAKE_FUNCTION pops code, qualname, then per flags.
            let mut defaults_t: Option<ExprRef> = None;
            let mut kwdefaults_d: Option<ExprRef> = None;
            let mut ann: Option<ExprRef> = None;
            let mut _closure: Option<ExprRef> = None;

            let has_ann = if self.version.at_least(3, 13) {
                false // annotations arrive via SET_FUNCTION_ATTRIBUTE
            } else {
                flags & 0x04 != 0
            };
            if flags & 0x08 != 0 {
                _closure = Some(self.pop_expr());
            }
            if has_ann {
                ann = Some(self.pop_expr());
            }
            if flags & 0x02 != 0 {
                kwdefaults_d = Some(self.pop_expr());
            }
            if flags & 0x01 != 0 {
                defaults_t = Some(self.pop_expr());
            }

            params = self.build_params(&code_obj, defaults_t, kwdefaults_d, ann);
            if self.version.at_least(3, 13) && flags & 0x04 != 0 {
                // 3.13: 0x04 = closure? no: 3.13 flags: 0x01 defaults,
                // 0x02 kwdefaults, 0x04 annotations? handled above
            }
        } else {
            // <= 3.5: defaults are individual stack values; MAKE_CLOSURE
            // (py2.1+/3.3-3.5) pushes the closure tuple ABOVE the defaults:
            // [defaults..., closure, code, qualname]
            // <=3.5: MAKE_FUNCTION arg = number of defaults on the stack
            let ndefaults = flags as usize;
            if inst.op == Op::MAKE_CLOSURE {
                let _closure = self.pop_expr();
            }
            let mut defaults = Vec::new();
            for _ in 0..ndefaults {
                defaults.push(self.pop_expr());
            }
            defaults.reverse();
            params = self.build_params_legacy(&code_obj, defaults);
        }

        // decorators: 2.6-3.5 applied via MAKE_FUNCTION wrapper calls;
        // 3.x modern: decorators are call wrappers around the function.
        let decorators = std::mem::take(&mut self.pending_decorators);

        let is_lambda = code_obj.name == "<lambda>";
        let is_async = code_obj.is_coroutine() || code_obj.is_async_generator();
        let fdef = Rc::new(FunctionDef {
            name: code_obj.name.clone(),
            code: code_obj,
            params,
            decorators,
            returns,
            is_async,
        });
        if is_lambda {
            // body: single return expression — extract from the lambda code
            let body = self.lambda_body(&fdef.code);
            self.push(Rc::new(Expr::Lambda {
                params: Box::new(fdef.params.clone()),
                body,
            }));
        } else {
            self.push(Rc::new(Expr::Function(fdef)));
        }
    }

    fn build_params(
        &mut self,
        code: &Rc<CodeObject>,
        defaults_t: Option<ExprRef>,
        kwdefaults_d: Option<ExprRef>,
        ann: Option<ExprRef>,
    ) -> Parameters {
        let argcount = code.arg_count as usize;
        let posonly = code.posonly_arg_count as usize;
        let kwonly = code.kwonly_arg_count as usize;
        let varargs = code.has_varargs();
        let varkw = code.has_varkeywords();

        // localsplus/varnames: positional args first, then kwonly, then
        // *args/**kwargs (3.11+ varnames already excludes non-LOCAL entries)
        let all_names: Vec<String> = code.varnames.clone();

        let defaults: Vec<ExprRef> = match &defaults_t {
            Some(e) => match &**e {
                Expr::Const(o) => match &**o {
                    PyObject::Tuple(items) => items
                        .iter()
                        .map(|i| Rc::new(Expr::Const(i.clone())) as ExprRef)
                        .collect(),
                    _ => Vec::new(),
                },
                Expr::Tuple(items) => items.clone(),
                other => vec![Rc::new(other.clone())],
            },
            None => Vec::new(),
        };

        // annotations (3.6-3.12): dict const or BUILD map on stack
        let mut ann_map: HashMap<String, ExprRef> = HashMap::new();
        let mut ret_ann: Option<ExprRef> = None;
        if let Some(a) = ann {
            match &*a {
                Expr::Const(o) => match &**o {
                    PyObject::Tuple(items)
                        if items.len() >= 2
                            && items.len() % 2 == 0
                            && items.iter().step_by(2).all(|it| matches!(&**it, PyObject::Str(_)))
                            && self.version.at_least(3, 12) =>
                    {
                        // 3.12+: flat (name, value, name, value, ...) pairs
                        for pair in items.chunks(2) {
                            if let PyObject::Str(name) = &*pair[0] {
                                let v: ExprRef = Rc::new(Expr::Const(pair[1].clone()));
                                if name == "return" {
                                    ret_ann = Some(v);
                                } else {
                                    ann_map.insert(name.clone(), v);
                                }
                            }
                        }
                    }
                    PyObject::Tuple(items) if items.len() == 2 => {
                        // 3.10+: (names_tuple, values_tuple)
                        let names: Vec<String> = match &*items[0] {
                            PyObject::Tuple(ns) => ns
                                .iter()
                                .filter_map(|n| match &**n {
                                    PyObject::Str(s) => Some(s.clone()),
                                    _ => None,
                                })
                                .collect(),
                            _ => Vec::new(),
                        };
                        let values: Vec<ExprRef> = match &*items[1] {
                            PyObject::Tuple(vs) => vs
                                .iter()
                                .map(|v| Rc::new(Expr::Const(v.clone())) as ExprRef)
                                .collect(),
                            _ => Vec::new(),
                        };
                        for (n, v) in names.into_iter().zip(values) {
                            if n == "return" {
                                ret_ann = Some(v);
                            } else {
                                ann_map.insert(n, v);
                            }
                        }
                    }
                    PyObject::Dict(entries) => {
                        for (k, v) in entries {
                            if let PyObject::Str(ks) = &**k {
                                if ks == "return" {
                                    ret_ann = Some(Rc::new(Expr::Const(v.clone())));
                                } else {
                                    ann_map
                                        .insert(ks.clone(), Rc::new(Expr::Const(v.clone())));
                                }
                            }
                        }
                    }
                    _ => {}
                },
                Expr::Dict(entries) => {
                    for (k, v) in entries {
                        if let Expr::Const(o) = &**k {
                            if let PyObject::Str(ks) = &**o {
                                if ks == "return" {
                                    ret_ann = Some(v.clone());
                                } else {
                                    ann_map.insert(ks.clone(), v.clone());
                                }
                            }
                        }
                    }
                }
                Expr::Tuple(items)
                    if items.len() >= 2
                        && items.len() % 2 == 0
                        && items
                            .iter()
                            .step_by(2)
                            .all(|it| matches!(&**it, Expr::Const(o) if matches!(&**o, PyObject::Str(_)))) =>
                {
                    // runtime-built flat (name, value, ...) pairs (3.10+)
                    for pair in items.chunks(2) {
                        if let Expr::Const(o) = &*pair[0] {
                            if let PyObject::Str(name) = &**o {
                                if name == "return" {
                                    ret_ann = Some(pair[1].clone());
                                } else {
                                    ann_map.insert(name.clone(), pair[1].clone());
                                }
                            }
                        }
                    }
                }
                Expr::Tuple(items) if items.len() == 2 => {
                    // 3.10 style (names_tuple_const, values_tuple_const)
                    let names: Vec<String> = match &*items[0] {
                        Expr::Const(o) => match &**o {
                            PyObject::Tuple(ns) => ns
                                .iter()
                                .filter_map(|n| match &**n {
                                    PyObject::Str(s) => Some(s.clone()),
                                    _ => None,
                                })
                                .collect(),
                            _ => Vec::new(),
                        },
                        _ => Vec::new(),
                    };
                    let values: Vec<ExprRef> = match &*items[1] {
                        Expr::Const(o) => match &**o {
                            PyObject::Tuple(vs) => vs
                                .iter()
                                .map(|v| Rc::new(Expr::Const(v.clone())) as ExprRef)
                                .collect(),
                            _ => Vec::new(),
                        },
                        _ => Vec::new(),
                    };
                    for (n, v) in names.into_iter().zip(values) {
                        if n == "return" {
                            ret_ann = Some(v);
                        } else {
                            ann_map.insert(n, v);
                        }
                    }
                }
                _ => {}
            }
        }

        let kw_defaults_map: HashMap<String, ExprRef> = match &kwdefaults_d {
            Some(e) => match &**e {
                Expr::Const(o) => match &**o {
                    PyObject::Dict(entries) => entries
                        .iter()
                        .filter_map(|(k, v)| match &**k {
                            PyObject::Str(ks) => Some((ks.clone(), Rc::new(Expr::Const(v.clone())) as ExprRef)),
                            _ => None,
                        })
                        .collect(),
                    _ => HashMap::new(),
                },
                Expr::Dict(entries) => entries
                    .iter()
                    .filter_map(|(k, v)| match &**k {
                        Expr::Const(o) => match &**o {
                            PyObject::Str(ks) => Some((ks.clone(), v.clone())),
                            _ => None,
                        },
                        _ => None,
                    })
                    .collect(),
                _ => HashMap::new(),
            },
            None => HashMap::new(),
        };

        let mk_param = |name: &str| Param {
            name: name.to_string(),
            annotation: ann_map.get(name).cloned(),
        };

        let mut params = Parameters::empty();
        params.posonly_count = posonly;
        for n in all_names.iter().take(argcount) {
            params.args.push(mk_param(n));
        }
        let mut idx = argcount;
        for n in all_names.iter().skip(argcount).take(kwonly) {
            let p = Param {
                name: n.clone(),
                annotation: ann_map.get(n).cloned(),
            };
            let d = kw_defaults_map.get(n).cloned();
            params.kwonly.push(p);
            params.kw_defaults.push(d);
            idx += 1;
        }
        if varargs {
            if let Some(n) = all_names.get(idx) {
                params.vararg = Some(mk_param(n));
                idx += 1;
            }
        }
        if varkw {
            if let Some(n) = all_names.get(idx) {
                params.kwarg = Some(mk_param(n));
            }
        }
        params.defaults = defaults;
        params.returns_annotation = ret_ann;
        params
    }

    fn build_params_legacy(&mut self, code: &Rc<CodeObject>, defaults: Vec<ExprRef>) -> Parameters {
        let argcount = code.arg_count as usize;
        let kwonly = code.kwonly_arg_count as usize;
        let varargs = code.has_varargs();
        let varkw = code.has_varkeywords();
        let mut params = Parameters::empty();
        for n in code.varnames.iter().take(argcount) {
            params.args.push(Param {
                name: sanitize_varname(n),
                annotation: None,
            });
        }
        let mut idx = argcount;
        for n in code.varnames.iter().skip(argcount).take(kwonly) {
            params.kwonly.push(Param {
                name: n.clone(),
                annotation: None,
            });
            params.kw_defaults.push(None);
            idx += 1;
        }
        if varargs {
            if let Some(n) = code.varnames.get(idx) {
                params.vararg = Some(Param {
                    name: n.clone(),
                    annotation: None,
                });
                idx += 1;
            }
        }
        if varkw {
            if let Some(n) = code.varnames.get(idx) {
                params.kwarg = Some(Param {
                    name: n.clone(),
                    annotation: None,
                });
            }
        }
        params.defaults = defaults;
        params
    }

    fn set_function_attribute_313(&mut self, flags: u32) {
        // 3.13+: SET_FUNCTION_ATTRIBUTE (func, attr -- func): the function
        // is on TOP, the attribute value below it
        let func_e = self.pop_expr();
        let value = self.pop_expr();
        let mut params_opt: Option<Parameters> = None;
        let mut returns_opt: Option<ExprRef> = None;
        let mut params = match &*func_e {
            Expr::Function(fd) => fd.params.clone(),
            Expr::Lambda { params, .. } => (**params).clone(),
            _ => {
                // not a function we track; restore stack best-effort
                self.push(value);
                self.push(func_e);
                return;
            }
        };
        if flags & 0x10 != 0 {
            // 3.14 PEP 649: value is the __annotate__ function whose body
            // returns the annotations dict
            if let Expr::Function(afd) = &*value {
                if afd.code.name == "__annotate__" {
                    if let Ok(d) = decompile(&afd.code, self.version) {
                        for stmt in &d.body {
                            if let Stmt::Return(Some(e)) = stmt {
                                apply_annotations_313_dictexpr(&mut params, e);
                            }
                        }
                    }
                }
            }
        }
        match flags {
            0x01 => params.defaults = tuple_items(&value),
            0x02 => {
                let map = dict_items(&value);
                params.kw_defaults = params
                    .kwonly
                    .iter()
                    .map(|p| map.iter().find(|(k, _)| k == &p.name).map(|(_, v)| v.clone()))
                    .collect();
            }
            0x04 => apply_annotations_313(&mut params, &value),
            0x08 => returns_opt = Some(value.clone()),
            _ => {}
        }
        let _ = &mut params_opt;
        let out = match &*func_e {
            Expr::Function(fd) => {
                let mut fd = (**fd).clone();
                fd.params = params;
                if let Some(r) = returns_opt {
                    fd.returns = Some(r);
                }
                Rc::new(Expr::Function(Rc::new(fd))) as ExprRef
            }
            Expr::Lambda { body, .. } => Rc::new(Expr::Lambda {
                params: Box::new(params),
                body: body.clone(),
            }),
            _ => func_e.clone(),
        };
        self.push(out);
    }

    fn lambda_body(&mut self, code: &CodeObject) -> ExprRef {
        // lambda code: build expression from the (short) instruction stream
        let inner = decompile(code, self.version);
        match inner {
            Ok(d) => {
                for stmt in &d.body {
                    if let Stmt::Return(Some(e)) = stmt {
                        return e.clone();
                    }
                    if let Stmt::Expr(e) = stmt {
                        return e.clone();
                    }
                }
                // yield lambdas etc.
                for stmt in &d.body {
                    if let Stmt::Return(None) = stmt {
                        return Rc::new(Expr::Const(Rc::new(PyObject::None)));
                    }
                }
                self.mark_unclean();
                self.name_expr("/*lambda?*/")
            }
            Err(_) => {
                self.mark_unclean();
                self.name_expr("/*lambda?*/")
            }
        }
    }

    fn decompile_function(&mut self, code: &Rc<CodeObject>) -> Option<Vec<Stmt>> {
        self.decompile_scoped(code, false)
    }

    /// Decompile a class body: pushes the class name onto the scope so
    /// methods can unmangle `_Class__attr` back to `__attr`.
    fn decompile_class_body(&mut self, code: &Rc<CodeObject>, name: &str) -> Option<Vec<Stmt>> {
        self.class_scope.push(name.to_string());
        let r = self.decompile_scoped(code, true);
        self.class_scope.pop();
        r
    }

    fn decompile_scoped(&mut self, code: &Rc<CodeObject>, scope_self: bool) -> Option<Vec<Stmt>> {
        let scope: Vec<String> = if scope_self {
            let mut v = self.class_scope.clone();
            v.push(code.name.clone());
            v
        } else {
            self.class_scope.clone()
        };
        match decompile_in_scope(code, self.version, &scope) {
            Ok(d) => {
                if !d.clean {
                    self.mark_unclean();
                }
                let mut body = postprocess_body(d.body, code);
                // Function docstrings never appear in bytecode: CPython
                // stores them in consts[0]. Up to 3.13 the compiler always
                // reserves slot 0 (None when there is no docstring), so a
                // leading string const IS the docstring; 3.14 dropped the
                // reserved slot and marks it with CO_HAS_DOCSTRING instead.
                if !scope_self && code.name != "<module>" {
                    let marked = if self.version.at_least(3, 14) {
                        code.flags & 0x0400_0000 != 0
                    } else {
                        true
                    };
                    if marked && !matches!(body.first(), Some(Stmt::Expr(_))) {
                        if let Some(c0) = code.consts.first() {
                            if matches!(&**c0, PyObject::Str(_) | PyObject::Bytes(_)) {
                                body.insert(0, Stmt::Expr(Rc::new(Expr::Const(c0.clone()))));
                            }
                        }
                    }
                }
                Some(body)
            }
            Err(_) => {
                self.mark_unclean();
                None
            }
        }
    }
}

impl<'a> Ctx<'a> {
    fn handle_collection_op(&mut self, inst: &Instruction, arg: u32) {
        match inst.op {
            Op::LIST_EXTEND | Op::SET_UPDATE => {
                let iter = self.pop_expr();
                let coll = self.pop_expr();
                let items = match &*coll {
                    Expr::List(v) => v.clone(),
                    Expr::Set(v) => v.clone(),
                    Expr::Tuple(v) => v.to_vec(),
                    other => vec![Rc::new(other.clone())],
                };
                let mut all = items;
                match &*iter {
                    Expr::Const(o) => match &**o {
                        PyObject::Tuple(t) | PyObject::List(t) | PyObject::FrozenSet(t) => {
                            all.extend(t.iter().map(|c| Rc::new(Expr::Const(c.clone())) as ExprRef));
                        }
                        _ => all.push(iter),
                    },
                    other => all.push(Rc::new(Expr::Starred(Rc::new(other.clone())))),
                }
                let e = match inst.op {
                    Op::LIST_EXTEND => Expr::List(all),
                    _ => Expr::Set(all),
                };
                self.push(Rc::new(e));
            }
            Op::DICT_UPDATE | Op::DICT_MERGE => {
                let other = self.pop_expr();
                let dict = self.pop_expr();
                let mut entries = match &*dict {
                    Expr::Dict(d) => d.clone(),
                    _ => Vec::new(),
                };
                match &*other {
                    Expr::Dict(d) => entries.extend(d.iter().cloned()),
                    o => entries.push((
                        Rc::new(Expr::Starred(Rc::new(o.clone()))),
                        self.name_expr(""),
                    )),
                }
                self.push(Rc::new(Expr::Dict(entries)));
            }
            Op::LIST_APPEND | Op::SET_ADD => {
                let item = self.pop_expr();
                let len = self.stack.len();
                let idx = len.saturating_sub(arg as usize);
                let coll = self
                    .stack
                    .get(idx)
                    .and_then(|sv| match sv {
                        Sv::E(e) => Some(e.clone()),
                        _ => None,
                    })
                    .unwrap_or_else(|| Rc::new(Expr::List(vec![])));
                let mut items = match &*coll {
                    Expr::List(v) => v.clone(),
                    Expr::Set(v) => v.clone(),
                    _ => vec![],
                };
                items.push(item);
                let e = match inst.op {
                    Op::LIST_APPEND => Expr::List(items),
                    _ => Expr::Set(items),
                };
                let new: ExprRef = Rc::new(e);
                if let Some(Sv::E(slot)) = self.stack.get_mut(idx) {
                    *slot = new;
                }
            }
            Op::MAP_ADD => {
                // CPython operand order: 3.8+ pushes key then value
                // (value on top); pre-3.8 (incl. py2.7 dict comps) pushes
                // value then key (key on top)
                let (key, value) = if self.version.at_least(3, 8) {
                    let value = self.pop_expr();
                    let key = self.pop_expr();
                    (key, value)
                } else {
                    let key = self.pop_expr();
                    let value = self.pop_expr();
                    (key, value)
                };
                let len = self.stack.len();
                let idx = len.saturating_sub(arg as usize);
                let coll = self
                    .stack
                    .get(idx)
                    .and_then(|sv| match sv {
                        Sv::E(e) => Some(e.clone()),
                        _ => None,
                    })
                    .unwrap_or_else(|| Rc::new(Expr::Dict(vec![])));
                let mut entries = match &*coll {
                    Expr::Dict(d) => d.clone(),
                    _ => vec![],
                };
                entries.push((key, value));
                let new: ExprRef = Rc::new(Expr::Dict(entries));
                if let Some(Sv::E(slot)) = self.stack.get_mut(idx) {
                    *slot = new;
                }
            }
            Op::LIST_TO_TUPLE => {
                let e = self.pop_expr();
                let items = match &*e {
                    Expr::List(v) => v.clone(),
                    other => vec![Rc::new(other.clone())],
                };
                self.push(Rc::new(Expr::Tuple(items)));
            }
            Op::COPY_DICT_WITHOUT_KEYS => {
                // match/case dict rest binding — not supported yet
                self.mark_unclean();
            }
            _ => self.mark_unclean(),
        }
    }
}

fn tuple_items(e: &ExprRef) -> Vec<ExprRef> {
    match &**e {
        Expr::Const(o) => match &**o {
            PyObject::Tuple(items) => items
                .iter()
                .map(|i| Rc::new(Expr::Const(i.clone())) as ExprRef)
                .collect(),
            _ => Vec::new(),
        },
        Expr::Tuple(items) => items.clone(),
        _ => Vec::new(),
    }
}

fn dict_items(e: &ExprRef) -> Vec<(String, ExprRef)> {
    let mut out = Vec::new();
    match &**e {
        Expr::Const(o) => match &**o {
            PyObject::Dict(entries) => {
                for (k, v) in entries {
                    if let PyObject::Str(ks) = &**k {
                        out.push((ks.clone(), Rc::new(Expr::Const(v.clone())) as ExprRef));
                    }
                }
            }
            _ => {}
        },
        Expr::Dict(entries) => {
            for (k, v) in entries {
                if let Expr::Const(o) = &**k {
                    if let PyObject::Str(ks) = &**o {
                        out.push((ks.clone(), v.clone()));
                    }
                }
            }
        }
        _ => {}
    }
    out
}

/// Apply annotations from a runtime Dict expression (PEP 649 __annotate__).
fn apply_annotations_313_dictexpr(params: &mut Parameters, value: &ExprRef) {
    let Expr::Dict(entries) = &**value else { return };
    for (k, v) in entries {
        let Expr::Const(o) = &**k else { continue };
        let PyObject::Str(name) = &**o else { continue };
        if name == "return" {
            params.returns_annotation = Some(v.clone());
            continue;
        }
        for p in params.args.iter_mut() {
            if p.name == *name {
                p.annotation = Some(v.clone());
            }
        }
        for p in params.kwonly.iter_mut() {
            if p.name == *name {
                p.annotation = Some(v.clone());
            }
        }
        if let Some(p) = params.vararg.as_mut() {
            if p.name == *name {
                p.annotation = Some(v.clone());
            }
        }
        if let Some(p) = params.kwarg.as_mut() {
            if p.name == *name {
                p.annotation = Some(v.clone());
            }
        }
    }
}

fn apply_annotations_313(params: &mut Parameters, value: &ExprRef) {
    // 3.13+: annotations as a flat runtime tuple (name, value, ...) —
    // including the "return" entry
    if let Expr::Tuple(items) = &**value {
        if items.len() >= 2 && items.len() % 2 == 0 {
            let mut handled = true;
            for pair in items.chunks(2) {
                let Expr::Const(o) = &*pair[0] else {
                    handled = false;
                    break;
                };
                let PyObject::Str(name) = &**o else {
                    handled = false;
                    break;
                };
                if name == "return" {
                    params.returns_annotation = Some(pair[1].clone());
                    continue;
                }
                let mut done = false;
                for p in params.args.iter_mut() {
                    if p.name == *name {
                        p.annotation = Some(pair[1].clone());
                        done = true;
                    }
                }
                for p in params.kwonly.iter_mut() {
                    if p.name == *name {
                        p.annotation = Some(pair[1].clone());
                        done = true;
                    }
                }
                if let Some(p) = params.vararg.as_mut() {
                    if p.name == *name {
                        p.annotation = Some(pair[1].clone());
                        done = true;
                    }
                }
                if let Some(p) = params.kwarg.as_mut() {
                    if p.name == *name {
                        p.annotation = Some(pair[1].clone());
                        done = true;
                    }
                }
                let _ = done;
            }
            if handled {
                return;
            }
        }
    }
    // fallback: dict form
    for (name, ann) in dict_items(value) {
        if name == "return" {
            params.returns_annotation = Some(ann);
            continue;
        }
        let mut found = false;
        for p in params.args.iter_mut() {
            if p.name == name {
                p.annotation = Some(ann.clone());
                found = true;
            }
        }
        for p in params.kwonly.iter_mut() {
            if p.name == name {
                p.annotation = Some(ann.clone());
                found = true;
            }
        }
        if let Some(p) = params.vararg.as_mut() {
            if p.name == name {
                p.annotation = Some(ann.clone());
                found = true;
            }
        }
        if let Some(p) = params.kwarg.as_mut() {
            if p.name == name {
                p.annotation = Some(ann.clone());
                found = true;
            }
        }
        let _ = found;
    }
    // tuple form
    if let Expr::Const(o) = &**value {
        if let PyObject::Tuple(items) = &**o {
            if items.len() == 2 {
                if let (PyObject::Tuple(ns), PyObject::Tuple(vs)) = (&*items[0], &*items[1]) {
                    for (n, v) in ns.iter().zip(vs.iter()) {
                        if let PyObject::Str(name) = &**n {
                            let ann: ExprRef = Rc::new(Expr::Const(v.clone()));
                            if name == "return" {
                                params.returns_annotation = Some(ann);
                                continue;
                            }
                            for p in params.args.iter_mut() {
                                if p.name == *name {
                                    p.annotation = Some(ann.clone());
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

fn binop_from_text(op_text: &str) -> BinaryOp {
    match op_text {
        "+" => BinaryOp::Add,
        "-" => BinaryOp::Sub,
        "*" => BinaryOp::Mult,
        "/" => BinaryOp::Div,
        "//" => BinaryOp::FloorDiv,
        "%" => BinaryOp::Mod,
        "**" => BinaryOp::Pow,
        "<<" => BinaryOp::LShift,
        ">>" => BinaryOp::RShift,
        "|" => BinaryOp::BitOr,
        "^" => BinaryOp::BitXor,
        "&" => BinaryOp::BitAnd,
        "@" => BinaryOp::MatMult,
        _ => BinaryOp::Add,
    }
}

fn dotted_last(module: &str) -> &str {
    module.rsplit('.').next().unwrap_or(module)
}

/// py2 names synthetic tuple-parameter locals `.0`, `.1`, ...; these are
/// not valid identifiers — rename to `_0`, `_1` when they leak through
/// without being folded back into `(a, b)` signature form.
fn sanitize_varname(n: &str) -> String {
    if n.starts_with('.') {
        n.replace('.', "_")
    } else {
        n.to_string()
    }
}

/// Render an unpack target as py2 tuple-parameter text: `(a, b)`.
fn tuple_param_text(e: &ExprRef) -> Option<String> {
    match &**e {
        Expr::Name(n) => Some(n.clone()),
        Expr::Tuple(items) => {
            let mut parts = Vec::new();
            for it in items {
                parts.push(tuple_param_text(it)?);
            }
            Some(format!("({})", parts.join(", ")))
        }
        _ => None,
    }
}

/// py2 `def f((a, b))`: the compiler creates a synthetic `.N` parameter
/// and emits the unpack `a, b = _N` at the body's head. Fold the unpacks
/// back into the signature (valid py2 tuple-param syntax) and drop the
/// statements. `varnames` are the code object's raw locals (params were
/// already sanitized to `_N`).
fn fold_py2_tuple_params(params: &mut Parameters, varnames: &[String], body: &mut Vec<Stmt>) {
    for (pi, p) in params.args.iter_mut().enumerate() {
        if !varnames.get(pi).map_or(false, |n| n.starts_with('.')) {
            continue;
        }
        let san = sanitize_varname(varnames.get(pi).map(|s| s.as_str()).unwrap_or(""));
        let mut found = None;
        for (bi, stmt) in body.iter().enumerate().take(8) {
            if let Stmt::Assign { targets, value } = stmt {
                if targets.len() == 1 && matches!(&**value, Expr::Name(n) if *n == san) {
                    if let Some(text) = tuple_param_text(&targets[0]) {
                        found = Some((bi, text));
                        break;
                    }
                }
            }
        }
        if let Some((bi, text)) = found {
            p.name = text;
            body.remove(bi);
        }
    }
}

/// Cleanup applied to a decompiled function/module body:
/// * drop synthetic `__qualname__` / `__module__` assignments (class bodies)
/// * convert leading `__doc__ = 'x'` assignments into docstring statements
/// * drop a trailing `return None` in function bodies
fn postprocess_body(mut body: Vec<Stmt>, code: &CodeObject) -> Vec<Stmt> {
    // __module__ / __qualname__ / __doc__ handling for class bodies
    let mut idx = 0;
    while idx < body.len() {
        let mut remove = false;
        if let Stmt::Assign { targets, value } = &body[idx] {
            if targets.len() == 1 {
                if let Expr::Name(n) = &*targets[0] {
                    if n == "__module__" {
                        if let Expr::Name(_) | Expr::Const(_) = &**value {
                            remove = true;
                        }
                    } else if n == "__qualname__" {
                        if let Expr::Const(_) = &**value {
                            remove = true;
                        }
                    } else if n == "__classcell__"
                        || n == "__classdictcell__"
                        || n == "__classdict__"
                        || n == "__firstlineno__"
                        || n == "__static_attributes__"
                    {
                        remove = true;
                    } else if n == "__doc__" {
                        if let Expr::Const(o) = &**value {
                            if matches!(&**o, PyObject::Str(_) | PyObject::Bytes(_) | PyObject::None) {
                                // rewrite as docstring const expr
                                body[idx] = Stmt::Expr(Rc::new(Expr::Const(o.clone())));
                            }
                        }
                    }
                }
            }
        }
        if remove {
            body.remove(idx);
        } else {
            idx += 1;
        }
    }
    // 3.11+ emits the finally body twice (inline sunk flow + handler);
    // the walk renders the sunk copy right after the Try — drop statements
    // immediately following a Try that mirror its finalbody exactly
    {
        let mut i = 0;
        while i < body.len() {
            let fin_dbg: Option<Vec<String>> = match &body[i] {
                Stmt::Try { finalbody, .. } if !finalbody.is_empty() => Some(
                    finalbody.iter().map(|s| format!("{s:?}")).collect(),
                ),
                _ => None,
            };
            if let Some(fin_dbg) = fin_dbg {
                let mut j = i + 1;
                let mut k = 0;
                while j < body.len()
                    && k < fin_dbg.len()
                    && format!("{:?}", body[j]) == fin_dbg[k]
                {
                    j += 1;
                    k += 1;
                }
                if k == fin_dbg.len() && j > i + 1 {
                    body.drain(i + 1..j);
                }
            }
            i += 1;
        }
    }
    // trailing `return None`
    if code.name != "<module>" && code.name != "<lambda>" {
        if let Some(Stmt::Return(None)) = body.last() {
            body.pop();
        }
    }
    // class bodies using zero-arg super() end with `return __class__`
    // (3.13+: an unnamed cell local shows up as a bad-local marker)
    if let Some(Stmt::Return(Some(e))) = body.last() {
        if let Expr::Name(n) = &**e {
            if n == "__class__" || n.contains("bad-local") || n.contains("__class") {
                body.pop();
            }
        }
    }
    body
}

// =====================  comprehensions  =====================

impl<'a> Ctx<'a> {
    /// Try to turn a completed call into a comprehension. The callee is a
    /// Function whose code object is named `<listcomp>` etc. The iterable is
    /// passed either as a normal argument (3.12+, 2.7 listcomp) or via the
    /// self/marker slot (3.7-3.11 LOAD_METHOD convention).
    fn try_make_comprehension(
        &mut self,
        call_e: &ExprRef,
        marker: Option<Sv>,
    ) -> Option<ExprRef> {
        let Expr::Call { func, args, .. } = &**call_e else {
            return None;
        };
        let fd = match &**func {
            Expr::Function(fd) => fd.clone(),
            Expr::Name(n) if n == "/*generator*/" => {
                // genexpr passed as a call argument: code object remembered
                // at RETURN_GENERATOR
                let code = self.pending_gen_code.take()?;
                Rc::new(FunctionDef {
                    name: code.name.clone(),
                    code,
                    params: Parameters::empty(),
                    decorators: Vec::new(),
                    returns: None,
                    is_async: false,
                })
            }
            _ => return None,
        };
        let kind = match fd.code.name.as_str() {
            "<listcomp>" => CompKind::List,
            "<setcomp>" => CompKind::Set,
            "<dictcomp>" => CompKind::Dict,
            "<genexpr>" | "<async_generator>" => CompKind::Generator,
            _ => return None,
        };

        // locate the iterable argument
        let iter: ExprRef = if let Some(Sv::E(e)) = marker {
            e
        } else if !args.is_empty()
            && !matches!(&*args[0], Expr::Name(n) if n == "/*generator*/")
        {
            args[0].clone()
        } else {
            return None;
        };

        let outer = iter.clone();
        match self.build_comprehension(&fd.code, kind, iter) {
            Some((elt, key, gens)) => {
                let mut generators = gens;
                if generators.is_empty() {
                    return None;
                }
                // the first generator's iterator is the passed-in iterable
                generators[0].iter = outer;
                Some(Rc::new(Expr::Comprehension {
                    kind,
                    elt,
                    key,
                    generators,
                }))
            }
            None => None,
        }
    }

    /// Decode a comprehension code object into (elt, key, generators).
    /// The implicit `.0` parameter holds the outermost iterator (replaced
    /// by the caller with the real iterable expression).
    fn build_comprehension(
        &mut self,
        code: &CodeObject,
        _kind: CompKind,
        outer_iter: ExprRef,
    ) -> Option<(ExprRef, Option<ExprRef>, Vec<Comprehension>)> {
        let table = table_for(self.version).ok()?;
        let instrs = crate::bytecode::decode_instructions(code, table, self.version);

        struct PartialGen {
            target: Option<ExprRef>,
            iter: ExprRef,
            ifs: Vec<ExprRef>,
            is_async: bool,
        }

        let mut partials: Vec<PartialGen> = Vec::new();
        let mut elt: Option<ExprRef> = None;
        let mut key: Option<ExprRef> = None;
        // UNPACK_SEQUENCE loop targets: collect the following stores into a
        // tuple target
        let mut unpack_remaining = 0usize;
        let mut unpack_names: Vec<ExprRef> = Vec::new();

        let mut stack: Vec<ExprRef> = Vec::new();
        let iter0 = outer_iter;
        let mut pending_async = false;

        let name_of_arg = |code: &CodeObject, idx: usize| -> String {
            code.names
                .get(idx)
                .and_then(|o| match &**o {
                    PyObject::Str(s) => Some(s.clone()),
                    PyObject::Bytes(b) => Some(String::from_utf8_lossy(b).into_owned()),
                    _ => None,
                })
                .unwrap_or_else(|| "?".into())
        };

        let mut prev_inst: Option<(Op, u32)> = None;
        for (ii, inst) in instrs.iter().enumerate() {
            let prev = prev_inst.replace((inst.op, inst.arg));
            // walrus inside a comprehension: DUP_TOP (<=3.10) / COPY 1
            // (3.11+) then a non-loop store; both duplicated slots fold
            // into a Named expression that becomes the element value
            let walrus = self.version.at_least(3, 8)
                && (matches!(prev, Some((Op::DUP_TOP, _)))
                    || matches!(prev, Some((Op::COPY, 1))))
                && matches!(
                    inst.op,
                    Op::STORE_FAST | Op::STORE_DEREF | Op::STORE_GLOBAL | Op::STORE_NAME
                )
                && !matches!(
                    instrs.get(ii + 1).map(|x| x.op),
                    Some(Op::STORE_FAST)
                        | Some(Op::STORE_NAME)
                        | Some(Op::STORE_DEREF)
                        | Some(Op::STORE_GLOBAL)
                );
            if walrus {
                let name = match inst.op {
                    Op::STORE_FAST => code
                        .varnames
                        .get(inst.arg as usize)
                        .cloned()
                        .unwrap_or_default(),
                    Op::STORE_DEREF => code
                        .deref_name(inst.arg as usize)
                        .unwrap_or("?")
                        .to_string(),
                    Op::STORE_GLOBAL | Op::STORE_NAME => name_of_arg(code, inst.arg as usize),
                    _ => String::new(),
                };
                let v = stack.pop();
                stack.pop(); // the duplicated original
                if let Some(v) = v {
                    stack.push(Rc::new(Expr::Named {
                        target: Rc::new(Expr::Name(name)),
                        value: v,
                    }));
                }
                continue;
            }
            match inst.op {
                Op::DUP_TOP => {
                    if let Some(t) = stack.last().cloned() {
                        stack.push(t);
                    }
                }
                Op::COPY => {
                    let n = inst.arg as usize;
                    if n >= 1 && stack.len() >= n {
                        let v = stack[stack.len() - n].clone();
                        stack.push(v);
                    }
                }
                Op::STORE_GLOBAL | Op::STORE_NAME => {
                    // non-walrus stores do not occur in comprehension code;
                    // consume the value to keep the stack balanced
                    stack.pop();
                }
                Op::RESUME
                | Op::NOP
                | Op::CACHE
                | Op::RETURN_VALUE
                | Op::RETURN_CONST
                | Op::END_FOR
                | Op::POP_ITER
                | Op::NOT_TAKEN
                | Op::POP_TOP
                | Op::JUMP_BACKWARD
                | Op::JUMP_BACKWARD_NO_INTERRUPT
                | Op::JUMP_ABSOLUTE
                | Op::JUMP_FORWARD
                | Op::JUMP
                | Op::GET_ANEXT
                | Op::END_ASYNC_FOR
                | Op::GET_YIELD_FROM_ITER
                | Op::PRECALL
                | Op::EXTENDED_ARG => {}
                Op::GET_ITER => {}
                Op::GET_AITER => {
                    pending_async = true;
                }
                Op::LOAD_FAST | Op::LOAD_FAST_CHECK | Op::LOAD_FAST_BORROW | Op::LOAD_FAST_AND_CLEAR => {
                    let name = code.varnames.get(inst.arg as usize).cloned();
                    match name {
                        Some(n) if n == ".0" => {
                            stack.push(iter0.clone());
                        }
                        Some(n) => stack.push(Rc::new(Expr::Name(n))),
                        None => stack.push(Rc::new(Expr::Name(format!(".{}", inst.arg)))),
                    }
                }
                Op::LOAD_FAST_BORROW_LOAD_FAST_BORROW | Op::LOAD_FAST_LOAD_FAST => {
                    for idx in [(inst.arg >> 4) as usize, (inst.arg & 0xF) as usize] {
                        match code.varnames.get(idx).cloned() {
                            Some(n) if n == ".0" => stack.push(iter0.clone()),
                            Some(n) => stack.push(Rc::new(Expr::Name(n))),
                            None => stack.push(Rc::new(Expr::Name(format!(".{idx}")))),
                        }
                    }
                }
                Op::LOAD_SMALL_INT => {
                    stack.push(Rc::new(Expr::Const(Rc::new(PyObject::Int(inst.arg as i32)))));
                }
                Op::LOAD_DEREF | Op::LOAD_CLOSURE | Op::LOAD_CLASSDEREF => {
                    let n = code
                        .deref_name(inst.arg as usize)
                        .unwrap_or("?")
                        .to_string();
                    stack.push(Rc::new(Expr::Name(n)));
                }
                Op::LOAD_CONST => {
                    if let Some(o) = code.consts.get(inst.arg as usize) {
                        stack.push(Rc::new(Expr::Const(o.clone())));
                    }
                }
                Op::LOAD_NAME => {
                    let n = name_of_arg(code, inst.arg as usize);
                    stack.push(Rc::new(Expr::Name(n)));
                }
                Op::LOAD_GLOBAL => {
                    let idx = if self.version.at_least(3, 11) {
                        (inst.arg >> 1) as usize
                    } else {
                        inst.arg as usize
                    };
                    let n = name_of_arg(code, idx);
                    stack.push(Rc::new(Expr::Name(n)));
                }
                Op::LOAD_ATTR | Op::LOAD_METHOD => {
                    let idx = if inst.op == Op::LOAD_ATTR && self.version.at_least(3, 12) {
                        (inst.arg >> 1) as usize
                    } else {
                        inst.arg as usize
                    };
                    let is_method = inst.op == Op::LOAD_METHOD
                        || (inst.op == Op::LOAD_ATTR
                            && self.version.at_least(3, 12)
                            && inst.arg & 1 != 0);
                    let attr = name_of_arg(code, idx);
                    if let Some(v) = stack.pop() {
                        let e: ExprRef = Rc::new(Expr::Attribute { value: v.clone(), attr });
                        if is_method {
                            if self.version.at_least(3, 14) {
                                stack.push(e);
                                stack.push(v);
                            } else if self.version.at_least(3, 11) {
                                stack.push(v);
                                stack.push(e);
                            } else {
                                stack.push(e);
                                stack.push(v);
                            }
                        } else {
                            stack.push(e);
                        }
                    }
                }
                Op::FOR_ITER => {
                    let it = stack.pop().unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                    partials.push(PartialGen {
                        target: None,
                        iter: it,
                        ifs: Vec::new(),
                        is_async: std::mem::take(&mut pending_async),
                    });
                }
                Op::STORE_FAST_LOAD_FAST => {
                    let idx = ((inst.arg >> 4) & 0xF) as usize;
                    let name = code.varnames.get(idx).cloned().unwrap_or_default();
                    if let Some(last) = partials.last_mut() {
                        if last.target.is_none() {
                            last.target = Some(Rc::new(Expr::Name(name.clone())));
                        }
                    }
                    // the LOAD half pushes the value back
                    match code.varnames.get((inst.arg & 0xF) as usize).cloned() {
                        Some(n) if n == ".0" => stack.push(iter0.clone()),
                        Some(n) => stack.push(Rc::new(Expr::Name(n))),
                        None => stack.push(Rc::new(Expr::Name("?".to_string()))),
                    }
                }
                Op::STORE_FAST | Op::STORE_DEREF => {
                    let name = if inst.op == Op::STORE_FAST {
                        code.varnames
                            .get(inst.arg as usize)
                            .cloned()
                            .unwrap_or_default()
                    } else {
                        code.deref_name(inst.arg as usize)
                            .unwrap_or("?")
                            .to_string()
                    };
                    if unpack_remaining > 0 {
                        unpack_names.push(Rc::new(Expr::Name(name)));
                        unpack_remaining -= 1;
                        if unpack_remaining == 0 {
                            let tuple = Rc::new(Expr::Tuple(std::mem::take(
                                &mut unpack_names,
                            )));
                            if let Some(last) = partials.last_mut() {
                                last.target = Some(tuple);
                            }
                        }
                        continue;
                    }
                    if let Some(last) = partials.last_mut() {
                        if last.target.is_none() {
                            last.target = Some(Rc::new(Expr::Name(name)));
                            continue;
                        }
                    }
                    // tuple targets or other stores: pop value
                    let v = stack.pop();
                    if name.starts_with('.') {
                        // tuple unpack of loop target
                        if let Some(last) = partials.last_mut() {
                            last.target = Some(v.unwrap_or_else(|| Rc::new(Expr::Name(name))));
                        }
                    }
                }
                Op::UNPACK_SEQUENCE => {
                    // the iterable stays for the element expression; the
                    // next `arg` stores form the tuple loop target
                    unpack_remaining = inst.arg as usize;
                    unpack_names.clear();
                }
                Op::POP_JUMP_IF_FALSE
                | Op::POP_JUMP_IF_TRUE
                | Op::POP_JUMP_FORWARD_IF_FALSE
                | Op::POP_JUMP_FORWARD_IF_TRUE
                | Op::POP_JUMP_BACKWARD_IF_FALSE
                | Op::POP_JUMP_BACKWARD_IF_TRUE
                | Op::JUMP_IF_FALSE_OR_POP
                | Op::JUMP_IF_TRUE_OR_POP => {
                    if let Some(c) = stack.pop() {
                        if let Some(last) = partials.last_mut() {
                            last.ifs.push(c);
                        }
                    }
                }
                Op::LIST_APPEND | Op::SET_ADD => {
                    let item = stack.pop().unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                    elt.get_or_insert(item);
                }
                Op::MAP_ADD => {
                    // 3.8+: value on top; pre-3.8 (incl. py2.7): key on top
                    let (k, v) = if self.version.at_least(3, 8) {
                        let v = stack.pop().unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                        let k = stack.pop().unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                        (k, v)
                    } else {
                        let k = stack.pop().unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                        let v = stack.pop().unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                        (k, v)
                    };
                    key.get_or_insert(k);
                    elt.get_or_insert(v);
                }
                Op::YIELD_VALUE => {
                    let item = stack.pop().unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                    elt.get_or_insert(item);
                }
                // f-string building (3.6+; `'%s' % x` compiles to this on
                // 3.11+, and comprehension elements may be f-strings)
                Op::FORMAT_VALUE | Op::FORMAT_SIMPLE => {
                    let conversion = match inst.arg & 0x3 {
                        1 => Some('s'),
                        2 => Some('r'),
                        3 => Some('a'),
                        _ => None,
                    };
                    let format_spec = if inst.op == Op::FORMAT_VALUE
                        && inst.arg & 0x04 != 0
                    {
                        stack.pop()
                    } else {
                        None
                    };
                    let value = stack
                        .pop()
                        .unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                    let part = FStringPart::Value {
                        value,
                        conversion,
                        format_spec: format_spec.map(|f| Box::new(expr_to_fstring(f))),
                    };
                    stack.push(Rc::new(Expr::FString(Box::new(FString {
                        parts: vec![part],
                    }))));
                }
                Op::FORMAT_WITH_SPEC => {
                    let format_spec = stack.pop();
                    let value = stack
                        .pop()
                        .unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                    let part = FStringPart::Value {
                        value,
                        conversion: None,
                        format_spec: format_spec.map(|f| Box::new(expr_to_fstring(f))),
                    };
                    stack.push(Rc::new(Expr::FString(Box::new(FString {
                        parts: vec![part],
                    }))));
                }
                Op::CONVERT_VALUE => {
                    let conversion = match inst.arg {
                        1 => Some('s'),
                        2 => Some('r'),
                        3 => Some('a'),
                        _ => None,
                    };
                    let value = stack
                        .pop()
                        .unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())));
                    let part = FStringPart::Value {
                        value,
                        conversion,
                        format_spec: None,
                    };
                    stack.push(Rc::new(Expr::FString(Box::new(FString {
                        parts: vec![part],
                    }))));
                }
                Op::BUILD_STRING => {
                    let n = inst.arg as usize;
                    let mut parts_e: Vec<ExprRef> = Vec::with_capacity(n);
                    for _ in 0..n {
                        if let Some(p) = stack.pop() {
                            parts_e.push(p);
                        }
                    }
                    parts_e.reverse();
                    let mut out_parts = Vec::new();
                    for p in parts_e {
                        match &*p {
                            Expr::Const(o) => match &**o {
                                PyObject::Str(s2) => {
                                    out_parts.push(FStringPart::Literal(s2.clone()))
                                }
                                _ => out_parts.push(FStringPart::Value {
                                    value: p.clone(),
                                    conversion: None,
                                    format_spec: None,
                                }),
                            },
                            Expr::FString(fs) => out_parts.extend(fs.parts.iter().cloned()),
                            _ => out_parts.push(FStringPart::Value {
                                value: p.clone(),
                                conversion: None,
                                format_spec: None,
                            }),
                        }
                    }
                    stack.push(Rc::new(Expr::FString(Box::new(FString {
                        parts: out_parts,
                    }))));
                }
                Op::BINARY_OP => {
                    let rhs = stack.pop();
                    let lhs = stack.pop();
                    if let (Some(l), Some(r)) = (lhs, rhs) {
                        let name = crate::bytecode::binary_op_name(inst.arg, self.version)
                            .unwrap_or("+");
                        let op = binop_from_text(name);
                        stack.push(Rc::new(Expr::Binary {
                            op,
                            left: l,
                            right: r,
                        }));
                    }
                }
                Op::BINARY_ADD
                | Op::BINARY_SUBTRACT
                | Op::BINARY_MULTIPLY
                | Op::BINARY_TRUE_DIVIDE
                | Op::BINARY_FLOOR_DIVIDE
                | Op::BINARY_MODULO
                | Op::BINARY_POWER
                | Op::BINARY_SUBSCR => {
                    let rhs = stack.pop();
                    let lhs = stack.pop();
                    if let (Some(l), Some(r)) = (lhs, rhs) {
                        if inst.op == Op::BINARY_SUBSCR {
                            stack.push(Rc::new(Expr::Subscript { value: l, index: r }));
                        } else {
                            let name = match inst.op {
                                Op::BINARY_ADD => "+",
                                Op::BINARY_SUBTRACT => "-",
                                Op::BINARY_MULTIPLY => "*",
                                Op::BINARY_TRUE_DIVIDE => "/",
                                Op::BINARY_FLOOR_DIVIDE => "//",
                                Op::BINARY_MODULO => "%",
                                Op::BINARY_POWER => "**",
                                _ => "+",
                            };
                            stack.push(Rc::new(Expr::Binary {
                                op: binop_from_text(name),
                                left: l,
                                right: r,
                            }));
                        }
                    }
                }
                Op::COMPARE_OP | Op::IS_OP | Op::CONTAINS_OP => {
                    let rhs = stack.pop();
                    let lhs = stack.pop();
                    if let (Some(l), Some(r)) = (lhs, rhs) {
                        let idx = if inst.op == Op::COMPARE_OP {
                            compare_op_index(inst.arg, self.version)
                        } else if inst.op == Op::IS_OP {
                            if inst.arg == 1 { 9 } else { 8 }
                        } else if inst.arg == 1 {
                            7
                        } else {
                            6
                        };
                        stack.push(Rc::new(Expr::Compare {
                            operands: vec![l, r],
                            ops: vec![cmp_from_index(idx)],
                        }));
                    }
                }
                Op::UNARY_NOT => {
                    if let Some(v) = stack.pop() {
                        stack.push(Rc::new(Expr::Unary {
                            op: UnaryOp::Not,
                            operand: v,
                        }));
                    }
                }
                Op::MAKE_FUNCTION | Op::MAKE_CLOSURE => {
                    // mini-sim: turn the code constant into a Function value
                    let mut popped = stack.pop();
                    // 3.3-3.10: qualname sits above the code constant
                    if self.version.at_least(3, 3) && !self.version.at_least(3, 11) {
                        let is_code = matches!(&popped, Some(e) if matches!(&**e, Expr::Const(o) if matches!(&**o, PyObject::Code(_))));
                        if !is_code {
                            popped = stack.pop();
                        }
                    }
                    let mut handled = false;
                    if let Some(e) = popped {
                        if let Expr::Const(o) = &*e {
                            if let PyObject::Code(c) = &**o {
                                stack.push(Rc::new(Expr::Function(Rc::new(FunctionDef {
                                    name: c.name.clone(),
                                    code: c.clone(),
                                    params: Parameters::empty(),
                                    decorators: Vec::new(),
                                    returns: None,
                                    is_async: false,
                                }))));
                                handled = true;
                            }
                        }
                        if !handled {
                            stack.push(e);
                        }
                    }
                }
                Op::CALL_FUNCTION | Op::CALL | Op::CALL_METHOD => {
                    let n = if inst.op == Op::CALL_FUNCTION && !self.version.at_least(3, 6) {
                        (inst.arg & 0xFF) as usize
                    } else {
                        inst.arg as usize
                    };
                    let mut args = Vec::new();
                    for _ in 0..n {
                        if let Some(a) = stack.pop() {
                            args.push(a);
                        }
                    }
                    args.reverse();
                    // comprehension instantiation: [genfunc, iterable]
                    let sn = stack.len();
                    if sn >= 2 && n == 0 {
                        let comp_fn = matches!(&*stack[sn - 2], Expr::Function(fd)
                            if matches!(fd.code.name.as_str(),
                                "<listcomp>" | "<setcomp>" | "<dictcomp>" | "<genexpr>"));
                        if comp_fn {
                            let iter = stack.pop().unwrap();
                            let func = stack.pop().unwrap();
                            if let Expr::Function(fd) = &*func {
                                let kind = match fd.code.name.as_str() {
                                    "<listcomp>" => CompKind::List,
                                    "<setcomp>" => CompKind::Set,
                                    "<dictcomp>" => CompKind::Dict,
                                    _ => CompKind::Generator,
                                };
                                if let Some((elt, key, gens)) =
                                    self.build_comprehension(&fd.code, kind, iter)
                                {
                                    stack.push(Rc::new(Expr::Comprehension {
                                        kind,
                                        elt,
                                        key,
                                        generators: gens,
                                    }));
                                    continue;
                                }
                            }
                        }
                    }
                    let underflow = || Rc::new(Expr::Name("?".to_string()));
                    let func = if inst.op == Op::CALL_FUNCTION {
                        // pre-3.7 calling convention: no marker slot
                        stack.pop().unwrap_or_else(underflow)
                    } else if self.version.at_least(3, 14) {
                        // [callable, marker, args]
                        if matches!(stack.last(), Some(m) if is_null_marker(m)) {
                            stack.pop();
                        }
                        stack.pop().unwrap_or_else(underflow)
                    } else if self.version.at_least(3, 11) {
                        // [marker, callable, args]
                        let f = stack.pop().unwrap_or_else(underflow);
                        if matches!(&*f, Expr::Attribute { .. }) {
                            stack.pop(); // method receiver slot
                        } else if matches!(stack.last(), Some(m) if is_null_marker(m)) {
                            stack.pop();
                        }
                        f
                    } else {
                        // 3.7-3.10: CALL_METHOD has [callable, marker, args]
                        if inst.op == Op::CALL_METHOD {
                            stack.pop();
                        }
                        stack.pop().unwrap_or_else(underflow)
                    };
                    // comprehension instantiation with the iterator passed
                    // as the single argument (<=3.11 listcomp/genexpr)
                    if args.len() == 1 && keywords_empty(&args) {
                        if let Expr::Function(fd) = &*func {
                            let kind = match fd.code.name.as_str() {
                                "<listcomp>" => Some(CompKind::List),
                                "<setcomp>" => Some(CompKind::Set),
                                "<dictcomp>" => Some(CompKind::Dict),
                                "<genexpr>" => Some(CompKind::Generator),
                                _ => None,
                            };
                            if let Some(kind) = kind {
                                if let Some((elt, key, gens)) = self.build_comprehension(
                                    &fd.code,
                                    kind,
                                    args[0].clone(),
                                ) {
                                    stack.push(Rc::new(Expr::Comprehension {
                                        kind,
                                        elt,
                                        key,
                                        generators: gens,
                                    }));
                                    continue;
                                }
                            }
                        }
                    }
                    stack.push(Rc::new(Expr::Call {
                        func,
                        args,
                        keywords: Vec::new(),
                        star_args: None,
                        star_kwargs: None,
                    }));
                }
                Op::BUILD_TUPLE | Op::BUILD_LIST | Op::BUILD_SET => {
                    let n = inst.arg as usize;
                    let mut items = Vec::new();
                    for _ in 0..n {
                        if let Some(v) = stack.pop() {
                            items.push(v);
                        }
                    }
                    items.reverse();
                    let e = match inst.op {
                        Op::BUILD_TUPLE => Expr::Tuple(items),
                        Op::BUILD_LIST => Expr::List(items),
                        _ => Expr::Set(items),
                    };
                    stack.push(Rc::new(e));
                }
                Op::TO_BOOL => {}
                _ => {}
            }
        }

        let elt = elt?;
        if partials.is_empty() {
            return None;
        }
        let gens: Vec<Comprehension> = partials
            .into_iter()
            .map(|p| Comprehension {
                target: p.target.unwrap_or_else(|| Rc::new(Expr::Name("_".to_string()))),
                iter: p.iter,
                ifs: p.ifs,
                is_async: p.is_async,
            })
            .collect();
        Some((elt, key, gens))
    }
}

// =====================  PEP 709 inline comprehensions (3.12+)  =====================

impl<'a> Ctx<'a> {
    /// Look backwards from the current FOR_ITER for the comprehension
    /// prologue: `GET_ITER; [LOAD_FAST_AND_CLEAR/SWAP...]; BUILD_{LIST,SET,
    /// MAP} 0; [SWAP...]`. Returns the comprehension kind when matched.
    fn detect_inline_comp(&self) -> Option<CompKind> {
        // PEP 709 inline comprehensions (3.12+) and py2.7 module-level
        // list/set/dict comprehensions share the same shape
        let inline_era = self.version.at_least(3, 12) || self.version.major == 2;
        if !inline_era {
            return None;
        }
        let cur = self.cur_offset;
        let ci = *self.idx_of.get(&cur)?;
        // walk back to the FOR_ITER
        let mut i = ci;
        while self.instrs.get(i).map(|x| x.offset) != Some(cur) && i > 0 {
            i -= 1;
        }
        // scan backwards: skip SWAPs, find BUILD_x 0, then GET_ITER before it
        let mut j = i;
        let mut kind = None;
        let mut steps = 0;
        while j > 0 && steps < 14 {
            j -= 1;
            steps += 1;
            // hop over a completed nested comprehension region (py2: the
            // outer comp's iterable was itself an inline comp)
            let off = self.instrs[j].offset;
            if let Some((rs, _)) = self
                .completed_comp_regions
                .iter()
                .find(|(rs, re)| off >= *rs && off < *re)
            {
                let rs = *rs;
                if let Some(&rj) = self.idx_of.get(&rs) {
                    j = rj; // loop pre-decrements to the instruction BEFORE
                            // the nested region — its own BUILD_x belongs
                            // to the nested comp, not the outer one
                    continue;
                }
            }
            let inst = &self.instrs[j];
            match inst.op {
                // 3.13 places GET_ITER right before FOR_ITER; 3.12 places it
                // before the LOAD_FAST_AND_CLEAR prologue; py2.7 has
                // BUILD_x 0; <iter expr>; GET_ITER; FOR_ITER
                Op::SWAP
                | Op::GET_ITER
                | Op::GET_AITER
                | Op::NOP
                | Op::LOAD_NAME
                | Op::LOAD_FAST
                | Op::LOAD_CONST
                | Op::LOAD_GLOBAL
                | Op::LOAD_DEREF
                | Op::LOAD_METHOD
                | Op::LOAD_ATTR
                | Op::CALL
                | Op::CALL_FUNCTION
                | Op::CALL_METHOD
                | Op::BUILD_TUPLE
                | Op::BUILD_LIST
                | Op::DUP_TOP
                | Op::COPY => {
                    // 2.6 stashes the accumulator in a synthetic `_[N]`
                    // name between BUILD_LIST and the loop
                    if matches!(inst.op, Op::BUILD_LIST | Op::BUILD_TUPLE) && inst.arg == 0 {
                        // empty collection build = comprehension accumulator
                        kind = Some(CompKind::List);
                        break;
                    }
                    continue;
                }
                Op::STORE_NAME
                    if self.version.major == 2
                        && self.const_name(inst.arg as usize).starts_with("_[") =>
                {
                    continue;
                }
                Op::BUILD_SET if inst.arg == 0 => {
                    kind = Some(CompKind::Set);
                    break;
                }
                Op::BUILD_MAP if inst.arg == 0 => {
                    kind = Some(CompKind::Dict);
                    break;
                }
                _ => return None,
            }
        }
        let kind = kind?;
        if self.version.major == 2 {
            // py2: BUILD_x 0; <iter expr>; GET_ITER; FOR_ITER — verify a
            // GET_ITER sits between the build and the loop
            let ok = self.instrs[j..i]
                .iter()
                .any(|x| matches!(x.op, Op::GET_ITER | Op::GET_AITER));
            return if ok { Some(kind) } else { None };
        }
        // before the BUILD: LOAD_FAST_AND_CLEAR*/SWAP/... then GET_ITER
        let mut k = j;
        let mut steps = 0;
        while k > 0 && steps < 8 {
            k -= 1;
            steps += 1;
            let inst = &self.instrs[k];
            match inst.op {
                Op::GET_ITER | Op::GET_AITER => return Some(kind),
                Op::SWAP | Op::LOAD_FAST_AND_CLEAR => continue,
                _ => return None,
            }
        }
        None
    }

    /// offset of the BUILD_x 0 that opened the current py2 comprehension
    fn comp_prologue_start(&self) -> usize {
        let Some(&ci) = self.idx_of.get(&self.cur_offset) else {
            return self.cur_offset;
        };
        let mut j = ci;
        let mut steps = 0;
        while j > 0 && steps < 16 {
            j -= 1;
            steps += 1;
            let ins = &self.instrs[j];
            if matches!(ins.op, Op::BUILD_LIST | Op::BUILD_SET | Op::BUILD_MAP)
                && (ins.arg == 0 || ins.op == Op::BUILD_MAP)
            {
                return ins.offset;
            }
        }
        self.cur_offset
    }

    fn start_inline_comp(&mut self, kind: CompKind, inst: &Instruction) {
        // the iterable is on top (GET_ITER kept it); consume it into the
        // generator model
        let iter = self.pop_expr();
        // cleared variables from the prologue: collect LOAD_FAST_AND_CLEAR
        // across SWAP/BUILD/GET_ITER until a non-prologue instruction
        let mut cleared = Vec::new();
        let cur = self.cur_offset;
        if let Some(&ci) = self.idx_of.get(&cur) {
            for back in (0..ci).rev().take(12) {
                let ins = &self.instrs[back];
                match ins.op {
                    Op::LOAD_FAST_AND_CLEAR => {
                        cleared.push(self.local_name(ins.arg as usize));
                    }
                    Op::SWAP
                    | Op::GET_ITER
                    | Op::GET_AITER
                    | Op::NOP
                    | Op::BUILD_LIST
                    | Op::BUILD_SET
                    | Op::BUILD_MAP
                    | Op::COPY => continue,
                    _ => break,
                }
            }
        }
        // pre-scan: collect every FOR_ITER offset and the region end
        let ci = *self.idx_of.get(&cur).unwrap_or(&0);
        let mut for_offsets = vec![inst.offset];
        let mut depth = 1usize;
        let mut end_off = usize::MAX;
        if self.version.major == 2 {
            // py2: no END_FOR; the outermost FOR_ITER exit ends the region
            end_off = inst.target.unwrap_or(usize::MAX);
            for ins in self.instrs.iter().skip(ci + 1) {
                if ins.offset >= end_off {
                    break;
                }
                if matches!(ins.op, Op::FOR_ITER) {
                    for_offsets.push(ins.offset);
                }
            }
        } else {
            for ins in self.instrs.iter().skip(ci + 1) {
                match ins.op {
                    Op::FOR_ITER | Op::FOR_LOOP => {
                        depth += 1;
                        for_offsets.push(ins.offset);
                    }
                    Op::END_FOR => {
                        depth -= 1;
                        if depth == 0 {
                            end_off = ins.offset;
                            break;
                        }
                    }
                    Op::RETURN_VALUE | Op::RETURN_CONST => break,
                    _ => {}
                }
            }
        }
        // an active comprehension becomes the parent of this nested one
        if let Some(parent) = self.inline_comp.take() {
            self.inline_comp_stack.push(parent);
        }
        // keep the iterator on the stack like the VM does; the loop-target
        // store will consume it
        self.push(iter.clone());
        let cleared_all = cleared;
        self.inline_comp = Some(InlineComp {
            kind,
            start: self.comp_prologue_start(),
            iter: iter.clone(),
            end: end_off,
            for_iter_offsets: for_offsets,
            gens: Vec::new(),
            cur: Some(PartialGen {
                target: None,
                iter,
                ifs: Vec::new(),
            }),
            elt: None,
            key: None,
            cleared_vars: cleared_all,
            target_seen: false,
        });
        self.comp_target_store = true;
    }

    fn comp_add_element(&mut self, inst: &Instruction) {
        let (value, key) = if inst.op == Op::MAP_ADD {
            // 3.8+: value on top, key below
            let value = self.pop_expr();
            let key = self.pop_expr();
            (value, Some(key))
        } else {
            (self.pop_expr(), None)
        };
        if let Some(comp) = &mut self.inline_comp {
            if let Some(k) = key {
                comp.key.get_or_insert(k);
            }
            comp.elt.get_or_insert(value);
        }
    }

    /// True when the offset lies inside the active comprehension region.
    fn in_comp_region(&self, offset: usize) -> bool {
        self.inline_comp
            .as_ref()
            .map_or(false, |c| offset > c.for_iter_offsets[0] && offset < c.end)
    }

    /// True when the instructions immediately before `offset` contain a
    /// BUILD_{LIST,SET,MAP} 0 — the marker of a NEW (nested) comprehension
    /// level rather than an extra generator of the current one.
    fn has_build_prologue(&self, offset: usize) -> bool {
        let Some(&ci) = self.idx_of.get(&offset) else {
            return false;
        };
        for back in (0..ci).rev().take(6) {
            let ins = &self.instrs[back];
            match ins.op {
                Op::SWAP | Op::LOAD_FAST_AND_CLEAR | Op::LOAD_FAST | Op::GET_ITER
                | Op::GET_AITER | Op::NOP | Op::LOAD_NAME | Op::LOAD_DEREF
                | Op::LOAD_CONST | Op::COPY => continue,
                Op::BUILD_LIST | Op::BUILD_SET | Op::BUILD_MAP => {
                    return ins.arg == 0;
                }
                _ => return false,
            }
        }
        false
    }

    /// Nested FOR_ITER inside an inline comprehension: complete the current
    /// generator and start a new one with the popped iterable.
    fn push_nested_comp_gen(&mut self) {
        // additional generator of the same comprehension.
        // 3.12+: the iterator stays on the stack (POP_ITER removes it at
        // the loop end). py2: there is no POP_ITER — the single end-of-comp
        // pop covers only the outermost iterator, so consume this one here
        // (start_inline_comp pushed it back for the target store)
        let iter = if self.version.major == 2 {
            self.pop_expr()
        } else {
            self.stack
                .last()
                .and_then(|sv| match sv {
                    Sv::E(e) => Some(e.clone()),
                    _ => None,
                })
                .unwrap_or_else(|| Rc::new(Expr::Name("?".to_string())))
        };
        if self.version.major == 2 {
            // keep the iterator available for the loop-target store flow
            self.push(iter.clone());
        }
        if let Some(comp) = &mut self.inline_comp {
            if let Some(done) = comp.cur.take() {
                comp.gens.push(Comprehension {
                    target: done
                        .target
                        .unwrap_or_else(|| Rc::new(Expr::Name("_".to_string()))),
                    iter: done.iter,
                    ifs: done.ifs,
                    is_async: false,
                });
            }
            comp.cur = Some(PartialGen {
                target: None,
                iter,
                ifs: Vec::new(),
            });
            comp.target_seen = false;
        }
        self.comp_target_store = true;
    }

    /// Called at the outermost END_FOR: build the comprehension expression.
    /// For a nested comprehension the result becomes the parent's element.
    fn finish_inline_comp(&mut self) {
        let Some(mut comp) = self.inline_comp.take() else {
            return;
        };
        if self.version.major == 2 && comp.start < comp.end && comp.end != usize::MAX {
            self.completed_comp_regions.push((comp.start, comp.end));
        }
        if let Some(done) = comp.cur.take() {
            comp.gens.push(Comprehension {
                target: done
                    .target
                    .unwrap_or_else(|| Rc::new(Expr::Name("_".to_string()))),
                iter: done.iter,
                ifs: done.ifs,
                is_async: false,
            });
        }
        let elt = comp
            .elt
            .take()
            .unwrap_or_else(|| Rc::new(Expr::Name("_".to_string())));
        let expr: ExprRef = Rc::new(Expr::Comprehension {
            kind: comp.kind,
            elt,
            key: comp.key.take(),
            generators: std::mem::take(&mut comp.gens),
        });
        // the BUILD_LIST/SET/MAP placeholder on the stack is replaced by the
        // comprehension expression (it may sit below a leftover iterator)
        let mut replaced = false;
        let n = self.stack.len();
        for i in (0..n).rev().take(3) {
            if let Sv::E(e) = &self.stack[i] {
                if matches!(&**e, Expr::List(_) | Expr::Set(_) | Expr::Dict(_)) {
                    self.stack[i] = Sv::E(expr.clone());
                    replaced = true;
                    // 3.13+ emits `END_FOR; POP_TOP/POP_ITER`: the VM's
                    // cleanup drops the exhausted iterator that sat ABOVE
                    // the result — we never modeled that slot, so eat the
                    // upcoming cleanup instead of letting it swallow the
                    // comprehension
                    if self.version.at_least(3, 13) && i + 1 == n {
                        if let Some(&ci) = self.idx_of.get(&self.cur_offset) {
                            if matches!(
                                self.instrs.get(ci + 1).map(|x| x.op),
                                Some(Op::POP_TOP) | Some(Op::POP_ITER)
                            ) {
                                self.skip_until = Some(self.instrs[ci + 1].end());
                            }
                        }
                    }
                    break;
                }
            }
        }
        if let Some(mut parent) = self.inline_comp_stack.pop() {
            // nested comprehension: parent resumes; its LIST_APPEND will
            // pop this expression as the parent's element
            for v in comp.cleared_vars {
                if !parent.cleared_vars.contains(&v) {
                    parent.cleared_vars.push(v);
                }
            }
            self.inline_comp = Some(parent);
            if !replaced {
                self.push(expr);
            }
        } else {
            for v in comp.cleared_vars.drain(..) {
                if !self.pending_restore_vars.contains(&v) {
                    self.pending_restore_vars.push(v);
                }
            }
            if !replaced {
                self.push(expr);
            }
        }
    }
}

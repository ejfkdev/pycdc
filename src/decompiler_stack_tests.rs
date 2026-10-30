use super::*;
use crate::pyc::PycModule;

fn context(code: &CodeObject, version: PythonVersion, instrs: Vec<Instruction>) -> Ctx<'_> {
    Ctx {
        code,
        table: table_for(version).unwrap(),
        version,
        instrs,
        idx_of: Default::default(),
        targets: Default::default(),
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
        region_collect_only: false,
        skipped_chain_landing: None,
        pending_gen_code: None,
        recent_code_const: None,
        pending_match_class: None,
        last_kw_names: Vec::new(),
        globals: Vec::new(),
        nonlocals: Vec::new(),
        exc_entries: Vec::new(),
        raw_exc_entries: Vec::new(),
        try_ctxs: HashMap::new(),
        handler_zone: None,
        chain_heads: Default::default(),
        with_regions: Default::default(),
        with_region_handlers: Default::default(),
        active_try: None,
        active_try_stack: Vec::new(),
        last_try_body_end: None,
        pending_try_tail: None,
        pending_post_chain_stmt: None,
        tail_pair_at: None,
        pending_try_ctx: None,
        emitting_try: std::collections::HashSet::new(),
        fin_copy_guard: None,
        pending_nested_finally: None,
        nested_inner_handlers: Vec::new(),
        legacy_try: None,
        legacy_handler: None,
        legacy_handler_end: None,
        legacy_handler_name_store: false,
        legacy_handler_cleanup: false,
        fused_guard_pad_at: std::collections::HashSet::new(),
        swallowed_cleanup_del: None,
        in_handler_prelude: false,
        pending_then: Vec::new(),
        pending_handlers: Vec::new(),
        pending_try_body: Vec::new(),
        pending_orelse_mark: None,
        return_offsets: std::collections::HashSet::new(),
        legacy_body_redirect: None,
        pending_loop_close_at_chain: None,
        chain_absorb_body: None,
        sunk_return_fold_at: None,
        sunk_loop_return_lift: false,
        sunk_pair_drop: None,
        sunk_while_lift: None,
        nested_tail_defer: false,
        lexical_loop_handlers: FastMap::default(),
        pending_try_handlers: Vec::new(),
        pending_loop: Vec::new(),
        pending_with: Vec::new(),
        pending_try_orelse: Vec::new(),
        with_exits: 0,
        pending_print: Vec::new(),
        pending_print_dest: None,
        unpack_targets: FrameTargets(Vec::new()),
        unpack_target_lines: Vec::new(),
        pending_unpack_wrap: Vec::new(),
        awaiting_for_target: false,
        pending_if_stmts: Vec::new(),
        cur_offset: 0,
        cur_next: 0,
        prev_op: None,
        prev_op_at_exec: None,
        skip_until: None,
        import_star_pop_pending: false,
        cond_jump_redirect: std::collections::HashMap::new(),
        dup_copy_redirect: HashMap::new(),
        dup_copy_skip: Vec::new(),
        broken_loop_top: None,
        py2_else_pop_at: None,
        pending_star_kw_call: false,
        threaded_break_at: HashSet::new(),
        closed_loop_tops: Vec::new(),
        while_true_loops: Vec::new(),
        or_rot_revals: Vec::new(),
        bare_try_parse: false,
        handler_sunk_tail: Vec::new(),
        dup_tail_ternary_skip: None,
        pending_as_cleanup: None,
        star_tail: Vec::new(),
        star_tail_end: None,
        region_result_expr: None,
        held_cleanup_store: None,
        class_scope: Vec::new(),
        inline_comp: None,
        inline_comp_stack: Vec::new(),
        pending_restore_vars: Vec::new(),
        comp_restore_vars: Vec::new(),
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
        dotted_as_just_emitted: false,
        import_module: None,
    }
}

fn instruction(op: Op, arg: u32) -> Instruction {
    Instruction {
        offset: 0, start: 0, size: 2, opcode: 0, op, arg,
        has_arg: true, target: None, is_backward: false, line: None,
    }
}

fn fixture() -> PycModule {
    PycModule::from_bytes(include_bytes!("../tests/pyc/comprehensions.3.11.pyc")).unwrap()
}

#[test]
fn copy_keeps_one_evaluation_and_swap_reorders_without_losing_operands() {
    let module = fixture();
    // The intermediate stack in `lower <= read() <= upper` is reordered
    // and copied so the middle expression is evaluated exactly once.
    let lower = Rc::new(Expr::Name("lower".into()));
    let middle = Rc::new(Expr::Call {
        func: Rc::new(Expr::Name("read".into())), args: Vec::new(),
        keywords: Vec::new(), star_args: None, star_kwargs: None,
    });
    for minor in 11..=14 {
        let version = PythonVersion { minor, ..module.version() };
        let ctx = context(&module.code, version,
            vec![instruction(Op::SWAP, 2), instruction(Op::COPY, 2)]);
        let result = ctx.sim_stack_region(0, 2, vec![lower.clone(), middle.clone()])
            .expect("COPY and SWAP are available from Python 3.11");
        assert_eq!(result.len(), 3);
        assert!(Rc::ptr_eq(&result[0], &middle));
        assert!(Rc::ptr_eq(&result[1], &lower));
        assert!(Rc::ptr_eq(&result[2], &middle));
    }
}

#[test]
fn copy_and_swap_respect_deeper_stack_entries_and_region_boundaries() {
    let module = fixture();
    let values: Vec<_> = ["callee", "argument", "value"].iter()
        .map(|name| Rc::new(Expr::Name((*name).into()))).collect();
    let ctx = context(&module.code, module.version(), vec![
        instruction(Op::SWAP, 3), instruction(Op::COPY, 3),
        instruction(Op::STORE_FAST, 0),
    ]);
    let result = ctx.sim_stack_region(0, 2, values.clone()).unwrap();
    assert_eq!(result.len(), 4);
    for (index, source) in [2, 1, 0, 2].iter().enumerate() {
        assert!(Rc::ptr_eq(&result[index], &values[*source]));
    }
    // Simulation must still reject a region that includes a statement.
    assert!(ctx.sim_stack_region(0, 3, values).is_none());
}

#[test]
fn copy_and_swap_reject_zero_depth_and_stack_underflow() {
    let module = fixture();
    for op in [Op::COPY, Op::SWAP] {
        for (depth, length) in [(0, 0), (0, 1), (1, 0), (2, 1), (u32::MAX, 1)] {
            let ctx = context(&module.code, module.version(), vec![instruction(op, depth)]);
            let values = vec![Rc::new(Expr::Name("value".into())); length];
            assert!(ctx.sim_stack_region(0, 1, values).is_none(), "{op:?} {depth}");
        }
    }
}

#[test]
fn top_copy_and_identity_swap_are_valid() {
    let module = fixture();
    let value = Rc::new(Expr::Name("value".into()));
    let ctx = context(&module.code, module.version(),
        vec![instruction(Op::COPY, 1), instruction(Op::SWAP, 1)]);
    let result = ctx.sim_stack_region(0, 2, vec![value.clone()]).unwrap();
    assert_eq!(result.len(), 2);
    assert!(result.iter().all(|entry| Rc::ptr_eq(entry, &value)));
}

#[test]
fn walrus_keeps_the_local_binding_and_one_evaluation() {
    let mut module = fixture();
    Rc::get_mut(&mut module.code).unwrap().varnames = vec!["state".into()];
    let value = Rc::new(Expr::Call {
        func: Rc::new(Expr::Name("get".into())),
        args: vec![Rc::new(Expr::Name("entity_id".into()))],
        keywords: Vec::new(), star_args: None, star_kwargs: None,
    });
    let outer = Rc::new(Expr::Name("outer".into()));
    // Assignment expressions exist since 3.8; this COPY-backed encoding
    // starts in 3.11. The bounded walker must preserve the binding in
    // `(state := get(entity_id))` while retaining unrelated stack entries.
    for minor in 11..=14 {
        let version = PythonVersion { minor, ..module.version() };
        let ctx = context(&module.code, version, vec![
            instruction(Op::COPY, 1), instruction(Op::STORE_FAST, 0),
        ]);
        let result = ctx.sim_stack_region(0, 2, vec![outer.clone(), value.clone()])
            .expect("COPY followed by STORE_FAST is an assignment expression");
        assert_eq!(result.len(), 2);
        assert!(Rc::ptr_eq(&result[0], &outer));
        match &*result[1] {
            Expr::Named { target, value: assigned } => {
                assert!(matches!(&**target, Expr::Name(name) if name == "state"));
                assert!(Rc::ptr_eq(assigned, &value));
            }
            other => panic!("expected a named expression, got {other:?}"),
        }
    }
}

#[test]
fn store_fast_rejects_separate_evaluations_and_standalone_assignments() {
    let module = fixture();
    let ctx = context(&module.code, module.version(),
        vec![instruction(Op::STORE_FAST, 0)]);
    let name = || Rc::new(Expr::Name("value".into()));
    // Equal syntax does not prove that the VM copied a single evaluation.
    for stack in [vec![], vec![name()], vec![name(), name()]] {
        assert!(ctx.sim_stack_region(0, 1, stack).is_none());
    }
}

fn nested_code(code: &CodeObject, name: &str) -> Rc<CodeObject> {
    code.consts.iter().find_map(|value| match &**value {
        PyObject::Code(code) if code.name == name => Some(code.clone()),
        _ => None,
    }).unwrap_or_else(|| panic!("missing code object {name}"))
}

#[test]
fn bounded_generator_regions_preserve_iterables_and_captured_cells() {
    for minor in 13..=15 {
        let path = format!("{}/tests/pyc/bounded_generator_expressions.3.{minor}.pyc",
                           env!("CARGO_MANIFEST_DIR"));
        let module = PycModule::from_bytes(&std::fs::read(path).unwrap()).unwrap();
        let version = module.version();
        for (name, expected) in [
            ("plain", "return collect((value for value in values))"),
            ("captured", "return collect((value + offset for value in values))"),
            ("multiple", "return collect(((value + first) * second for value in values))"),
        ] {
            let code = nested_code(&module.code, name);
            let instrs = crate::bytecode::decode_instructions(&code, table_for(version).unwrap(), version);
            let start = instrs.iter().position(|ins| ins.op == Op::LOAD_GLOBAL).unwrap();
            let end = instrs.iter().position(|ins| ins.op == Op::RETURN_VALUE).unwrap();
            let ctx = context(&code, version, instrs);
            let result = ctx.sim_stack_region(start, end, vec![])
                .unwrap_or_else(|| panic!("3.{minor} {name}: generator construction rejected"));
            assert_eq!(result.len(), 1, "3.{minor} {name}: {result:?}");
            let source = crate::codegen::generate(&[Stmt::Return(Some(result[0].clone()))], version, true);
            assert_eq!(source.trim(), expected, "3.{minor} {name}");
        }
        let ordinary = nested_code(&module.code, "ordinary_function");
        let instrs = crate::bytecode::decode_instructions(&ordinary, table_for(version).unwrap(), version);
        let start = instrs.iter().position(|ins| ins.op == Op::LOAD_CONST).unwrap();
        let end = instrs.iter().position(|ins| ins.op == Op::RETURN_VALUE).unwrap();
        let ctx = context(&ordinary, version, instrs);
        assert!(ctx.sim_stack_region(start, end, vec![]).is_none());
    }
}

#[test]
fn bounded_generator_construction_rejects_invalid_closure_slots() {
    let module = PycModule::from_bytes(include_bytes!(
        "../tests/pyc/bounded_generator_expressions.3.13.pyc")).unwrap();
    let parent = nested_code(&module.code, "captured");
    let generator = nested_code(&parent, "<genexpr>");
    assert_eq!(generator.freevars, ["offset"]);
    let constant = Rc::new(Expr::Const(Rc::new(PyObject::Code(generator))));
    let name = Rc::new(Expr::Name("offset".into()));
    for closure in [name.clone(), Rc::new(Expr::Tuple(vec![])),
                    Rc::new(Expr::Tuple(vec![name.clone(), name.clone()]))] {
        let ctx = context(&parent, module.version(), vec![
            instruction(Op::MAKE_FUNCTION, 0), instruction(Op::SET_FUNCTION_ATTRIBUTE, 8),
        ]);
        assert!(ctx.sim_stack_region(0, 2, vec![closure, constant.clone()]).is_none());
    }
    let ctx = context(&parent, module.version(), vec![
        instruction(Op::MAKE_FUNCTION, 0), instruction(Op::SET_FUNCTION_ATTRIBUTE, 8),
    ]);
    let result = ctx.sim_stack_region(0, 2,
        vec![Rc::new(Expr::Tuple(vec![name])), constant]).unwrap();
    assert!(matches!(&*result[0], Expr::Function(_)));
    let ctx = context(&parent, module.version(), vec![instruction(Op::GET_ITER, 0)]);
    assert!(ctx.sim_stack_region(0, 1, vec![]).is_none());
}

#[test]
fn expected_async_exit_underflow_preserves_prior_diagnostics() {
    let module = fixture();
    for minor in [14, 15] {
        for initial_clean in [true, false] {
            let mut next = instruction(Op::GET_AWAITABLE, 2);
            next.offset = 2;
            let mut ctx = context(&module.code, PythonVersion { minor, ..module.version() },
                vec![instruction(Op::CALL, 3), next]);
            ctx.idx_of.insert(0, 0);
            ctx.with_exits = 1;
            ctx.clean = initial_clean;
            ctx.stack = vec![Sv::E(Rc::new(Expr::Const(Rc::new(PyObject::None)))); 3];
            ctx.call_311(3, false);
            assert!(ctx.with_exit_await_drop);
            assert_eq!(ctx.clean, initial_clean, "prior diagnostics must survive");
            assert_eq!(ctx.with_exits, 0);
        }
        for (argc, awaited) in [(2, true), (3, false)] {
            let mut next = instruction(if awaited { Op::GET_AWAITABLE } else { Op::POP_TOP }, 2);
            next.offset = 2;
            let mut ctx = context(&module.code, PythonVersion { minor, ..module.version() },
                vec![instruction(Op::CALL, argc as u32), next]);
            ctx.idx_of.insert(0, 0);
            ctx.with_exits = 1;
            ctx.stack = vec![Sv::E(Rc::new(Expr::Const(Rc::new(PyObject::None)))); argc];
            ctx.call_311(argc, false);
            assert!(!ctx.clean, "only the exact three-None async exit forgives its absent callable");
        }
    }
}

#[test]
fn nested_context_return_matcher_requires_complete_exit_groups_and_slots() {
    let module = fixture();
    let none = module.code.consts.iter().position(|o| matches!(&**o, PyObject::None)).unwrap() as u32;
    for minor in 11..=15 {
        for groups in [1, 2, 3] {
            let mut instrs = Vec::new();
            for _ in 0..groups {
                instrs.extend([
                    instruction(Op::SWAP, 3), instruction(Op::SWAP, 2),
                    instruction(Op::LOAD_CONST, none), instruction(Op::LOAD_CONST, none),
                    instruction(Op::LOAD_CONST, none), instruction(Op::CALL, 3),
                    instruction(Op::POP_TOP, 0),
                ]);
            }
            instrs.push(instruction(Op::RETURN_VALUE, 0));
            for (i, inst) in instrs.iter_mut().enumerate() { inst.offset = i * 2; }
            let end = instrs.last().unwrap().end();
            let mut ctx = context(&module.code, PythonVersion { minor, ..module.version() }, instrs);
            ctx.with_exits = groups;
            assert_eq!(ctx.with_return_tail_info(0), Some((end, groups)));
            if groups > 1 {
                ctx.with_exits = groups - 1;
                assert!(ctx.with_return_tail_info(0).is_none(), "must not consume unknown exits");
                ctx.with_exits = groups;
                ctx.instrs[8].arg = 1;
                assert!(ctx.with_return_tail_info(0).is_none(), "second SWAP pair must be exact");
                ctx.instrs[8].arg = 2;
                ctx.instrs[13].op = Op::NOP;
                assert!(ctx.with_return_tail_info(0).is_none(), "each exit must discard its call result");
            }
        }
    }
}

#[test]
fn normal_async_exit_spans_recognize_actual_suspension_protocols() {
    for minor in [14, 15] {
        let path = format!("{}/tests/pyc/normal_async_exits.3.{minor}.pyc", env!("CARGO_MANIFEST_DIR"));
        let module = PycModule::from_bytes(&std::fs::read(path).unwrap()).unwrap();
        let code = nested_code(&module.code, "normal_1");
        let version = module.version();
        let instrs = crate::bytecode::decode_instructions(&code, table_for(version).unwrap(), version);
        let mut ctx = context(&code, version, instrs);
        ctx.idx_of = ctx.instrs.iter().enumerate().map(|(i, x)| (x.offset, i)).collect();
        let starts: Vec<_> = ctx.instrs.windows(3).enumerate()
            .filter(|(_, group)| group.iter().all(|x| ctx.loads_none(x.op, x.arg)))
            .map(|(i, group)| (i, group[0].offset)).collect();
        assert_eq!(starts.len(), 2);
        for (i, off) in starts {
            assert!(ctx.inline_with_exit_span(off).is_some(), "3.{minor} exit at {off}: {:?}", &ctx.instrs[i..i+16]);
        }
    }
}

#[test]
fn async_normal_exit_rejects_user_awaits_broken_loops_and_return_tails() {
    for minor in [14, 15] {
        let path = format!("{}/tests/pyc/normal_async_exits.3.{minor}.pyc", env!("CARGO_MANIFEST_DIR"));
        let module = PycModule::from_bytes(&std::fs::read(path).unwrap()).unwrap();
        let code = nested_code(&module.code, "normal_1");
        let version = module.version();
        let instrs = crate::bytecode::decode_instructions(&code, table_for(version).unwrap(), version);
        let make = |instrs| {
            let mut ctx = context(&code, version, instrs);
            ctx.idx_of = ctx.instrs.iter().enumerate().map(|(i, x)| (x.offset, i)).collect();
            ctx
        };
        let ctx = make(instrs.clone());
        let start = ctx.instrs.windows(3).position(|group| group.iter().all(|x| ctx.loads_none(x.op, x.arg))).unwrap();
        let off = ctx.instrs[start].offset;
        let after = ctx.inline_with_exit_span(off).unwrap();
        let end = ctx.idx_of[&after];
        for mutation in 0..4 {
            let mut bad = instrs.clone();
            let span = &mut bad[start..end];
            match mutation {
                0 => span.iter_mut().find(|x| x.op == Op::GET_AWAITABLE).unwrap().arg = 0,
                1 => span.iter_mut().find(|x| x.op == Op::JUMP_BACKWARD_NO_INTERRUPT).unwrap().target = Some(off),
                2 => span.iter_mut().find(|x| x.op == Op::END_SEND).unwrap().op = Op::NOP,
                _ => span.iter_mut().find(|x| x.op == Op::RESUME).unwrap().op = Op::LOAD_GLOBAL,
            }
            assert!(make(bad).inline_with_exit_span(off).is_none(), "3.{minor}: mutation {mutation}");
        }
        for padding in [0, 1, 3, 9] {
            for constant in [false, true] {
                let mut tail = instrs[..end].to_vec();
                tail.extend((0..padding).map(|_| instruction(Op::NOP, 0)));
                if constant {
                    tail.push(instruction(Op::LOAD_SMALL_INT, 4));
                    tail.extend((0..padding).map(|_| instruction(Op::NOP, 0)));
                }
                tail.push(instruction(Op::RETURN_VALUE, 0));
                for (i, item) in tail[end..].iter_mut().enumerate() { item.offset = after + i * 2; }
                assert!(make(tail).inline_with_exit_span(off).is_none(), "3.{minor}: carried return with {padding} pads");
            }
        }
    }
}

#[test]
fn async_exit_ownership_preserves_displaced_and_nested_slots() {
    for minor in [14, 15] {
        let path = format!("{}/tests/pyc/normal_async_exits.3.{minor}.pyc", env!("CARGO_MANIFEST_DIR"));
        let module = PycModule::from_bytes(&std::fs::read(path).unwrap()).unwrap();
        let code = nested_code(&module.code, "normal_1");
        let version = module.version();
        let instrs = crate::bytecode::decode_instructions(&code, table_for(version).unwrap(), version);
        let mut ctx = context(&code, version, instrs);
        ctx.idx_of = ctx.instrs.iter().enumerate().map(|(i, x)| (x.offset, i)).collect();
        ctx.cur_offset = ctx.instrs.windows(3).find(|group| group.iter().all(|x| ctx.loads_none(x.op, x.arg))).unwrap()[0].offset;
        let after = ctx.inline_with_exit_span(ctx.cur_offset).unwrap();
        assert!(ctx.owned_inline_with_exit_span().is_some());
        ctx.exc_entries.push(crate::code::ExceptionEntry { start: ctx.cur_offset, end: after, target: 999, depth: 2, lasti: true });
        ctx.with_region_handlers.insert(1, 999);
        assert!(ctx.owned_inline_with_exit_span().is_none(), "lost Try and With must retain the protected exit");
        ctx.blocks.push(Block::new(BlockType::Try, 0, after));
        assert!(ctx.owned_inline_with_exit_span().is_none(), "a displaced Try has no owning With");
        let mut owner = Block::new(BlockType::With, 0, after);
        owner.with_handler = Some(999);
        ctx.blocks.push(owner);
        assert!(ctx.owned_inline_with_exit_span().is_none(), "the open owner's handler protects an inner exit");
        ctx.blocks.last_mut().unwrap().with_handler = Some(1001);
        assert!(ctx.owned_inline_with_exit_span().is_some());
        ctx.blocks.remove(1);
        assert!(ctx.owned_inline_with_exit_span().is_some(), "ordinary open-With walks keep their exit handling");
    }
}

#[test]
fn following_exception_clauses_require_bounded_typed_mismatch_protocols() {
    let module = fixture();
    let build = |mut prefix: Vec<Instruction>, jump_op, forward| {
        prefix.push(instruction(Op::CHECK_EXC_MATCH, 0));
        let mut jump = instruction(jump_op, 0);
        jump.target = Some(if forward { 1000 } else { 0 });
        prefix.push(jump);
        for (i, x) in prefix.iter_mut().enumerate() { x.offset = i * 2; }
        let mut ctx = context(&module.code, module.version(), prefix);
        ctx.idx_of = ctx.instrs.iter().enumerate().map(|(i, x)| (x.offset, i)).collect();
        ctx
    };
    for prefix in [
        vec![instruction(Op::LOAD_GLOBAL, 0)],
        vec![instruction(Op::LOAD_NAME, 0)],
        vec![instruction(Op::LOAD_FAST, 0), instruction(Op::LOAD_ATTR, 0)],
        vec![instruction(Op::LOAD_DEREF, 0), instruction(Op::LOAD_ATTR, 0)],
        vec![instruction(Op::LOAD_GLOBAL, 0), instruction(Op::LOAD_GLOBAL, 1), instruction(Op::BUILD_TUPLE, 2)],
    ] {
        let ctx = build(prefix.clone(), Op::POP_JUMP_IF_FALSE, true);
        assert_eq!(ctx.following_except_clause_end(0), Some(ctx.instrs.last().unwrap().end()));
        assert!(build(prefix.clone(), Op::POP_JUMP_IF_FALSE, false).following_except_clause_end(0).is_none());
        assert!(build(prefix, Op::POP_JUMP_IF_TRUE, true).following_except_clause_end(0).is_none());
    }
    for barrier in [Op::PUSH_EXC_INFO, Op::POP_EXCEPT, Op::RERAISE, Op::CALL, Op::JUMP_FORWARD] {
        let ctx = build(vec![instruction(Op::LOAD_GLOBAL, 0), instruction(barrier, 0)], Op::POP_JUMP_IF_FALSE, true);
        assert!(ctx.following_except_clause_end(0).is_none(), "must stop at {barrier:?}");
    }
    let ctx = build(vec![instruction(Op::NOP, 0); 32], Op::POP_JUMP_IF_FALSE, true);
    assert!(ctx.following_except_clause_end(0).is_none());
}

#[test]
fn bounded_mapping_preserves_pair_order_prefix_and_rejects_underflow() {
    let module = fixture();
    let values: Vec<_> = ["prefix", "key0", "value0", "key1", "value1"].iter()
        .map(|name| Rc::new(Expr::Name((*name).into()))).collect();
    for minor in 8..=15 {
        let version = PythonVersion { minor, ..module.version() };
        let ctx = context(&module.code, version, vec![instruction(Op::BUILD_MAP, 2)]);
        let result = ctx.sim_stack_region(0, 1, values.clone()).unwrap();
        assert_eq!(result.len(), 2);
        assert!(Rc::ptr_eq(&result[0], &values[0]));
        let Expr::Dict(pairs) = &*result[1] else { panic!("expected dictionary"); };
        assert_eq!(pairs.len(), 2);
        for (i, (key, value)) in pairs.iter().enumerate() {
            assert!(Rc::ptr_eq(key, &values[1 + 2 * i]));
            assert!(Rc::ptr_eq(value, &values[2 + 2 * i]));
        }
        assert!(ctx.sim_stack_region(0, 1, values[..3].to_vec()).is_none());
        let empty = context(&module.code, version, vec![instruction(Op::BUILD_MAP, 0)]);
        let result = empty.sim_stack_region(0, 1, values[..1].to_vec()).unwrap();
        assert!(matches!(&*result[1], Expr::Dict(pairs) if pairs.is_empty()));
        let oversized = context(&module.code, version, vec![instruction(Op::BUILD_MAP, u32::MAX)]);
        assert!(oversized.sim_stack_region(0, 1, values.clone()).is_none());
    }
}

#[test]
fn bounded_formatting_preserves_conversions_and_dynamic_specs() {
    for minor in 13..=15 {
        let path = format!("{}/tests/pyc/bounded_formatting.3.{minor}.pyc", env!("CARGO_MANIFEST_DIR"));
        let module = PycModule::from_bytes(&std::fs::read(path).unwrap()).unwrap();
        let version = module.version();
        for (name, expected) in [
            ("simple", "return f'{value}'"),
            ("conversions", "return f'{label!r}: {value!s:>{width}}'"),
            ("ascii_spec", "return f'{label!a}: {value:{width}}'"),
        ] {
            let code = nested_code(&module.code, name);
            let instrs = crate::bytecode::decode_instructions(&code, table_for(version).unwrap(), version);
            let start = instrs.iter().position(|ins| ins.op == Op::RESUME).unwrap() + 1;
            let end = instrs.iter().position(|ins| ins.op == Op::RETURN_VALUE).unwrap();
            let ctx = context(&code, version, instrs);
            let prefix = Rc::new(Expr::Name("prefix".into()));
            let result = ctx.sim_stack_region(start, end, vec![prefix.clone()]).unwrap();
            assert_eq!(result.len(), 2, "3.{minor}: {name}");
            assert!(Rc::ptr_eq(&result[0], &prefix));
            let source = crate::codegen::generate(&[Stmt::Return(Some(result[1].clone()))], version, true);
            assert_eq!(source.trim(), expected, "3.{minor}: {name}");
        }
    }
}

#[test]
fn bounded_formatting_rejects_invalid_conversion_parts_and_missing_operands() {
    let module = fixture();
    let value = Rc::new(Expr::Name("value".into()));
    for minor in 13..=15 {
        let version = PythonVersion { minor, ..module.version() };
        for (op, arg, stack) in [
            (Op::CONVERT_VALUE, 1, vec![]),
            (Op::CONVERT_VALUE, 0, vec![value.clone()]),
            (Op::CONVERT_VALUE, 4, vec![value.clone()]),
            (Op::FORMAT_SIMPLE, 0, vec![]),
            (Op::FORMAT_WITH_SPEC, 0, vec![]),
            (Op::FORMAT_WITH_SPEC, 0, vec![value.clone()]),
            (Op::BUILD_STRING, 2, vec![value.clone()]),
            (Op::BUILD_STRING, 1, vec![value.clone()]),
            (Op::BUILD_STRING, 1, vec![Rc::new(Expr::Const(Rc::new(PyObject::Int(3))))]),
        ] {
            let ctx = context(&module.code, version, vec![instruction(op, arg)]);
            assert!(ctx.sim_stack_region(0, 1, stack).is_none(), "3.{minor}: {op:?} {arg}");
        }
        for (arg, conversion) in [(1, 's'), (2, 'r'), (3, 'a')] {
            let ctx = context(&module.code, version, vec![instruction(Op::CONVERT_VALUE, arg), instruction(Op::FORMAT_SIMPLE, 0)]);
            let result = ctx.sim_stack_region(0, 2, vec![value.clone()]).unwrap();
            assert_eq!(result.len(), 1);
            let Expr::FString(text) = &*result[0] else { panic!("expected f-string"); };
            assert!(matches!(&text.parts[..], [FStringPart::Value { conversion: Some(c), format_spec: None, .. }] if *c == conversion));
        }
    }
}

#[test]
fn shared_raise_regions_require_exact_operands_and_no_statements() {
    for minor in [14, 15] {
        let path = format!("{}/tests/pyc/shared_validation_raises.3.{minor}.pyc", env!("CARGO_MANIFEST_DIR"));
        let module = PycModule::from_bytes(&std::fs::read(path).unwrap()).unwrap();
        let version = module.version();
        for name in ["plain", "cause", "suppress"] {
            let code = nested_code(&module.code, name);
            let instrs = crate::bytecode::decode_instructions(&code, table_for(version).unwrap(), version);
            let first = instrs.iter().position(|item| item.op == Op::POP_JUMP_IF_NONE).unwrap();
            let target = instrs[first].target.unwrap();
            let terminal = instrs.iter().position(|item| item.op == Op::RAISE_VARARGS).unwrap();
            let mut ctx = context(&code, version, instrs);
            ctx.idx_of = ctx.instrs.iter().enumerate().map(|(i, x)| (x.offset, i)).collect();
            ctx.cur_offset = ctx.instrs[first].offset;
            let cond = Rc::new(Expr::Compare {
                operands: vec![Rc::new(Expr::Name("value".into())), Rc::new(Expr::Const(Rc::new(PyObject::None)))],
                ops: vec![CmpOp::Is],
            });
            let (_, body, _) = ctx.try_shared_rejection_guard(&cond, true, target).unwrap();
            assert!(matches!(&body[..], [Stmt::Raise { exc: Some(_), cause, .. }] if cause.is_some() == (name != "plain")));
            let original = ctx.instrs[terminal].arg;
            for arg in [0, 3, if original == 1 { 2 } else { 1 }] {
                ctx.instrs[terminal].arg = arg;
                assert!(ctx.try_shared_rejection_guard(&cond, true, target).is_none(), "3.{minor}: {name}, arg {arg}");
            }
            ctx.instrs[terminal].arg = original;
            let start = ctx.idx_of[&target];
            let original = ctx.instrs[start].op;
            for op in [Op::STORE_FAST, Op::POP_EXCEPT, Op::PUSH_EXC_INFO, Op::RERAISE] {
                ctx.instrs[start].op = op;
                assert!(ctx.try_shared_rejection_guard(&cond, true, target).is_none(), "3.{minor}: {name}, {op:?}");
            }
            ctx.instrs[start].op = original;
            ctx.stack.push(Sv::E(cond.clone()));
            assert!(ctx.try_shared_rejection_guard(&cond, true, target).is_none());
        }
    }
}

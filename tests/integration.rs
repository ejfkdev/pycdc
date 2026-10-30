//! Integration tests: decompile committed pyc fixtures (spanning Python 2.7
//! through 3.14) and assert the recovered source structure.

use pycdc::codegen::generate;
use pycdc::decompiler::decompile;
use pycdc::pyc::PycModule;

fn decompile_fixture(name: &str) -> (String, bool) {
    let path = format!("{}/tests/pyc/{}", env!("CARGO_MANIFEST_DIR"), name);
    let data = std::fs::read(&path).unwrap_or_else(|e| panic!("read {path}: {e}"));
    let module = PycModule::from_bytes(&data)
        .unwrap_or_else(|e| panic!("load {path}: {e}"));
    let d = decompile(&module.code, module.version())
        .unwrap_or_else(|e| panic!("decompile {path}: {e}"));
    let src = generate(&d.body, module.version(), d.clean);
    (src, d.clean)
}

fn assert_contains(haystack: &str, needles: &[&str], ctx: &str) {
    for n in needles {
        assert!(
            haystack.contains(n),
            "{ctx}: expected to find {n:?} in output:\n{haystack}"
        );
    }
}

#[test]
fn disjunction_inside_for_preserves_each_operand_and_else() {
    for version in ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("for_loop_disjunctions.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "for value in values:\n        if not test(value) or value < 0.2:",
                "for value in values:\n        if not value or value < 0.2:",
                "for value in values:\n        if value is None or value < 0.2:",
                "for value in values:\n        if test(value) or value < 0.2:",
                "else:\n            result.append('wet')",
                "while value < 2 or value == 3:",
                "result.append('complete')",
                "result.append('tail')",
            ],
            version,
        );
    }
}

#[test]
fn padded_none_return_does_not_absorb_a_following_branch() {
    for version in ["3.11", "3.12", "3.13", "3.14", "3.15"] {
        for padding in [0, 1, 3] {
            let (src, clean) = decompile_fixture(
                &format!("padded_none_returns_{padding}.{version}.pyc"));
            assert!(clean, "Python {version}, padding {padding}: incomplete:\n{src}");
            assert_contains(
                &src,
                &[
                    "try:\n            stamp = datetime.fromtimestamp(value, timezone.utc)",
                    "return stamp\n    if isinstance(value, str):",
                    "try:\n            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))",
                    "parsed.astimezone(timezone.utc)",
                    "def unprotected_return(read):",
                    "def else_return(read):",
                    "read('inside')",
                    "return read('outside')",
                ],
                version,
            );
        }
    }
}

#[test]
fn padded_return_consumes_the_existing_calculated_value_once() {
    for version in ["3.11", "3.12", "3.13", "3.14", "3.15"] {
        for padding in [1, 3, 9] {
            let (src, clean) = decompile_fixture(
                &format!("carried_value_returns_{padding}.{version}.pyc"));
            assert!(clean, "Python {version}, padding {padding}: incomplete:\n{src}");
            for value in ["make(value)", "make(value).result", "make(value), 7",
                          "{'value': make(value)}"] {
                assert!(src.contains(&format!("try:\n            return {value}\n")),
                        "Python {version}, padding {padding}: lost protected value {value}:\n{src}");
            }
            assert_eq!(src.matches("make(value)").count(), 5, "{version}: {src}");
            assert_eq!(src.matches("return fallback.read().result or default.result").count(), 5,
                       "{version}: {src}");
            assert_contains(&src, &["try:\n            make(value)\n", "return 'handled'"], version);
        }
    }
}

#[test]
fn bounded_try_return_keeps_its_handler_and_following_sibling() {
    for version in ["3.11", "3.12", "3.13", "3.14", "3.15"] {
        for padding in [0, 1, 3] {
            let (src, clean) = decompile_fixture(
                &format!("bounded_try_returns_{padding}.{version}.pyc"));
            assert!(clean, "Python {version}, padding {padding}: incomplete:\n{src}");
            assert_contains(&src, &[
                "try:\n            return datetime.fromtimestamp(value, timezone.utc)",
                "except (OverflowError, OSError, ValueError):\n            return\n    if isinstance(value, str):",
                "try:\n            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))",
                "parsed.astimezone(timezone.utc)",
                "def unprotected_return(read):", "def else_return(read):",
                "read('inside')", "return read('outside')",
            ], version);
            assert_eq!(src.matches("datetime.fromtimestamp(value, timezone.utc)").count(), 1,
                       "{version}: {src}");
        }
    }
}

#[test]
fn chained_comparison_ternaries_keep_collection_values_and_filters_distinct() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(
            &format!("comprehension_chained_ternaries.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "return {value: 1 if 6 <= value <= 8 else 0 for value in values}",
            "return {value if 6 <= value <= 8 else -value: value for value in values}",
            "return [0.6 + 0.4 * (1.0 if 4 <= value <= 8 < 10 else 0.3) for value in values]",
            "return [1 if value >= 6 else 0 for value in values if value <= 8]",
            "base(value) + coefficient(value) * (1.0 if lower() <= probe(value) <= upper() else 0.3)",
        ], version);
    }
}

#[test]
fn generator_statement_route_preserves_repeated_targets_and_closure_calls() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(
            &format!("generator_statement_reconstruction.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "value is not None for value, discarded, discarded, discarded in values",
            "(value, discarded, _) for value, _, discarded, discarded in values",
            "sum((value for value in row)) / len(row) for row in rows",
            "sum((factory(deltas) for _ in deltas)) / len(deltas) for _ in range(3)",
        ], version);
    }
}

#[test]
fn generator_statement_route_keeps_python312_multiline_filter_layout() {
    let (src, clean) = decompile_fixture("generator_multiline_filter_312.3.12.pyc");
    assert!(clean, "{src}");
    assert_contains(&src, &["value for value in values\n         if value not in excluded"],
                    "3.12 multiline filter");
}

#[test]
fn filtered_generators_keep_boolean_values_separate_from_rejection_guards() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(
            &format!("filtered_generator_boolean_values.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "row[1] or 0 for row in rows if row[0]",
            "row[1] and row[2] for row in rows if row[0]",
            "row[1] or row[2] or 0 for row in rows if row[0]",
            "row[1] and row[2] or 0 for row in rows if row[0]",
            "row.get('amount') or 0.0 for row in rows if row.get('amount') is not None",
        ], version);
    }
}

#[test]
fn generator_walrus_keeps_its_parent_cell_and_short_circuit_value() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("generator_walrus_cells.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "isinstance(row, dict) and (change := row.get('change')) is not None and change >= 0",
            "change = 'initial'", "return results, change",
        ], version);
        assert_eq!(src.matches("change :=").count(), 2, "{version}: {src}");
        assert!(!src.contains("nonlocal "), "{version}: declaration escaped its generator:\n{src}");
    }
}

#[test]
fn suspension_cleanup_does_not_split_async_with_exception_suites() {
    for version in ["3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("await_exception_regions.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "async with manager:\n        try:\n            await work('a')\n        finally:\n            record('cleanup')\n        await work('b')\n        return 'tail'",
            "async with manager:\n        try:\n            a = await work('a')\n        except ValueError:\n            record('handled')\n        else:\n            await work('b')\n        return 'tail'",
        ], version);
    }
}

#[test]
fn await_region_reconstruction_preserves_adjacent_contexts_and_outer_handlers() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("await_context_controls.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "async with manager:\n        a = await work('a')\n    async with manager:\n        b = await work('b')\n    return a, b",
            "try:\n        a = await work('a')\n        async with manager:",
            "try:\n        async with manager:\n            a = await work('a')\n            b = await work('b')",
            "except ValueError:\n        return 'handled'\n    return a, b",
        ], version);
    }
}

#[test]
fn early_context_returns_preserve_finally_and_remaining_exit_bookkeeping() {
    for version in ["3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("context_exit_accounting.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "async with manager:\n        if flag:\n            return 'early'\n        try:\n            return await work('a')\n        finally:\n            record('cleanup')",
            "async with manager:\n        try:\n            return await work('a')\n        finally:\n            record('cleanup')",
            "async with manager:\n        if flag is None:\n            return 3\n        try:\n            return await work('a')\n        finally:\n            record('cleanup')",
        ], version);
    }
}

#[test]
fn context_managers_keep_return_values_inside_the_body() {
    for version in ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("context_manager_returns.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "def synchronous(manager):\n    with manager as value:\n        return value",
            "def synchronous_attribute(manager):\n    with manager as value:\n        return value.result",
            "async def asynchronous(manager):\n    async with manager as value:\n        return value",
            "async def asynchronous_attribute(manager):\n    async with manager as value:\n        return value.result",
        ], version);
    }
}

#[test]
fn handler_loops_keep_computed_returns_inside_their_context() {
    for version in ["3.10", "3.11", "3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("loop_context_returns.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        for prefix in ["", "async "] {
            for (suffix, value) in [("value", "result"), ("length", "len(result)"),
                                    ("mapping", "{'rows': result}")] {
                let name = if prefix.is_empty() { "sync" } else { "async" };
                // 3.10 optimizes this final continue into the loop's fallthrough.
                let handler = if version == "3.10" && suffix == "value" { "pass" } else { "continue" };
                let expected = format!("{prefix}def {name}_{suffix}(lock, rows, parse):\n    {prefix}with lock:\n        result = []\n        for row in rows:\n            try:\n                result.append(parse(row))\n            except ValueError:\n                {handler}\n        return {value}");
                assert!(src.contains(&expected), "Python {version}: {expected} missing:\n{src}");
            }
        }
    }
}

#[test]
fn sunk_early_context_exits_leave_the_normal_exit_available() {
    for version in ["3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("sunk_context_exits.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "if pending:\n            return False\n    record('outside')",
            "if pending:\n            return\n    record('outside')",
            "if pending:\n            return False\n        if release:\n            return False\n    record('outside')",
            "if pending:\n            return release\n    record('outside')",
            "await user_call(None, None, None)\n    record('outside')",
            "record('ready')\n    record('outside')",
        ], version);
        assert!(!src.contains("await None("), "Python {version}: leaked exit call:\n{src}");
    }
}

#[test]
fn nested_contexts_carry_one_return_through_every_exit() {
    for version in ["3.11", "3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("nested_context_returns.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "with contexts[0]:\n        with contexts[1]:\n            return value()",
            "with contexts[0]:\n        with contexts[1]:\n            with contexts[2]:\n                return {'rows': value()}",
            "async with contexts[0]:\n        async with contexts[1]:\n            return value()",
            "async with contexts[0]:\n        async with contexts[1]:\n            async with contexts[2]:\n                return await value()",
            "async with contexts[0]:\n        async with contexts[1]:\n            return (value(),)",
            "async with contexts[0]:\n        return await value()",
            "result = value()\n        return result",
            "result = await value()\n        return result",
        ], version);
    }
}

#[test]
fn per_row_handlers_remain_owned_by_their_loop_and_outer_try() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("loop_handler_ownership.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "try:\n        for row in owner.rows:\n            try:\n                owner.record(row)\n            except ValueError as error:",
            "            except KeyError as error:\n                owner.other(row, str(error))",
            "            try:\n                owner.second(row)\n            except KeyError:",
            "            except Exception:\n                owner.failed(row)",
            "        owner.finish()\n    except RuntimeError as error:",
            "        owner.finish()\n    except Exception as error:",
            "                await owner.arecord(row)\n                await owner.asecond(row)\n            except ValueError:",
            "    finally:\n        owner.finish()",
            "def nonloop(owner):\n    try:\n        try:\n            owner.record(owner.row)",
            "        except ValueError:\n            owner.failed(owner.row)",
        ], version);
        // The compiler may sink implicit None returns into either arm.
        let nonloop = src.split("def nonloop(owner):").nth(1).unwrap();
        assert!(nonloop.contains("    except RuntimeError:\n        owner.fallback()"), "{src}");
    }
}

#[test]
fn normal_async_exits_close_only_their_own_context() {
    for version in ["3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("normal_async_exits.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "row0 = await query.read()\n    value = owner.build(row0, row0)",
            "row3 = await query.read()\n    value = owner.build(row0, row3)",
            "row0 = await query.read()\n        async with owner.query('row1') as query:",
            "row0 = await query.read()\n        return 4",
            "row0 = await query.read()\n        return row0",
            "row1 = await query.read()\n        return owner.build(row0, row0)",
            "row1 = await query.read()\n        return {'value': row0}",
            "await owner.user(None, None, None)\n        return owner.build(1, 2)",
            "if owner.ready:\n            return 4\n        await owner.write(1, 2)\n    return 2",
        ], version);
    }
}

#[test]
fn async_return_padding_never_turns_a_carried_exit_into_a_normal_exit() {
    for version in ["3.14", "3.15"] {
        for padding in [1, 3, 9] {
            let (src, clean) = decompile_fixture(&format!("async_context_return_padding_{padding}.{version}.pyc"));
            assert!(clean, "Python {version}, padding {padding}: incomplete:\n{src}");
            assert_contains(&src, &[
                "row0 = await query.read()\n        return 4",
                "row0 = await query.read()\n        return {'value': row0}",
            ], version);
        }
    }
}

#[test]
fn private_handler_bodies_do_not_hide_later_typed_clauses() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("private_handler_clauses.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "except RuntimeError as inner:\n                    await owner.log('close-failed', str(inner))",
            "        except ValueError as error:\n            await owner.log('invalid', str(error))",
            "        except (OSError, asyncio.TimeoutError) as error:\n            await owner.log('transient', str(error))",
            "        except Exception as error:\n            await owner.log('unavailable', str(error))",
            "        except ValueError as error:\n            owner.log('invalid', str(error))",
            "        except faults.invalid as error:",
            "        except (faults.operating, faults.timeout) as error:",
            "        except faults.ordinary as error:",
            "    await owner.log('finished', accepted)\n    return accepted",
            "async def single_clause(owner):", "async def no_private_try(owner):",
        ], version);
        assert_eq!(src.matches("except (faults.operating, faults.timeout)").count(), 2);
    }
}

#[test]
fn handler_iterator_disposal_preserves_break_and_post_loop_work() {
    for version in ["3.12", "3.13", "3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("handler_iterator_breaks.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "except (OSError, asyncio.TimeoutError) as error:\n            await owner.log('transient', str(error))\n            break",
            "except Exception as error:\n            await owner.log('unavailable', str(error))\n            break",
            "except (OSError, asyncio.TimeoutError) as error:\n            owner.log('transient', str(error))\n            break",
            "except (OSError, asyncio.TimeoutError):\n            await owner.log('transient', 'owned fault')\n            break",
            "except Exception:\n            await owner.log('unavailable', 'owned fault')\n            break",
            "    await owner.log('finished', accepted)\n    return accepted",
            "    owner.log('finished', accepted)\n    return accepted",
        ], version);
        assert_eq!(src.matches("\n            break").count(), 10, "Python {version}: {src}");
    }
}

#[test]
fn py27_if_elif_else() {
    let (src, clean) = decompile_fixture("if_elif_else.2.7.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(
        &src,
        &[
            "def test(msgtype, flags):",
            "if flags == 1:",
            "elif flags == 2:",
            "elif flags == 3:",
            "return msgtype",
        ],
        "py2.7 if/elif",
    );
}

#[test]
fn py27_constants() {
    let (src, clean) = decompile_fixture("simple_const.2.7.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(
        &src,
        &[
            "a = 42",
            "b = 3.14159",
            "c = 'test'",
            "d = (1, 2)",
            "e = (3,)",
            "f = [1, 2]",
            "g = {'key': 42}",
        ],
        "py2.7 constants",
    );
}

#[test]
fn py27_list_comprehension() {
    let (src, _) = decompile_fixture("test_listComprehensions.2.7.pyc");
    assert_contains(&src, &["[i for i in XXX]"], "py2.7 inline listcomp");
}

#[test]
fn py27_ternary() {
    let (src, _) = decompile_fixture("conditional_expressions_py2.2.7.pyc");
    assert_contains(
        &src,
        &["result = 'even' if a % 2 == 0 else 'odd'"],
        "py2.7 ternary",
    );
}

#[test]
fn py39_basics() {
    let (src, clean) = decompile_fixture("basics.3.9.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(
        &src,
        &[
            "a, (c, d2) = 1, (2, 3)",
            "x += 1",
            "z = x if x > 5 else y",
            "v = 1 < x < 100",
            "elif x > 10:",
            "while i < 10:",
            "continue",
            "break",
            "for item in l:",
            "for k, val in d.items():",
        ],
        "py3.9 basics",
    );
}

#[test]
fn py310_basics() {
    let (src, clean) = decompile_fixture("basics.3.10.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(&src, &["while i < 10:", "v = 1 < x < 100"], "py3.10 basics");
}

#[test]
fn assignment_identity() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("assignment_identity.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "def separate(read):\n    left, right = read(), read()\n    return left, right",
                "def shared(read):\n    left = right = read()\n    return left, right",
                "def separate_none():\n    left, right = None, None\n    return left, right",
                "def shared_none():\n    right = left = None\n    return left, right",
            ],
            &fixture,
        );
        assert_eq!(src.matches("read()").count(), 3, "{fixture}:\n{src}");
    }
}

#[test]
fn py311_comprehensions() {
    let (src, clean) = decompile_fixture("comprehensions.3.11.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(
        &src,
        &[
            "sq = [x * x for x in nums]",
            "ev = [x for x in nums if x % 2 == 0]",
            "[(x, y) for x in nums for y in nums if x != y]",
            "s = {x * 2 for x in nums}",
            "d = {x: x * x for x in nums}",
            "[[y for y in row] for row in ([1, 2], [3, 4])]",
        ],
        "py3.11 comprehensions",
    );
}

#[test]
fn py312_hello() {
    let (src, clean) = decompile_fixture("hello.3.12.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(
        &src,
        &[
            "import os",
            "import sys",
            "class Greeter:",
            "'''Greets people.'''",
            "def __init__(self, name):",
            "self.name = name",
            "def greet(self, times=1):",
            "for i in range(times):",
            "def fib(n):",
            "a, b = 0, 1",
            "while a < n:",
            "a, b = b, a + b",
            "data = {'x': [1, 2, 3], 'y': {4, 5}}",
            "if len(data['x']) > 2:",
            "else:",
        ],
        "py3.12 hello",
    );
}

#[test]
fn assignment_chains() {
    // 3.13 introduces fused stores; older fixtures check COPY-only chains.
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("assignment_chains.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        for (name, names) in [
            ("three", &['a', 'b', 'c'][..]),
            ("four", &['a', 'b', 'c', 'd'][..]),
            ("five", &['a', 'b', 'c', 'd', 'e'][..]),
            ("six", &['a', 'b', 'c', 'd', 'e', 'f'][..]),
        ] {
            let names: Vec<String> = names.iter().map(char::to_string).collect();
            let targets = names.join(" = ");
            let values = names.join(", ");
            assert_contains(
                &src,
                &[
                    &format!("def {name}(read):\n    {targets} = read()\n    return {values}"),
                    &format!("def {name}_none():\n    {targets} = None\n    return {values}"),
                ],
                &fixture,
            );
        }
        assert_eq!(src.matches("read()").count(), 4, "{fixture}:\n{src}");
    }
}

#[test]
fn py313_hello() {
    let (src, clean) = decompile_fixture("hello.3.13.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(&src, &["class Greeter:", "while a < n:", "a, b = b, a + b"], "py3.13 hello");
}

#[test]
fn generator_expanded_calls() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("generator_expanded_calls.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "def positional(rows, factory):\n    return tuple((factory(*row) for row in rows))",
                if version == "3.11" {
                    "def keywords(rows, factory):\n    return tuple((factory(*(), **{**dict(row)}) for row in rows))"
                } else {
                    "def keywords(rows, factory):\n    return tuple((factory(**dict(row)) for row in rows))"
                },
                if version == "3.11" {
                    "def both(rows, factory):\n    return tuple((factory(*row[0], **{**row[1]}) for row in rows))"
                } else {
                    "def both(rows, factory):\n    return tuple((factory(*row[0], **row[1]) for row in rows))"
                },
            ],
            &fixture,
        );
        assert_eq!(src.matches("factory(").count(), 3, "{fixture}:\n{src}");
    }
}

#[test]
fn py314_hello() {
    // 3.14 is brand new; accept incomplete-marker output as long as the
    // structure is recovered
    let (src, _clean) = decompile_fixture("hello.3.14.pyc");
    assert_contains(
        &src,
        &["class Greeter:", "for i in range(times):", "while a < n:"],
        "py3.14 hello",
    );
}

#[test]
fn sequential_generator_handlers_keep_the_shared_mainline() {
    // CALL_INTRINSIC_1 3 starts in 3.12; 3.11 has no frame-wide handler.
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(
            &format!("sequential_generator_handlers.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        let body = "    try:\n        yield work('first')\n    except ValueError:\n        yield 2\n    yield 3\n    try:\n        yield work('last')\n    except KeyError:\n        yield 5\n    yield 6";
        for definition in ["def synchronous(work):", "async def asynchronous(work):"] {
            let expected = format!("{definition}\n{body}");
            assert_contains(&src, &[&expected], version);
        }
        assert!(!src.contains("else:"), "Python {version}: spurious handler else:\n{src}");
    }
}

#[test]
fn empty_defaults_keep_the_comprehension_level() {
    // PEP 709 inlining starts in 3.12; retain the 3.11 compatibility case.
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("comprehension_default_arguments.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        for (name, expression) in [
            ("list_default", "[field for row in rows for field in row.get('values', [])]"),
            ("set_default", "{field for row in rows for field in row.get('values', {})}"),
            ("dict_default", "{field: len(field) for row in rows for field in row.get('values', {})}"),
            ("nested_list", "[[field for field in row.get('values', [])] for row in rows]"),
            ("nested_set", "[{field for field in row.get('values', {})} for row in rows]"),
            ("nested_dict", "[{field: len(field) for field in row.get('values', {})} for row in rows]"),
            ("subscript", "[field for row in rows for field in row['values']]"),
            ("no_default", "[field for row in rows for field in row.get('values')]"),
            ("tuple_default", "[field for row in rows for field in row.get('values', ())]"),
        ] {
            let expected = format!(
                "def {name}(rows):\n    row = 'saved-row'\n    field = 'saved-field'\n    result = {expression}\n    return result, row, field");
            assert_contains(&src, &[&expected], version);
        }
    }
}

#[test]
fn unpacked_targets_keep_iterator_cleanup_and_saved_locals() {
    // PEP 709 inlining starts in 3.12; retain the 3.11 compatibility case.
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("unpacked_comprehension_cleanup.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        for (name, expression) in [
            ("unpack4", "[a + b + c + d for rows in groups for a, b, c, d in rows]"),
            ("unpack_list", "[(a, c) for a, b in groups for c, d in b]"),
            ("unpack_set", "{(a, c) for a, b in groups for c, d in b}"),
            ("unpack_dict", "{a: c for a, b in groups for c, d in b}"),
            ("unpack6", "[(a, c, e) for a, b in groups for c, d in b for e, f in d]"),
            ("simple", "[(a, c) for a in groups for c in a]"),
            ("mixed", "[(a, c) for key, a in groups for c in a]"),
            ("mixed_inner", "[(a, c) for a in groups for key, c in a]"),
        ] {
            let expected = format!(
                "def {name}(groups):\n    a, b, c, d, e, f = 10, 20, 30, 40, 50, 60\n    result = {expression}\n    after = 0\n    for number in (1, 2, 3):\n        after += number\n    return result, (a, b, c, d, e, f), after");
            assert_contains(&src, &[&expected], version);
        }
    }
}

#[test]
fn padded_handler_returns_keep_false_before_the_success_tail() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        for padding in [1, 3, 9] {
            let (src, clean) = decompile_fixture(
                &format!("handler_return_padding_{padding}.{version}.pyc"));
            assert!(clean, "Python {version}, {padding} NOPs: incomplete:\n{src}");
            assert_contains(&src, &[
                "async def handled(read, log):\n    try:\n        await read()\n        log('saved')\n    except ValueError:\n        log('locked')\n        return False\n    except Exception as error:\n        log('failed', error)\n        return False\n    return True",
            ], version);
        }
    }
}

#[test]
fn large_dictionary_displays_remain_comprehension_elements() {
    // CPython 3.10 starts using MAP_ADD 1 for large displays. Before 3.12,
    // list comprehensions also use the separate code-object walker.
    for version in ["3.10", "3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(
            &format!("comprehension_dictionary_displays.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        for size in [17, 20] {
            let fields = (0..size).map(|index| format!("'k{index}': row + {index}"))
                .collect::<Vec<_>>().join(", ");
            for (name, open, close) in [("list", "[", "]"), ("generator", "(", ")")] {
                let expected = format!(
                    "def {name}{size}(rows):\n    return {open}{{{fields}}} for row in rows{close}");
                assert_contains(&src, &[&expected], version);
            }
        }
        assert_contains(&src, &[
            "def dictionary_comprehension(rows):\n    return {row: row + 1 for row in rows}",
            "def small_display(rows):\n    return [{'value': row} for row in rows]",
        ], version);
    }
}

#[test]
fn extended_loop_prefix_preserves_handler_continue() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("extended_loop_prefix.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        for count in [1, 30, 60] {
            let body = "            work(row)\n".repeat(count);
            let expected = format!(
                "def size_{count}(rows, work):\n    result = []\n    for row in rows:\n        try:\n{body}        except ValueError:\n            continue\n        result.append(row)");
            assert_contains(&src, &[&expected], version);
        }
    }
}

#[test]
fn conditional_loop_prefix_keeps_both_arms_inside_loop() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("conditional_loop_prefix.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        let args = "row.ok, row.a, row.b, row.c, row.d, row.e, row.f, row.g, row.h, row.i, row.j, row.k, row.l";
        let file_condition = if version == "3.12" { "" } else { "not " };
        let directory_condition = if version == "3.11" { "elif not" } else { "if" };
        assert_contains(
            &src,
            &[
                &format!("    for row in rows:\n        if row.is_file:\n            if {file_condition}work('file', {args}):"),
                &format!("        {directory_condition} work('directory', {args}):"),
                "    return success",
            ],
            version,
        );
        assert!(!src.contains("\n    success = False"), "Python {version}: failure assignment escaped the loop:\n{src}");
        if version == "3.13" || version == "3.14" {
            assert_contains(
                &src,
                &["                success = False\n                continue\n            continue"],
                version,
            );
        }
    }
}

#[test]
fn awaited_collections_use_synchronous_iteration() {
    for version in ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("awaited_synchronous_iteration.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        assert_contains(&src, &[
            r#"async def awaited(read):
    result = []
    for item in await read():
        result.append(item)
    return result"#,
            r#"async def asynchronous(read):
    result = []
    async for item in read():
        result.append(item)
    return result"#,
            r#"async def sync(read):
    result = []
    for item in read():
        result.append(item)
    return result"#,
        ], version);
    }
}

#[test]
fn real_value_build_still_matches_the_sunk_tail() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("sunk_value_return_control.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        assert_contains(&src, &[
            r#"def select(value):
    try:
        entry = value.entry
    except AttributeError:
        kind = 'missing'
    else:
        kind = 'present'
    return kind, value"#,
        ], version);
    }
}

#[test]
fn padding_does_not_match_a_mainline_value_build() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        for padding in [1, 3, 9] {
            let (src, clean) = decompile_fixture(
                &format!("padded_value_returns_{padding}.{version}.pyc"));
            assert!(clean, "Python {version}, {padding} NOPs: incomplete:\n{src}");
            assert_contains(&src, &[
                r#"def synchronous(read, build):
    try:
        item = read()
    except ValueError:
        return build('missing')
    return build(item)"#,
                r#"async def asynchronous(read, build):
    try:
        item = await read()
    except ValueError:
        return build('missing')
    return build(item)"#,
            ], version);
        }
    }
}

#[test]
fn finite_else_span_keeps_its_inner_guard() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("guarded_else_merge.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        assert_contains(&src, &[
            r#"async def awaited(owner):
    value = None
    active = owner.active
    if active:
        value = 1
    else:
        row = await owner.fetch()
        if row and row[0] is not None:
            value = float(row[0])
    owner.record(value)
    return value"#,
            r#"async def synchronous(owner):
    value = None
    active = owner.active
    if active:
        value = float(1)
    else:
        row = owner.fetch()
        if row and row[0] is not None:
            value = 2
    owner.record(value)
    return value"#,
            r#"async def attribute(owner):
    value = None
    active = owner.active
    if active:
        value = float(active['total'])
    else:
        row = owner.row
        if row and row[0] is not None:
            value = float(row[0])
    owner.record(value)
    return value"#,
            r#"async def following_else_work(owner):
    value = None
    active = owner.active
    if active:
        value = 1
    else:
        row = await owner.fetch()
        if row and row[0] is not None:
            value = 2
        owner.record('queried')
    owner.record(value)
    return value"#,
            r#"async def independent(owner):
    value = None
    row = None
    if owner.active:
        value = 1
    else:
        row = await owner.fetch()
    if row and row[0] is not None:
        value = 2
    return value"#,
        ], version);
    }
}

#[test]
fn split_exception_suites_generate_one_complete_try_statement() {
    use pycdc::ast::{ExceptHandler, Expr, Stmt};
    use pycdc::version::PythonVersion;
    use std::rc::Rc;
    let name = |value: &str| Rc::new(Expr::Name(value.into()));
    let inner = Stmt::Try {
        body: vec![Stmt::Expr(name("work")), Stmt::Expr(name("more_work"))],
        handlers: vec![ExceptHandler {
            type_: Some(name("ValueError")), name: Some(name("error")),
            body: vec![Stmt::Expr(name("handled"))], is_star: false,
        }],
        orelse: vec![], finalbody: vec![],
    };
    let outer = Stmt::Try {
        body: vec![inner.clone()], handlers: vec![],
        orelse: vec![Stmt::Expr(name("success"))],
        finalbody: vec![Stmt::Expr(name("cleanup")), Stmt::Expr(name("more_cleanup"))],
    };
    let module = PycModule::from_bytes(include_bytes!("pyc/hello.3.14.pyc")).unwrap();
    // Unified try/except/finally syntax starts in Python 2.5. The repair
    // concerns the recovered AST shape, rather than one opcode version.
    for (major, minor) in [(2, 5), (2, 7), (3, 8), (3, 11), (3, 12), (3, 13), (3, 14)] {
        let version = PythonVersion { major, minor, ..module.version() };
        let binding = if major == 2 { ", error" } else { " as error" };
        let expected = format!("try:\n    work\n    more_work\nexcept ValueError{binding}:\n    handled\nelse:\n    success\nfinally:\n    cleanup\n    more_cleanup\n");
        assert_eq!(generate(&[outer.clone()], version, true), expected);

        // A legitimate outer try/finally has no success suite to reunite.
        let nested = Stmt::Try {
            body: vec![inner.clone()], handlers: vec![], orelse: vec![],
            finalbody: vec![Stmt::Expr(name("cleanup"))],
        };
        let expected = format!("try:\n    try:\n        work\n        more_work\n    except ValueError{binding}:\n        handled\nfinally:\n    cleanup\n");
        assert_eq!(generate(&[nested], version, true), expected);
    }
}

#[test]
fn keyword_calls_survive_conditional_value_reconstruction() {
    for version in ["3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("keyword_conditional_calls.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        assert_contains(&src, &[
            r#"def case_0(value, build, other):
    return build('reject' if value else 'accept', amount=0)"#,
            r#"def case_1(value, build, other):
    return build('prefix', amount=0 if value else 1)"#,
            r#"def case_2(value, build, other):
    return build(0 if value else 1, amount=value)"#,
            r#"def case_9(value, build, other):
    return build('prefix', amount=1 if value else 2, last=other(value))"#,
            r#"def case_11(value, build, other):
    return other(build(amount=1) if value else build(amount=2, other=3))"#,
        ], version);
    }
}

#[test]
fn keyword_call_merge_does_not_hoist_an_arm_local_callable() {
    for version in ["3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("keyword_call_arm_boundary.{version}.pyc"));
        assert!(!clean, "Python {version}: an unproved call merge must remain incomplete:\n{src}");
        assert!(!src.contains("owner.build(amount=1 if value else 2)"),
            "Python {version}: callable resolution moved before the condition:\n{src}");
    }
}

#[test]
fn overwritten_unpack_slots_reuse_the_surviving_binding() {
    for version in ["3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("repeated_unpack_bindings.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        assert_contains(&src, &[
            r#"def repeated_loop(values):
    result = []
    for value, discarded, discarded, discarded in values:
        result.append(value is not None)
    return result"#,
            r#"def repeated_list(values):
    return [value is not None for value, discarded, discarded, discarded in values]"#,
            r#"def underscore_loop(values):
    result = []
    for value, _, discarded, discarded in values:
        result.append((value, discarded, _))
    return result"#,
            r#"def underscore_list(values):
    return [(value, discarded, _) for value, _, discarded, discarded in values]"#,
            r#"def nested_loop(values):
    result = []
    for value, (discarded, discarded) in values:
        result.append((value, discarded))
    return result"#,
            r#"def nested_list(values):
    return [(value, discarded) for value, (discarded, discarded) in values]"#,
        ], version);
    }
}

#[test]
fn slice_constants_preserve_axes_and_runtime_calls() {
    for version in ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"] {
        let (src, clean) = decompile_fixture(&format!("slice_constants_and_calls.{version}.pyc"));
        assert!(clean, "Python {version}: output marked incomplete:\n{src}");
        assert_contains(&src, &[
            r#"def dynamic_axes(data, stop):
    return data[:stop, :]"#,
            r#"def constant_axes(data, stop):
    return data[:, :]"#,
            r#"def mixed_axes(data, stop):
    return data[1:stop:2, :, 7]"#,
            r#"def call(data, stop):
    return data[slice(None, stop, None)]"#,
            r#"def call_axes(data, stop):
    return data[slice(None, stop, None), :]"#,
        ], version);
    }
}

#[test]
fn nested_conditional_comprehension_arms_keep_their_values() {
    for version in ["3.12", "3.13", "3.14"] {
        let fixture = format!("nested_conditional_elements.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "return [{'excluded': {'count': row['count'], 'reasons': loads(row['reasons']) if row['reasons'] else {}} if row['count'] is not None else {}, 'archived': str(row['archived']) if row['archived'] else None} for row in rows]",
                "return [build(1 if row.inner else 2) if row.outer else 3 for row in rows]",
                "return [1 if row.outer else build(2 if row.inner else 3) for row in rows]",
                "return [build(1 if row.inner is None else 2) if row.outer else build(3 if row.inner is not None else 4) for row in rows]",
            ],
            &fixture,
        );
    }
}

#[test]
fn chained_comprehension_filters_keep_each_polarity() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("chained_comprehension_filters.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        for (kind, open, close, element) in [
            ("list", "[", "]", "value"),
            ("set", "{", "}", "value"),
            ("dict", "{", "}", "value: value"),
        ] {
            for (polarity, negation) in [("positive", ""), ("negative", "not ")] {
                for join in ["separate", "joined"] {
                    let expected = format!(
                        "def {kind}_{polarity}_{join}(values):\n    return {open}{element} for value in values if {negation}isinstance(value, str) if value{close}"
                    );
                    assert_contains(&src, &[&expected], &fixture);
                }
            }
        }
        assert_contains(
            &src,
            &[
                "return [row.tag for row in rows if row.value == wanted if row.ready() if row.final()]",
                "return [row.tag for row in rows if row.value != wanted if not row.ready() if row.final()]",
            ],
            &fixture,
        );
        let normalized = src.split_whitespace().collect::<Vec<_>>().join(" ");
        assert_contains(
            &normalized,
            &["def broken_lines(values): return [value for value in values if isinstance(value, str) if value]"],
            &fixture,
        );
    }
}

#[test]
fn comprehension_boolean_values_remain_elements_not_filters() {
    for version in ["3.12", "3.13", "3.14"] {
        let fixture = format!("comprehension_boolean_values.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "return [max(0.0, float(row.get('x') or 0.0)) for row in rows]",
                "return [row[1] or 0 for row in rows]",
                "return [row[1] and 7 for row in rows]",
                "return {row[1] or 0 for row in rows}",
                "return {row[0]: row[1] and 7 for row in rows}",
                "return [row.first() or row.second() for row in rows]",
                "return [row.first() and row.second() for row in rows]",
                "return [row[1] for row in rows if row[0]]",
                "return [row[1] or 0 for row in rows if row[0]]",
                "return [row[1] if row[0] else 0 for row in rows]",
            ],
            &fixture,
        );
    }
}

#[test]
fn keyword_expansions_keep_merge_checks_and_dictionary_boundaries() {
    for version in ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("ordered_keyword_expansions.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "return fn(1, fixed=2, **first, **second)",
                "return fn(1, **first, **{'fixed': 2}, **second)",
                "return fn(1, **first, **second)",
                "return fn(1, **{'fixed': 2, **first, **second})",
                "return fn(1, **{'my col': 2, **first, **second})",
                "return fn(1, **{'class': 2, **first, **second})",
                "return fn(1, **{'fixed': 2, 'fixed': 3, **first, **second})",
                "return fn(1, fixed=2, **get_first(), **get_second())",
            ],
            &fixture,
        );
    }
}

#[test]
fn deferred_class_annotations_keep_registration_gates() {
    let fixture = "class_annotation_registration.3.14.pyc";
    let (src, clean) = decompile_fixture(fixture);
    assert!(clean, "output marked incomplete:\n{src}");
    assert!(src.starts_with("module_count: int = 5\n"), "{src}");
    assert_contains(
        &src,
        &[
            "class Always:",
            "'''Documented class.'''",
            "    if True:\n        amount: int = 3\n        label: str = 'ready'",
            "        if enabled:\n            if True:\n                label: str = 'ready'",
            "        for value in values:\n            if True:\n                limit: int = default(value)",
            "        for value in values:\n            if True:\n                amount: int = default(value)",
            "def read(self) -> int:",
        ],
        fixture,
    );
    assert!(!src.contains("__conditional_annotations__"), "{src}");
}

#[test]
fn nested_comprehensions_remain_generator_elements() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("nested_generator_comprehensions.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "return tuple(({key: row[key] for key in row} for row in rows))",
                "return tuple(([value * 2 for value in row] for row in rows))",
                "return tuple(({value * 2 for value in row} for row in rows))",
                "return tuple((collect([value * 2 for value in row]) for row in rows))",
                "return tuple(({key: row[key] for key in row if key} for row in rows if row))",
                "return tuple(({key: value for key, value in zip(columns, row) if key} for row in rows))",
            ],
            &fixture,
        );
    }
}

#[test]
fn boolean_value_chains_preserve_call_arguments_and_prefixes() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("boolean_call_arguments.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        assert_contains(
            &src,
            &[
                "return call(before(), first() and second() or last(), after())",
                "return call(value, value and second() or last(), after())",
                "return bool(a and b or c or d or e)",
                "return bool(c or d or a and b or e)",
                "return bool(a and a.get('available') or b or c or d or e)",
                "value = a and a.get('available') or b or c or d or e\n    return bool(value)",
                "return bool(a or b or c or d or e)",
                "return bool(a and b and c and d and e)",
                "return call(a and b or c, d if e else 0)",
            ],
            &fixture,
        );
    }
}

#[test]
fn independent_lookup_guards_keep_assignment_and_return_inside_the_loop() {
    for version in ["3.11", "3.12", "3.13", "3.14"] {
        let fixture = format!("loop_lookup_guards.{version}.pyc");
        let (src, clean) = decompile_fixture(&fixture);
        assert!(clean, "{fixture}: output marked incomplete:\n{src}");
        // The existing None-jump printer uses either equivalent spelling.
        let src = src.replace("not coordinator is not None", "coordinator is None");
        assert_contains(
            &src,
            &[
                "def rating_lookup(values):\n    for value in values:\n        if not value.rating < 10:\n            continue\n        coordinator = value.coordinator\n        if coordinator is None:\n            continue\n        return coordinator",
                "def dictionary_lookup(rows):\n    for row in rows:\n        if not isinstance(row, dict):\n            continue\n        coordinator = row.get('coordinator')\n        if coordinator is None:\n            continue\n        return coordinator",
                "def none_lookup(rows):\n    for row in rows:\n        if row is None:\n            continue\n        coordinator = row.coordinator\n        if coordinator is None:\n            continue\n        return coordinator",
                "return [row.get('coordinator') for row in rows if isinstance(row, dict)]",
            ],
            &fixture,
        );
        assert!(!src.contains("value.rating >="), "{fixture}: comparison inverted");
    }
}

#[test]
fn python315_shapes_recover_changed_encodings() {
    // 3.15 changed the inline-comprehension layout, IMPORT_NAME packing,
    // LOAD_COMMON_CONSTANT, yield-from, loop-return cleanup, genexpr
    // call slots and with as-targets. All of these are regressions that
    // the 3.14-only fixtures cannot see.
    let (src, clean) = decompile_fixture("python315_shapes.3.15.pyc");
    assert!(clean, "3.15 shapes: output marked incomplete:\n{src}");
    assert_contains(
        &src,
        &[
            "import os.path",
            "from os.path import join",
            "[x * 2 for x in xs], {x for x in xs}, {x: x + 1 for x in xs}",
            "fn(x, alphas=1, X_test=x, mode=2, max_iter=int(",
            "fn(x, x if x > 1 else 0)",
            "if not any((s in p for s in ['.a', '.b']))",
            "tuple((tuple((s for s in row)) for row in rows))",
            "for i in range(3):",
            "return 'hit%d' % i",
            "yield from xs",
            "if v is True:",
            "if v is False:",
            "if v is None:",
            "return -1",
            "with ctx as holder.value:",
            "with ctx as holder['k']:",
        ],
        "3.15 shapes",
    );
    assert!(!src.contains("/*with-result*/"), "unresolved with target:\n{src}");
    assert!(!src.contains('\0'), "PUSH_NULL marker leaked:\n{src}");
}

#[test]
fn none_rejection_guards_preserve_chains_calls_and_success_returns() {
    for version in ["3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("none_rejection_guards.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "if value is None or not 0.0 <= value <= 15.0:",
            "if read is None or not 0.0 <= read() <= 15.0:",
            "if first is None or not 0.0 <= first() <= second() <= 15.0:",
            "if read is None or not 0.0 <= read() or not read() <= 15.0:",
            "def same_tail(value):\n    if value is None or not 0.0 <= value <= 15.0:\n        return False\n    return False",
            "return 3\n    return 5",
            "return 'reject'\n    return 'accept'",
            "if a is None or b is None or c is None or d is None or d < 0.01:\n            continue",
        ], version);
        assert_eq!(src.matches("            continue").count(), 2, "{version}: {src}");
    }
}

#[test]
fn constructed_rejections_keep_selected_values_and_statement_boundaries() {
    for version in ["3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("constructed_rejection_guards.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "if value is None or not 0.0 <= value <= 20.0:\n        return build('reject', amount=0)",
            "if not value or len(value) < 2:\n        return build('reject', amount=0)",
            "if invalid(value) or value < 2:",
            "if not value or len(value) < 2:\n        return False\n    return True",
            "if value is None or not 0.0 <= value <= 20.0:\n        return ['reject', value]",
            "if value is None or not 0.0 <= value <= 20.0:\n        return {'kind': 'reject', 'value': value}",
            "return collect((scale * item for item in rows))",
            "result = build('reject', amount=0)\n        return result",
            "log('rejected')\n        return build('reject', amount=0)",
        ], version);
    }
}

#[test]
fn shared_validation_raises_keep_causes_and_formatted_error_paths() {
    for version in ["3.14", "3.15"] {
        let (src, clean) = decompile_fixture(&format!("shared_validation_raises.{version}.pyc"));
        assert!(clean, "Python {version}: incomplete:\n{src}");
        assert_contains(&src, &[
            "if value is None or bad(value) or not ready(value):",
            "if value is None or not 0 <= read(value) <= 10 or invalid(value):",
            "raise make_error('invalid', value=value) from make_cause(value)",
            "raise make_error('invalid', value=value) from None",
            "raise make_error(f'{label!r}: {value!s:>{width}}') from make_cause()",
            "raise make_error(f'{label!a}: {value:{width}}') from make_cause()",
            "if value is None or reject(value):\n        raise ValueError",
        ], version);
    }
}

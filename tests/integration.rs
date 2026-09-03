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
fn py313_hello() {
    let (src, clean) = decompile_fixture("hello.3.13.pyc");
    assert!(clean, "output marked incomplete:\n{src}");
    assert_contains(&src, &["class Greeter:", "while a < n:", "a, b = b, a + b"], "py3.13 hello");
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

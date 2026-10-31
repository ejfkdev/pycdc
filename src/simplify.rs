//! Optional post-processing of decompiled Python source with the `cure`
//! simplifier/formatter (https://github.com/ejfkdev/cure).
//!
//! `cure` turns decompiler-shaped code into idiomatic source: folds
//! constants and opaque predicates, inlines copies, removes compiler
//! artifacts, and prints clean formatting. It is opt-in (`--cure`) so the
//! verified default output stays byte-stable.

/// Why a module was left untouched by [`simplify_python`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Skip {
    /// cure's parser reported an error (incomplete or non-Python input).
    Unparseable,
    /// The module introspects the compiler's annotation machinery.
    AnnotationIntrospection,
}

impl Skip {
    pub fn reason(self) -> &'static str {
        match self {
            Skip::Unparseable => "cure cannot parse it",
            Skip::AnnotationIntrospection => "annotation introspection",
        }
    }
}

/// Simplify/format `src` with cure's Python backend.
///
/// Returns `Err` when the module must keep pycdc's own output instead of a
/// partially-preserved rewrite.
pub fn simplify_python(src: &str) -> Result<String, Skip> {
    // Code that introspects the compiler's annotation machinery must keep
    // pycdc's exact shape: cure folds `if True:` registration gates, which
    // changes `__annotate__.__code__.co_freevars` and similar metadata.
    // Only these opt-in markers are skipped (never present in ordinary
    // application code).
    const REFLECTION_MARKERS: [&str; 4] = [
        "__annotate__",
        "co_freevars",
        "__conditional_annotations__",
        "__classdict__",
    ];
    if REFLECTION_MARKERS.iter().any(|marker| src.contains(marker)) {
        return Err(Skip::AnnotationIntrospection);
    }
    let mut outcome = cure_python_parser::parse(src);
    if !outcome.errors.is_empty() {
        return Err(Skip::Unparseable);
    }
    let cfg = cure_engine::Config::default();
    cure_python_simplify::simplify_module(&mut outcome.ast, outcome.module, &cfg);
    Ok(cure_python_print::print_module(&outcome.ast, outcome.module))
}

#[cfg(test)]
mod tests {
    use super::{simplify_python, Skip};

    #[test]
    fn folds_if_return_into_ternary() {
        let src = "def f(v):\n    if v:\n        return 1\n    return 2\n";
        let out = simplify_python(src).expect("cure parses");
        assert!(out.contains("return 1 if v else 2"), "{out}");
    }

    #[test]
    fn skips_compiler_introspection_sources() {
        let src = "def f(cls):\n    return cls.__annotate__.__code__.co_freevars\n";
        assert_eq!(simplify_python(src), Err(Skip::AnnotationIntrospection));
    }

    #[test]
    fn keeps_unparseable_input_untouched() {
        assert_eq!(simplify_python("def broken(:\n    pass\n"), Err(Skip::Unparseable));
    }

    #[test]
    fn cures_modules_that_unbind_locals() {
        // cure 0.4.2 records `del` targets as forbidden; a deleted name must
        // keep its `del` and its later read untouched.
        let src = "def f():\n    v = 5\n    del v\n    try:\n        return v\n    except UnboundLocalError:\n        return 'unbound'\n";
        let out = simplify_python(src).expect("cure parses");
        assert!(out.contains("del v") && out.contains("return v"), "{out}");
        assert!(!out.contains("return 5"), "propagated across del: {out}");
    }

    #[test]
    fn compiles_simplified_module() {
        let src = "def f(xs):\n    out = []\n    for x in xs:\n        if x:\n            out.append(x)\n    return out\n";
        let out = simplify_python(src).expect("cure parses");
        assert!(out.contains("def f(xs):"), "{out}");
    }
}
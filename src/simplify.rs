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
    /// The module deletes a local name, which cure 0.4 mis-simplifies.
    DeletedName,
}

impl Skip {
    pub fn reason(self) -> &'static str {
        match self {
            Skip::Unparseable => "cure cannot parse it",
            Skip::AnnotationIntrospection => "annotation introspection",
            Skip::DeletedName => "deletes a local name",
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
    // `del name` unbinds a local: cure 0.4 propagates the deleted name's
    // last literal into later reads (turning a real UnboundLocalError into
    // a value) and can drop the read statement itself. Skip those modules
    // until cure records deleted names as forbidden (fixed upstream, not
    // yet in a published release).
    if has_deleted_name(src) {
        return Err(Skip::DeletedName);
    }
    let mut outcome = cure_python_parser::parse(src);
    if !outcome.errors.is_empty() {
        return Err(Skip::Unparseable);
    }
    let cfg = cure_engine::Config::default();
    cure_python_simplify::simplify_module(&mut outcome.ast, outcome.module, &cfg);
    Ok(cure_python_print::print_module(&outcome.ast, outcome.module))
}

/// True when a `del` statement targets a bare local name (`del v`,
/// `del a, b`, `del (a, b)`). `del obj.attr` and `del box[k]` only drop a
/// binding's contents, so the base name keeps its value and is safe.
fn has_deleted_name(src: &str) -> bool {
    src.lines().any(|line| {
        let Some(rest) = line.trim_start().strip_prefix("del ") else {
            return false;
        };
        rest.split(',').any(|target| is_bare_name(target))
    })
}

fn is_bare_name(target: &str) -> bool {
    let target = target.trim();
    let target = target.strip_prefix('(').unwrap_or(target);
    let target = target.strip_suffix(')').unwrap_or(target);
    let mut chars = target.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic() || c == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
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
    fn skips_modules_that_unbind_locals() {
        for src in [
            "def f():\n    v = 5\n    del v\n    return v\n",
            "def f():\n    a = 1\n    b = 2\n    del a, b\n    return a\n",
            "def f():\n    a = 1\n    del (a)\n    return a\n",
        ] {
            assert_eq!(simplify_python(src), Err(Skip::DeletedName), "{src}");
        }
    }

    #[test]
    fn still_cures_item_and_attribute_deletes() {
        let src = "def f(box):\n    box['k'] = 1\n    del box['k']\n    obj.attr = 2\n    del obj.attr\n    return box\n";
        let out = simplify_python(src).expect("only bindings' contents are dropped");
        assert!(out.contains("def f(box):"), "{out}");
    }

    #[test]
    fn compiles_simplified_module() {
        let src = "def f(xs):\n    out = []\n    for x in xs:\n        if x:\n            out.append(x)\n    return out\n";
        let out = simplify_python(src).expect("cure parses");
        assert!(out.contains("def f(xs):"), "{out}");
    }
}
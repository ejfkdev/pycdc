//! CLI integration tests: argument handling, output modes and the
//! directory-mirroring batch decompiler.

use std::process::Command;

fn bin() -> &'static str {
    env!("CARGO_BIN_EXE_pycdc")
}

fn pyc_fixture() -> &'static str {
    // a small, stable corpus module for output-shape assertions
    "tests/corpus/3.8.20/base64.pyc"
}

fn out(tmp: &std::path::Path, name: &str) -> std::path::PathBuf {
    tmp.join(name)
}

fn run(args: &[&str]) -> (String, String, std::process::ExitStatus) {
    let o = Command::new(bin()).args(args).output().unwrap();
    (
        String::from_utf8_lossy(&o.stdout).into_owned(),
        String::from_utf8_lossy(&o.stderr).into_owned(),
        o.status,
    )
}

#[test]
fn help_and_version_exit_zero() {
    for a in [["--help"], ["-h"], ["help"], ["version"], ["-V"], ["--version"]] {
        let (so, _, st) = run(&a);
        assert!(st.success(), "{a:?}: exit {st:?}");
        assert!(!so.is_empty(), "{a:?}: empty stdout");
    }
    let (so, _, _) = run(&["--help"]);
    assert!(so.contains("Usage:"), "help missing usage: {so}");
    let (so, _, _) = run(&["version"]);
    assert!(so.contains("pycdc"), "version output: {so}");
    // no arguments at all prints help
    let (so, _, st) = run(&[]);
    assert!(st.success() && so.contains("Usage:"));
}

#[test]
fn unknown_option_and_missing_input_fail() {
    let (_, se, st) = run(&["--bogus", "x.pyc"]);
    assert!(!st.success());
    assert!(se.contains("unknown option: --bogus"));
    let (_, se, st) = run(&["definitely-missing.pyc"]);
    assert!(!st.success());
    assert!(se.contains("no such file or directory"));
}

#[test]
fn single_file_stdout_matches_file_output() {
    let tmp = std::env::temp_dir().join(format!("pycdc-cli-{}", std::process::id()));
    std::fs::create_dir_all(&tmp).unwrap();
    let pyc = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(pyc_fixture());

    let (so, _, st) = run(&[pyc.to_str().unwrap()]);
    assert!(st.success());

    let f = out(&tmp, "single.py");
    let (logged, se, st) = run(&[pyc.to_str().unwrap(), "-o", f.to_str().unwrap()]);
    assert!(st.success(), "stderr: {se}");
    let written = std::fs::read_to_string(&f).unwrap();
    // file output carries the same source (modulo the trailing newline)
    assert!(
        written.trim_end() == so.trim_end(),
        "stdout vs file mismatch\n--stdout--\n{so}\n--file--\n{written}"
    );
    assert!(logged.contains("->"), "batch progress line missing: {logged}");
    std::fs::remove_dir_all(&tmp).ok();
}

#[test]
fn output_to_directory_places_stem_dot_py() {
    let tmp = std::env::temp_dir().join(format!("pycdc-dir-{}", std::process::id()));
    let d = out(&tmp, "outdir");
    let pyc = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(pyc_fixture());
    // trailing separator forces directory interpretation
    let (logged, _, st) = run(&[pyc.to_str().unwrap(), "-o", &format!("{}/", d.display())]);
    assert!(st.success());
    let f = d.join("base64.py");
    assert!(f.is_file(), "expected {f:?} (log: {logged})");
    // existing directory also lands inside
    let (_, _, st) = run(&[pyc.to_str().unwrap(), "-o", d.to_str().unwrap()]);
    assert!(st.success() && f.is_file());
    std::fs::remove_dir_all(&tmp).ok();
}

#[test]
fn batch_directory_mirrors_structure_and_default_sibling() {
    let tmp = std::env::temp_dir().join(format!("pycdc-batch-{}", std::process::id()));
    let src_root = tmp.join("corpus");
    std::fs::create_dir_all(src_root.join("pkg/sub")).unwrap();
    let pyc = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(pyc_fixture());
    std::fs::copy(&pyc, src_root.join("top.pyc")).unwrap();
    std::fs::copy(&pyc, src_root.join("pkg/mid.pyc")).unwrap();
    std::fs::copy(&pyc, src_root.join("pkg/sub/leaf.pyc")).unwrap();

    // no -o: default sibling directory "<name>-decompiled" next to the input
    let (_, se, st) = run(&[src_root.to_str().unwrap()]);
    assert!(st.success(), "stderr: {se}");
    let default_root = tmp.join("corpus-decompiled");
    for rel in ["top.py", "pkg/mid.py", "pkg/sub/leaf.py"] {
        let f = default_root.join(rel);
        assert!(f.is_file(), "missing mirrored output {f:?}");
    }

    // -o directory: mirrored inside it
    let mirror = tmp.join("mirror");
    let (_, _, st) = run(&[src_root.to_str().unwrap(), "-o", mirror.to_str().unwrap()]);
    assert!(st.success());
    for rel in ["top.py", "pkg/mid.py", "pkg/sub/leaf.py"] {
        assert!(mirror.join(rel).is_file());
    }
    std::fs::remove_dir_all(&tmp).ok();
}

#[test]
fn empty_directory_and_non_pyc_only_fail_cleanly() {
    let tmp = std::env::temp_dir().join(format!("pycdc-empty-{}", std::process::id()));
    let d = tmp.join("empty");
    std::fs::create_dir_all(&d).unwrap();
    let (_, se, st) = run(&[d.to_str().unwrap()]);
    assert!(!st.success());
    assert!(se.contains("no .pyc/.pyo files found"));
    std::fs::remove_dir_all(&tmp).ok();
}

//! pycdc — multi-version Python bytecode decompiler.
//!
//! pycdc [OPTIONS] <INPUT>...   decompile .pyc files or directories
//! pycdc version | help         tool information

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use pycdc::codegen::generate;
use pycdc::decompiler::decompile;
use pycdc::loader;

const HELP: &str = "\
pycdc — multi-version Python bytecode decompiler

Usage:
  pycdc [OPTIONS] <INPUT>...     decompile .pyc/.pyo files or directories
  pycdc version                  print version information
  pycdc help                     print this help

Arguments:
  <INPUT>...                     one or more .pyc/.pyo files, or directories
                                 (scanned recursively for .pyc/.pyo files)

Options:
  -o, --output <PATH>    output file or directory (see OUTPUT below)
  -j, --jobs <N>         parallel worker threads for batch mode
                         (default: number of CPUs; -j 1 = serial)
      --opcodes <DIR>    load extra/override opcode config JSONs
  -c                     accepted for compatibility; raw-marshal input is
                         selected by -v alone
  -v <X.Y>               treat the input as raw marshal data for version
                         X.Y (e.g. 3.8) instead of a headered pyc
  -h, --help             print this help
  -V, --version          print version information

Output:
  * one input file without -o:  the source is printed to stdout
  * -o PATH with one input file:  PATH is the output .py file — unless
    PATH is an existing directory or ends with a path separator, in
    which case the result lands in PATH/<stem>.py
  * directory inputs (or several inputs):  results are written into an
    output directory, mirroring the input layout (.pyc -> .py).
    -o selects the directory (created if missing); without -o every
    directory input gets a default sibling directory named
    \"<input-name>-decompiled\" at the same level, and multiple file
    inputs write <stem>.py next to each input.
";

/// Write to stdout, exiting quietly when the reader closed the pipe
/// (`pycdc foo.pyc | head` must not panic-print a BrokenPipe message).
fn print_stdout(text: &str) {
    use std::io::Write;
    let stdout = std::io::stdout();
    let mut lock = stdout.lock();
    if let Err(e) = lock.write_all(text.as_bytes()) {
        if e.kind() == std::io::ErrorKind::BrokenPipe {
            std::process::exit(0);
        }
        eprintln!("error: stdout: {e}");
        std::process::exit(1);
    }
}

fn print_help() {
    print_stdout(HELP);
    print_stdout("\n");
}

fn print_version() {
    print_stdout(&format!(
        "pycdc {}\nsupported: Python 2.0 - 3.15 pyc (CPython, PyPy and other implementations)\n",
        env!("CARGO_PKG_VERSION")
    ));
}

struct Cli {
    inputs: Vec<PathBuf>,
    output: Option<PathBuf>,
    opcode_dir: Option<PathBuf>,
    version_override: Option<(u8, u8)>,
    jobs: Option<usize>,
}

fn parse_args(args: &[String]) -> Result<Cli, String> {
    let mut cli = Cli {
        inputs: Vec::new(),
        output: None,
        opcode_dir: None,
        version_override: None,
        jobs: None,
    };
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--opcodes" => {
                i += 1;
                match args.get(i) {
                    Some(p) => cli.opcode_dir = Some(PathBuf::from(p)),
                    None => return Err("--opcodes requires a directory argument".into()),
                }
            }
            "-o" | "--output" => {
                i += 1;
                match args.get(i) {
                    Some(p) if !p.starts_with('-') => cli.output = Some(PathBuf::from(p)),
                    _ => return Err("-o/--output requires a path argument".into()),
                }
            }
            "-j" | "--jobs" => {
                i += 1;
                match args.get(i).and_then(|s| s.parse::<usize>().ok()) {
                    Some(n) if n >= 1 => cli.jobs = Some(n),
                    _ => return Err("-j/--jobs requires a positive integer".into()),
                }
            }
            "-c" => {}
            "-v" => {
                i += 1;
                match args.get(i).and_then(|s| loader::parse_version_arg(s)) {
                    Some(v) => cli.version_override = Some(v),
                    None => return Err("-v requires a version like 3.8".into()),
                }
            }
            "-h" | "--help" => {
                print_help();
                std::process::exit(0);
            }
            "-V" | "--version" => {
                print_version();
                std::process::exit(0);
            }
            other => {
                if other.starts_with('-') && other.len() > 1 {
                    return Err(format!(
                        "unknown option: {other} (see `pycdc --help`)"
                    ));
                }
                cli.inputs.push(PathBuf::from(other));
            }
        }
        i += 1;
    }
    Ok(cli)
}

/// Every .pyc/.pyo under `dir`, in deterministic order.
fn collect_pycs(dir: &Path, out: &mut Vec<PathBuf>) -> Result<(), String> {
    let mut entries: Vec<std::fs::DirEntry> = std::fs::read_dir(dir)
        .map_err(|e| format!("{}: {e}", dir.display()))?
        .collect::<Result<_, _>>()
        .map_err(|e| format!("{}: {e}", dir.display()))?;
    entries.sort_by_key(|e| e.file_name());
    for e in entries {
        let p = e.path();
        if p.is_dir() {
            collect_pycs(&p, out)?;
        } else if p.is_file()
            && matches!(p.extension().and_then(|x| x.to_str()), Some("pyc") | Some("pyo"))
        {
            out.push(p);
        }
    }
    Ok(())
}

/// Decompile one pyc to source text (no trailing-newline normalization —
/// the file-writing path appends one; stdout stays byte-identical to the
/// historical output).
fn decompile_file(
    file: &Path,
    version_override: Option<(u8, u8)>,
) -> Result<String, String> {
    let loaded =
        loader::load(file, version_override)
            .map_err(|e| format!("{}: error: {e}", file.display()))?;
    let d = decompile(&loaded.code, loaded.version)
        .map_err(|e| format!("{}: decompile error: {e}", file.display()))?;
    let text = generate(&d.body, loaded.version, d.clean);
    if !d.clean {
        eprintln!(
            "{}: WARNING: decompilation incomplete (Python {})",
            file.display(),
            loaded.version.display()
        );
    }
    Ok(text)
}

fn write_output(path: &Path, text: &str) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("{}: {e}", parent.display()))?;
        }
    }
    std::fs::write(path, text).map_err(|e| format!("{}: {e}", path.display()))
}

/// The directory a batch input writes into when no -o was given: a
/// sibling of the input named "<input-name>-decompiled".
fn default_out_dir(input: &Path) -> PathBuf {
    let name = input
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "decompiled".to_string());
    match input.parent() {
        Some(p) if !p.as_os_str().is_empty() => p.join(format!("{name}-decompiled")),
        _ => PathBuf::from(format!("{name}-decompiled")),
    }
}

fn ends_with_sep(p: &Path) -> bool {
    p.as_os_str()
        .to_string_lossy()
        .ends_with(std::path::is_separator)
}

/// One scheduled write: source file -> output path.
struct Job {
    src: PathBuf,
    dst: PathBuf,
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();

    if args.is_empty() {
        print_help();
        return ExitCode::SUCCESS;
    }
    if args[0] == "version" {
        print_version();
        return ExitCode::SUCCESS;
    }
    if args[0] == "help" {
        print_help();
        return ExitCode::SUCCESS;
    }

    let cli = match parse_args(&args) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("error: {e}");
            return ExitCode::FAILURE;
        }
    };
    if cli.inputs.is_empty() {
        eprintln!("error: no input files or directories (see `pycdc --help`)");
        return ExitCode::FAILURE;
    }
    for input in &cli.inputs {
        if !input.exists() {
            eprintln!("error: {}: no such file or directory", input.display());
            return ExitCode::FAILURE;
        }
    }
    if let Some(dir) = &cli.opcode_dir {
        if let Err(e) = pycdc::opcode::set_override_dir(dir) {
            eprintln!("error: {e}");
            return ExitCode::FAILURE;
        }
    }

    // stdout mode: exactly one input, it is a file, and no -o was given
    let stdout_mode = cli.output.is_none()
        && cli.inputs.len() == 1
        && cli.inputs[0].is_file();

    if stdout_mode {
        return run_stdout(&cli);
    }
    run_batch(&cli)
}

fn run_stdout(cli: &Cli) -> ExitCode {
    let file = &cli.inputs[0];
    match decompile_file(file, cli.version_override) {
        Ok(text) => {
            print_stdout(&text);
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("{e}");
            ExitCode::FAILURE
        }
    }
}

fn run_batch(cli: &Cli) -> ExitCode {
    // plan every write up front so a bad -o fails before any work
    let mut jobs: Vec<Job> = Vec::new();
    for input in &cli.inputs {
        if input.is_dir() {
            let root = match &cli.output {
                Some(o) => o.clone(),
                None => default_out_dir(input),
            };
            if root.exists() && !root.is_dir() {
                eprintln!("error: {}: output path exists and is not a directory", root.display());
                return ExitCode::FAILURE;
            }
            let mut pycs = Vec::new();
            if let Err(e) = collect_pycs(input, &mut pycs) {
                eprintln!("error: {e}");
                return ExitCode::FAILURE;
            }
            for pyc in pycs {
                let rel = pyc.strip_prefix(input).unwrap_or(pyc.as_path());
                let dst = rel.with_extension("py");
                jobs.push(Job {
                    src: pyc,
                    dst: root.join(dst),
                });
            }
        } else {
            // file input
            let dst = match &cli.output {
                Some(o) => {
                    let single = cli.inputs.len() == 1;
                    if single && !o.is_dir() && !ends_with_sep(o) {
                        o.clone()
                    } else {
                        o.join(input.file_name().unwrap_or_default()).with_extension("py")
                    }
                }
                None => input.with_extension("py"),
            };
            jobs.push(Job {
                src: input.clone(),
                dst,
            });
        }
    }
    if jobs.is_empty() {
        eprintln!("error: no .pyc/.pyo files found in the given inputs");
        return ExitCode::FAILURE;
    }

    let n_threads = cli
        .jobs
        .unwrap_or_else(|| {
            std::thread::available_parallelism()
                .map(|n| n.get())
                .unwrap_or(1)
        })
        .min(jobs.len());

    // run_job: decompile + write one job; the per-job message is returned
    // instead of printed so batch output stays in deterministic order.
    let run_job = |job: &Job| -> Result<String, String> {
        let text = decompile_file(&job.src, cli.version_override)?;
        let mut text = text;
        if !text.ends_with('\n') {
            text.push('\n');
        }
        write_output(&job.dst, &text)?;
        Ok(format!("{} -> {}", job.src.display(), job.dst.display()))
    };

    let n_jobs = jobs.len();
    let results: Vec<Result<String, String>> = if n_threads <= 1 {
        jobs.iter().map(run_job).collect()
    } else {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Mutex;
        let next = AtomicUsize::new(0);
        let slots: Mutex<Vec<Option<Result<String, String>>>> =
            Mutex::new((0..n_jobs).map(|_| None).collect());
        std::thread::scope(|s| {
            for _ in 0..n_threads {
                s.spawn(|| loop {
                    let i = next.fetch_add(1, Ordering::Relaxed);
                    if i >= n_jobs {
                        break;
                    }
                    let r = run_job(&jobs[i]);
                    slots.lock().unwrap()[i] = Some(r);
                });
            }
        });
        slots
            .into_inner()
            .unwrap()
            .into_iter()
            .map(|r| r.expect("every job recorded"))
            .collect()
    };

    let mut failed = false;
    for r in results {
        match r {
            Ok(line) => print_stdout(&format!("{line}\n")),
            Err(e) => {
                eprintln!("{e}");
                failed = true;
            }
        }
    }
    if failed {
        ExitCode::FAILURE
    } else {
        ExitCode::SUCCESS
    }
}

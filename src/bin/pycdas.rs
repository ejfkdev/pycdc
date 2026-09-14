//! pycdas — multi-version Python bytecode disassembler.
//!
//! Usage: pycdas [OPTIONS] <INPUT>...   (files, directories, or - for stdin)

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use pycdc::disasm::{disassemble, DisasmOptions};
use pycdc::loader;
use pycdc::version::FLAG_HASH_BASED;

fn help_text() -> String {
    format!(
        "\
pycdas {version} — multi-version Python bytecode disassembler

Disassembles Python .pyc/.pyo bytecode with full per-version opcode
resolution. Supports Python 2.0 - 3.15 (CPython, PyPy and others).

Repository: https://github.com/ejfkdev/pycdc

Usage:
  pycdas [OPTIONS] <INPUT>...    disassemble .pyc/.pyo files or directories
  pycdas version                 print version information
  pycdas help                    print this help

Arguments:
  <INPUT>...                     one or more .pyc/.pyo files, directories
                                 (scanned recursively), or - for stdin

Options:
  -o, --output <PATH>    output file or directory (see OUTPUT below)
  -j, --jobs <N>         parallel worker threads for batch mode
                         (default: number of CPUs; -j 1 = serial)
  -q, --quiet            batch mode: suppress the per-file src -> dst
                         lines (errors still print)
      --opcodes <DIR>    load extra/override opcode config JSONs
  -c                     accepted for compatibility; raw-marshal input is
                         selected by -v alone
  -v <X.Y>               treat the input as raw marshal data for version
                         X.Y (e.g. 3.8) instead of a headered pyc
  -h, --help             print this help
  -V, --version          print version information

Examples:
  pycdas program.pyc                 disassemble a file to stdout
  pycdas program.pyc -o program.dis  disassemble into a specific file
  pycdas app/ -o out/                disassemble a directory tree,
                                     mirroring its layout (.pyc -> .dis)
  pycdas -q app/ -j 8 -o out/        quiet batch, 8 parallel workers
  cat program.pyc | pycdas -         disassemble from stdin
  pycdas -v 3.8 data.marshal         disassemble raw marshal data as 3.8

Output:
  * one input file (or -) without -o:  printed to stdout
  * -o PATH with one input:  PATH is the output file — unless PATH is an
    existing directory or ends with a path separator, in which case the
    result lands in PATH/<stem>.dis
  * directory inputs (or several inputs):  results are written into an
    output directory mirroring the input layout (.pyc -> .dis); without
    -o each directory input gets a sibling <input-name>-disasm directory

Exit codes: 0 success, 1 a file failed to load/disassemble/write,
2 usage error.
",
        version = env!("CARGO_PKG_VERSION")
    )
}

/// Write to stdout, exiting quietly when the reader closed the pipe.
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

fn print_version() {
    print_stdout(&format!(
        "pycdas {}\nsupported: Python 2.0 - 3.15 pyc (CPython, PyPy and other implementations)\n",
        env!("CARGO_PKG_VERSION")
    ));
}

struct Cli {
    inputs: Vec<PathBuf>,
    output: Option<PathBuf>,
    opcode_dir: Option<PathBuf>,
    version_override: Option<(u8, u8)>,
    jobs: Option<usize>,
    quiet: bool,
}

fn parse_args(args: &[String]) -> Result<Cli, String> {
    let mut cli = Cli {
        inputs: Vec::new(),
        output: None,
        opcode_dir: None,
        version_override: None,
        jobs: None,
        quiet: false,
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
            "-q" | "--quiet" => cli.quiet = true,
            "-c" => {}
            "-v" => {
                i += 1;
                match args.get(i).and_then(|s| loader::parse_version_arg(s)) {
                    Some(v) => cli.version_override = Some(v),
                    None => return Err("-v requires a version like 3.8".into()),
                }
            }
            "-h" | "--help" => {
                print_stdout(&help_text());
                std::process::exit(0);
            }
            "-V" | "--version" => {
                print_version();
                std::process::exit(0);
            }
            other => {
                if other.starts_with('-') && other.len() > 1 {
                    return Err(format!(
                        "unknown option: {other} (see `pycdas --help`)"
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

/// Disassemble one input (path or `-` for stdin) into the full report text.
fn disasm_file(file: &Path, version_override: Option<(u8, u8)>) -> Result<String, String> {
    let data = loader::read_input(file)
        .map_err(|e| format!("{}: error: {e}", file.display()))?;
    let loaded = loader::load_bytes(&data, version_override)
        .map_err(|e| format!("{}: error: {e}", file.display()))?;
    let mut out = format!(
        "{} (Python {} {}, magic {})\n",
        file.display(),
        loaded.version.display(),
        loaded.version.implementation.name(),
        loaded.version.magic
    );
    if let Some(h) = &loaded.header {
        if h.kind == pycdc::version::HeaderKind::Pep552 && h.flags & FLAG_HASH_BASED != 0 {
            out.push_str(&format!("  hash-based pyc, flags {:#x}\n", h.flags));
        } else {
            out.push_str(&format!(
                "  timestamp {} source size {}\n",
                h.timestamp, h.source_size
            ));
        }
    }
    out.push('\n');
    let text = disassemble(&loaded.code, loaded.version, &DisasmOptions::default(), 0)
        .map_err(|e| format!("{}: disassembly error: {e}", file.display()))?;
    out.push_str(&text);
    out.push('\n');
    Ok(out)
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
/// sibling of the input named "<input-name>-disasm".
fn default_out_dir(input: &Path) -> PathBuf {
    let name = input
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "disasm".to_string());
    match input.parent() {
        Some(p) if !p.as_os_str().is_empty() => p.join(format!("{name}-disasm")),
        _ => PathBuf::from(format!("{name}-disasm")),
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
        print_stdout(&help_text());
        return ExitCode::SUCCESS;
    }
    if args[0] == "version" {
        print_version();
        return ExitCode::SUCCESS;
    }
    if args[0] == "help" {
        print_stdout(&help_text());
        return ExitCode::SUCCESS;
    }

    let usage_err = |m: String| {
        eprintln!("error: {m}");
        ExitCode::from(2)
    };
    let cli = match parse_args(&args) {
        Ok(c) => c,
        Err(e) => return usage_err(e),
    };
    if cli.inputs.is_empty() {
        // missing required input: default to the help screen (exit 2)
        print_stdout(&help_text());
        return ExitCode::from(2);
    }
    if cli.inputs.iter().any(|p| p == Path::new("-")) && cli.inputs.len() > 1 {
        return usage_err("stdin input (-) cannot be combined with other inputs".into());
    }
    for input in &cli.inputs {
        if input != Path::new("-") && !input.exists() {
            return usage_err(format!("{}: no such file or directory", input.display()));
        }
    }
    if let Some(dir) = &cli.opcode_dir {
        if let Err(e) = pycdc::opcode::set_override_dir(dir) {
            return usage_err(e.to_string());
        }
    }

    // stdout mode: exactly one input, it is a file (or stdin), no -o
    let stdout_mode = cli.output.is_none()
        && cli.inputs.len() == 1
        && (cli.inputs[0].is_file() || cli.inputs[0] == Path::new("-"));
    if stdout_mode {
        return match disasm_file(&cli.inputs[0], cli.version_override) {
            Ok(text) => {
                print_stdout(&text);
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("{e}");
                ExitCode::FAILURE
            }
        };
    }

    // plan every write up front so a bad -o fails before any work
    let mut jobs: Vec<Job> = Vec::new();
    for input in &cli.inputs {
        if input.is_dir() {
            let root = match &cli.output {
                Some(o) => o.clone(),
                None => default_out_dir(input),
            };
            if root.exists() && !root.is_dir() {
                return usage_err(format!(
                    "{}: output path exists and is not a directory",
                    root.display()
                ));
            }
            let mut pycs = Vec::new();
            if let Err(e) = collect_pycs(input, &mut pycs) {
                return usage_err(e);
            }
            for pyc in pycs {
                let rel = pyc.strip_prefix(input).unwrap_or(pyc.as_path());
                let dst = rel.with_extension("dis");
                jobs.push(Job {
                    src: pyc,
                    dst: root.join(dst),
                });
            }
        } else {
            // file input (or stdin: named "stdin" for placement purposes)
            let stem = if input == Path::new("-") {
                PathBuf::from("stdin")
            } else {
                input.clone()
            };
            let dst = match &cli.output {
                Some(o) => {
                    let single = cli.inputs.len() == 1;
                    if single && !o.is_dir() && !ends_with_sep(o) {
                        o.clone()
                    } else {
                        o.join(stem.file_name().unwrap_or_default()).with_extension("dis")
                    }
                }
                None => stem.with_extension("dis"),
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

    let run_job = |job: &Job| -> Result<String, String> {
        let text = disasm_file(&job.src, cli.version_override)?;
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
            Ok(line) => {
                if !cli.quiet {
                    print_stdout(&format!("{line}\n"));
                }
            }
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

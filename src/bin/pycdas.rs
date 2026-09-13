//! pycdas — multi-version Python bytecode disassembler.
//!
//! Usage: pycdas [--opcodes DIR] <file.pyc>...

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use pycdc::disasm::{disassemble, DisasmOptions};
use pycdc::loader;
use pycdc::version::FLAG_HASH_BASED;

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

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut files: Vec<PathBuf> = Vec::new();
    let mut opcode_dir: Option<PathBuf> = None;
    let mut version_override: Option<(u8, u8)> = None;

    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--opcodes" => {
                i += 1;
                match args.get(i) {
                    Some(p) => opcode_dir = Some(PathBuf::from(p)),
                    None => {
                        eprintln!("--opcodes requires a directory argument");
                        return ExitCode::FAILURE;
                    }
                }
            }
            "-v" => {
                i += 1;
                match args.get(i).and_then(|s| loader::parse_version_arg(s)) {
                    Some(v) => version_override = Some(v),
                    None => {
                        eprintln!("-v requires a version like 3.8");
                        return ExitCode::FAILURE;
                    }
                }
            }
            "-h" | "--help" => {
                print_stdout(
                    "Usage: pycdas [--opcodes DIR] [-v X.Y] <file.pyc>...\n\n  --opcodes DIR   load extra/override opcode config JSONs\n  -v X.Y          treat input as raw marshal data for version X.Y\n",
                );
                return ExitCode::SUCCESS;
            }
            other => files.push(Path::new(other).to_path_buf()),
        }
        i += 1;
    }

    if files.is_empty() {
        eprintln!("Usage: pycdas [--opcodes DIR] [-v X.Y] <file.pyc>...");
        return ExitCode::FAILURE;
    }
    if let Some(dir) = &opcode_dir {
        if let Err(e) = pycdc::opcode::set_override_dir(dir) {
            eprintln!("error: {e}");
            return ExitCode::FAILURE;
        }
    }

    let mut failed = false;
    for file in &files {
        match loader::load(file, version_override) {
            Ok(loaded) => {
                let mut head = format!(
                    "{} (Python {} {}, magic {})\n",
                    file.display(),
                    loaded.version.display(),
                    loaded.version.implementation.name(),
                    loaded.version.magic
                );
                if let Some(h) = &loaded.header {
                    if h.kind == pycdc::version::HeaderKind::Pep552
                        && h.flags & FLAG_HASH_BASED != 0
                    {
                        head.push_str(&format!("  hash-based pyc, flags {:#x}\n", h.flags));
                    } else {
                        head.push_str(&format!(
                            "  timestamp {} source size {}\n",
                            h.timestamp, h.source_size
                        ));
                    }
                }
                head.push('\n');
                print_stdout(&head);
                match disassemble(&loaded.code, loaded.version, &DisasmOptions::default(), 0) {
                    Ok(text) => print_stdout(&text),
                    Err(e) => {
                        eprintln!("{}: disassembly error: {e}", file.display());
                        failed = true;
                    }
                }
                print_stdout("\n");
            }
            Err(e) => {
                eprintln!("{}: error: {e}", file.display());
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

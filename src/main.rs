//! pycdc — multi-version Python bytecode decompiler.
//!
//! Usage: pycdc [--opcodes DIR] [-c -v X.Y] <file.pyc>...

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use pycdc::codegen::generate;
use pycdc::decompiler::decompile;
use pycdc::loader;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut files: Vec<PathBuf> = Vec::new();
    let mut opcode_dir: Option<PathBuf> = None;
    let mut version_override: Option<(u8, u8)> = None;
    let mut raw_marshal = false;

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
            "-c" => raw_marshal = true,
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
                println!("Usage: pycdc [--opcodes DIR] [-c] [-v X.Y] <file.pyc>...");
                println!();
                println!("  --opcodes DIR   load extra/override opcode config JSONs");
                println!("  -c -v X.Y       treat input as raw marshal data for version X.Y");
                return ExitCode::SUCCESS;
            }
            other => files.push(Path::new(other).to_path_buf()),
        }
        i += 1;
    }

    if files.is_empty() {
        eprintln!("Usage: pycdc [--opcodes DIR] [-c] [-v X.Y] <file.pyc>...");
        return ExitCode::FAILURE;
    }
    if raw_marshal && version_override.is_none() {
        eprintln!("-c requires -v X.Y");
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
                match decompile(&loaded.code, loaded.version) {
                    Ok(d) => {
                        print!("{}", generate(&d.body, loaded.version, d.clean));
                        if !d.clean {
                            eprintln!(
                                "{}: WARNING: decompilation incomplete (Python {})",
                                file.display(),
                                loaded.version.display()
                            );
                        }
                    }
                    Err(e) => {
                        eprintln!("{}: decompile error: {e}", file.display());
                        failed = true;
                    }
                }
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

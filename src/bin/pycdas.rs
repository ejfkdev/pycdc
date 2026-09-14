//! pycdas — multi-version Python bytecode disassembler.
//!
//! Thin wrapper over [`pycdc::cli_disasm`]; the same functionality is
//! also reachable as `pycdc dis`.

use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    pycdc::cli_disasm::run("pycdas", &args)
}

//! Recursive disassembly of code objects (pycdas).

use std::fmt::Write as _;

use crate::bytecode::{decode_instructions, disasm_line};
use crate::code::CodeObject;
use crate::object::PyObject;
use crate::opcode::table_for;
use crate::version::PythonVersion;

pub struct DisasmOptions {
    /// Print raw header and per-code-object metadata.
    pub verbose: bool,
}

impl Default for DisasmOptions {
    fn default() -> Self {
        DisasmOptions { verbose: true }
    }
}

/// Disassemble a code object (and nested ones) into a string.
pub fn disassemble(
    code: &CodeObject,
    version: PythonVersion,
    opts: &DisasmOptions,
    indent: usize,
) -> crate::Result<String> {
    let table = table_for(version)?;
    let mut out = String::new();
    let pad = " ".repeat(indent);

    if opts.verbose {
        writeln!(
            out,
            "{pad}Disassembly of <code object {} (file {}, line {})>:",
            code.name, code.filename, code.first_line
        )?;
        writeln!(
            out,
            "{pad}  argcount={} posonly={} kwonly={} nlocals={} stacksize={} flags={:#x}",
            code.arg_count,
            code.posonly_arg_count,
            code.kwonly_arg_count,
            code.n_locals,
            code.stack_size,
            code.flags
        )?;
        if !code.varnames.is_empty() {
            writeln!(out, "{pad}  varnames: {:?}", code.varnames)?;
        }
        if !code.cellvars.is_empty() {
            writeln!(out, "{pad}  cellvars: {:?}", code.cellvars)?;
        }
        if !code.freevars.is_empty() {
            writeln!(out, "{pad}  freevars: {:?}", code.freevars)?;
        }
        if !code.qualname.is_empty() && code.qualname != code.name {
            writeln!(out, "{pad}  qualname: {}", code.qualname)?;
        }
        writeln!(out)?;
    }

    // Collect jump targets for markers.
    let instrs = decode_instructions(code, table, version);
    let mut targets: std::collections::HashSet<usize> = std::collections::HashSet::new();
    for inst in &instrs {
        if let Some(t) = inst.target {
            targets.insert(t);
        }
    }
    for e in code.exception_entries() {
        targets.insert(e.target);
    }

    let mut last_line: Option<u32> = None;
    for inst in &instrs {
        if targets.contains(&inst.start) {
            writeln!(out, "{pad}>>{}", " ".repeat(inst.start.to_string().len()))?;
        }
        if let Some(l) = inst.line {
            if last_line != Some(l) {
                writeln!(out, "{pad}  [line {l}]")?;
                last_line = Some(l);
            }
        }
        let line = disasm_line(inst, code, table, version);
        writeln!(out, "{pad}  {line}")?;
    }

    // Exception table (3.11+)
    let entries = code.exception_entries();
    if !entries.is_empty() {
        writeln!(out, "{pad}  ExceptionTable:")?;
        for e in entries {
            writeln!(
                out,
                "{pad}    {} to {} -> {} [depth {}{}]",
                e.start,
                e.end,
                e.target,
                e.depth,
                if e.lasti { ", lasti" } else { "" }
            )?;
        }
    }

    // Nested code objects
    for c in &code.consts {
        if let PyObject::Code(nested) = &**c {
            writeln!(out)?;
            out.push_str(&disassemble(nested, version, opts, indent + 2)?);
        }
    }
    Ok(out)
}

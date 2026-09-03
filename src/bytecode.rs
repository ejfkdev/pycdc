//! Instruction decoding with full cross-version normalization.
//!
//! The decoder absorbs every historical instruction-encoding difference so
//! that consumers (disassembler, decompiler) see one uniform stream:
//!
//! * pre-3.6 variable width (1 or 3 bytes) vs 3.6+ fixed 2-byte wordcode
//! * EXTENDED_ARG chains folded into the final argument
//! * absolute vs relative jumps, byte vs word-unit targets, and 3.11's
//!   backward-jump variants all resolved to absolute byte offsets
//! * 3.11+ inline CACHE entries skipped
//! * instruction sizes include caches so block-end arithmetic stays in bytes

use std::collections::HashMap;

use crate::code::CodeObject;
use crate::object::PyObject;
use crate::opcode::{Op, OpcodeTable};
use crate::version::PythonVersion;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Instruction {
    /// Byte offset of the logical instruction (after any EXTENDED_ARG prefix).
    pub offset: usize,
    /// Byte offset including the EXTENDED_ARG prefix.
    pub start: usize,
    /// Total bytes consumed: prefix + instruction + trailing CACHE entries.
    pub size: usize,
    pub opcode: u8,
    pub op: Op,
    /// Merged argument (EXTENDED_ARG folded in); 0 for no-arg instructions.
    pub arg: u32,
    pub has_arg: bool,
    /// Normalized absolute jump target in byte offsets, when this is a jump.
    pub target: Option<usize>,
    /// True for relative jumps whose target precedes the instruction end.
    pub is_backward: bool,
    /// Source line, when the line table provides one.
    pub line: Option<u32>,
}

impl Instruction {
    pub fn is_jump(&self) -> bool {
        self.target.is_some()
    }

    /// Offset immediately after this instruction (including caches).
    pub fn end(&self) -> usize {
        self.start + self.size
    }
}

/// Decode a code object's instruction stream.
pub fn decode_instructions(
    code: &CodeObject,
    table: &OpcodeTable,
    version: PythonVersion,
) -> Vec<Instruction> {
    let bytes = &code.code;
    let mut out: Vec<Instruction> = Vec::new();
    let mut i = 0usize;
    let mut ext_arg: u32 = 0;
    let mut ext_start: Option<usize> = None;

    let line_map: HashMap<usize, u32> = code.line_starts().iter().cloned().collect();
    let lookup_line = |off: usize| -> Option<u32> {
        // exact match, else the last entry at or before off
        let mut best: Option<u32> = None;
        for (o, l) in code.line_starts() {
            if *o <= off {
                best = Some(*l);
            } else {
                break;
            }
        }
        best.or_else(|| line_map.get(&0).copied())
    };

    let jumps_in_words = version.jumps_in_words();

    while i < bytes.len() {
        let opcode = bytes[i];

        // 3.11+: skip stray CACHE entries defensively (normally consumed below)
        if version.has_cache_entries() && table.name(opcode) == "CACHE" {
            i += 2;
            continue;
        }

        if table.wordcode {
            if i + 1 >= bytes.len() {
                break;
            }
            let arg_byte = bytes[i + 1] as u32;
            let op_start = ext_start.unwrap_or(i);
            let offset = i;
            i += 2;

            if table.op(opcode) == Op::EXTENDED_ARG {
                ext_arg = (ext_arg + arg_byte) << 8;
                if ext_start.is_none() {
                    ext_start = Some(offset);
                }
                continue;
            }

            let has_arg = table.has_arg(opcode);
            let arg = if has_arg { ext_arg + arg_byte } else { 0 };
            let cache_bytes = if version.has_cache_entries() {
                table.cache_entries(opcode) as usize * 2
            } else {
                0
            };
            let size = (offset + 2 + cache_bytes) - op_start;
            let target = normalize_jump(
                table, opcode, arg, offset + 2 + cache_bytes, jumps_in_words, true,
            );
            out.push(Instruction {
                offset,
                start: op_start,
                size,
                opcode,
                op: table.op(opcode),
                arg,
                has_arg,
                is_backward: target.map_or(false, |t| t < offset + 2 + cache_bytes),
                target,
                line: lookup_line(offset),
            });
            ext_arg = 0;
            ext_start = None;
            i += cache_bytes;
        } else {
            let op_start = ext_start.unwrap_or(i);
            let offset = i;
            i += 1;

            if table.op(opcode) == Op::EXTENDED_ARG {
                if i + 1 >= bytes.len() {
                    break;
                }
                let lo = bytes[i] as u32;
                let hi = bytes[i + 1] as u32;
                i += 2;
                ext_arg = (ext_arg + (lo | (hi << 8))) << 16;
                if ext_start.is_none() {
                    ext_start = Some(offset);
                }
                continue;
            }

            let has_arg = table.has_arg(opcode);
            let mut arg = 0u32;
            if has_arg {
                if i + 1 >= bytes.len() {
                    break;
                }
                let lo = bytes[i] as u32;
                let hi = bytes[i + 1] as u32;
                i += 2;
                arg = ext_arg + (lo | (hi << 8));
            }
            let size = i - op_start;
            let target = normalize_jump(
                table, opcode, arg, i, jumps_in_words, false,
            );
            out.push(Instruction {
                offset,
                start: op_start,
                size,
                opcode,
                op: table.op(opcode),
                arg,
                has_arg,
                is_backward: target.map_or(false, |t| t < i),
                target,
                line: lookup_line(offset),
            });
            ext_arg = 0;
            ext_start = None;
        }
    }
    out
}

/// Resolve a jump operand to an absolute byte offset.
///
/// * `next` is the byte offset directly after the jump instruction's operand
///   (pre-CACHE-skip position for wordcode).
/// * 3.10+ count jump deltas in instruction words, earlier versions in bytes.
/// * 3.11 renamed backward relative jumps (JUMP_BACKWARD,
///   POP_JUMP_BACKWARD_IF_*); 3.12 made all remaining relative jumps
///   forward-relative again.
fn normalize_jump(
    table: &OpcodeTable,
    opcode: u8,
    arg: u32,
    next: usize,
    jumps_in_words: bool,
    wordcode: bool,
) -> Option<usize> {
    let name = table.name(opcode);
    let backward = name.contains("BACKWARD");
    let unit = if jumps_in_words { 2usize } else { 1usize };
    let delta = arg as usize * unit;

    if table.is_jabs(opcode) {
        // absolute target; 3.10+ counted in words
        let _ = (next, wordcode);
        return Some(delta);
    }
    if table.is_jrel(opcode) {
        return if backward {
            next.checked_sub(delta)
        } else {
            Some(next + delta)
        };
    }
    None
}

/// Render one instruction the way `dis` does, for the disassembler.
pub fn disasm_line(
    inst: &Instruction,
    code: &CodeObject,
    table: &OpcodeTable,
    version: PythonVersion,
) -> String {
    
    let name = table.name(inst.opcode);
    let mut argrepr = String::new();
    if inst.has_arg {
        let a = inst.arg;
        match inst.op {
            Op::LOAD_CONST | Op::RETURN_CONST => {
                if let Some(c) = code.consts.get(a as usize) {
                    argrepr = format!("({})", short_const_repr(c, version));
                } else {
                    argrepr = format!("{a}");
                }
            }
            Op::LOAD_FAST | Op::STORE_FAST | Op::DELETE_FAST => {
                // 3.11+: LOAD_FAST arg indexes localsplus; earlier: varnames
                let idx = a as usize;
                let n = if version.at_least(3, 11) {
                    code.deref_names.get(idx).cloned()
                } else {
                    None
                }
                .or_else(|| code.varnames.get(idx).cloned());
                argrepr = match n {
                    Some(s) => format!("{a} ({s})"),
                    None => format!("{a}"),
                };
            }
            Op::LOAD_NAME
            | Op::STORE_NAME
            | Op::DELETE_NAME
            | Op::LOAD_ATTR
            | Op::STORE_ATTR
            | Op::DELETE_ATTR
            | Op::LOAD_GLOBAL
            | Op::STORE_GLOBAL
            | Op::DELETE_GLOBAL
            | Op::IMPORT_NAME
            | Op::IMPORT_FROM
            | Op::LOAD_METHOD
            | Op::LOAD_SUPER_ATTR => {
                // LOAD_GLOBAL (3.11+) and LOAD_SUPER_ATTR (3.12+) pack a
                // "push NULL" flag into the low bits of the index.
                let idx = match inst.op {
                    Op::LOAD_GLOBAL if version.at_least(3, 11) => (a >> 1) as usize,
                    Op::LOAD_SUPER_ATTR if version.at_least(3, 12) => (a >> 2) as usize,
                    // 3.12: LOAD_ATTR low bit = "method" (pushes NULL+self);
                    // STORE_ATTR/DELETE_ATTR use the plain index
                    Op::LOAD_ATTR if version.at_least(3, 12) => (a >> 1) as usize,
                    _ => a as usize,
                };
                let nm = code
                    .names
                    .get(idx)
                    .and_then(|n| {
                        n.as_str().map(str::to_string).or_else(|| {
                            n.as_bytes().and_then(|b| std::str::from_utf8(b).ok()).map(str::to_string)
                        })
                    });
                argrepr = match nm {
                    Some(s) => format!("{a} ({s})"),
                    None => format!("{a}"),
                };
            }
            Op::LOAD_DEREF
            | Op::STORE_DEREF
            | Op::DELETE_DEREF
            | Op::LOAD_CLOSURE
            | Op::LOAD_CLASSDEREF
            | Op::LOAD_FROM_DICT_OR_DEREF
            | Op::MAKE_CELL => {
                if let Some(n) = code.deref_name(a as usize) {
                    argrepr = format!("{a} ({n})");
                } else {
                    argrepr = format!("{a}");
                }
            }
            Op::COMPARE_OP => {
                // 3.12 packs a specialization flag in the low bits; 3.13+
                // uses the plain index again
                let idx = compare_op_index(a, version);
                argrepr = table
                    .cmp_op
                    .get(idx)
                    .map(|s| format!("{a} ({s})"))
                    .unwrap_or_else(|| format!("{a}"));
            }
            Op::BINARY_OP => {
                argrepr = binary_op_name(a, version)
                    .map(|s| format!("{a} ({s})"))
                    .unwrap_or_else(|| format!("{a}"));
            }
            _ => {
                if let Some(t) = inst.target {
                    argrepr = format!("to {t}");
                } else {
                    argrepr = format!("{a}");
                }
            }
        }
    }
    format_line(inst, name, &argrepr)
}

fn format_line(inst: &Instruction, name: &str, argrepr: &str) -> String {
    if argrepr.is_empty() {
        format!("{:>6} {:<24}", inst.offset, name)
    } else {
        format!("{:>6} {:<24} {}", inst.offset, name, argrepr)
    }
}

/// Short repr of a constant for disassembly output.
pub fn short_const_repr(obj: &crate::object::PyObject, version: PythonVersion) -> String {
    match obj {
        PyObject::None => "None".into(),
        PyObject::True => "True".into(),
        PyObject::False => "False".into(),
        PyObject::Ellipsis => "Ellipsis".into(),
        PyObject::Int(i) => i.to_string(),
        PyObject::Long(l) => {
            if version.major == 2 {
                format!("{}L", l)
            } else {
                l.decimal.clone()
            }
        }
        PyObject::Float(_, Some(s)) => s.clone(),
        PyObject::Float(f, None) => float_repr(*f),
        PyObject::Complex(re, im) => format!("{}+{}j", re, im),
        PyObject::Str(s) => {
            if s.len() > 40 {
                format!("{:?}...", truncate_str(s, 37))
            } else {
                format!("{s:?}")
            }
        }
        PyObject::Bytes(b) => {
            let s = String::from_utf8_lossy(b);
            if b.len() > 40 {
                format!("b{:?}...", truncate_str(&s, 37))
            } else if version.major >= 3 {
                format!("b{:?}", s)
            } else {
                format!("{:?}", s)
            }
        }
        PyObject::Tuple(items) => format!("tuple[{}]", items.len()),
        PyObject::List(items) => format!("list[{}]", items.len()),
        PyObject::Dict(items) => format!("dict[{}]", items.len()),
        PyObject::Set(items) => format!("set[{}]", items.len()),
        PyObject::FrozenSet(items) => format!("frozenset[{}]", items.len()),
        PyObject::Slice(..) => "slice".into(),
        PyObject::Code(c) => format!("<code object {} at line {}>", c.name, c.first_line),
        PyObject::StopIteration => "StopIteration".into(),
    }
}

/// Truncate to at most `max` bytes on a char boundary.
fn truncate_str(s: &str, max: usize) -> &str {
    if s.len() <= max {
        return s;
    }
    let mut end = max;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    &s[..end]
}

/// repr of an f64 in Python style (always with .0 for integral values).
pub fn float_repr(f: f64) -> String {
    if f.is_infinite() {
        return if f > 0.0 { "inf".into() } else { "-inf".into() };
    }
    if f.is_nan() {
        return "nan".into();
    }
    let s = format!("{f:?}");
    if s.contains('.') || s.contains('e') || s.contains("inf") || s.contains("NaN") {
        s
    } else {
        format!("{s}.0")
    }
}

/// COMPARE_OP argument -> cmp_op index. 3.12 packs specialization flags in
/// the low 4 bits, 3.13+ in the low 5 bits; earlier versions use the raw arg.
pub fn compare_op_index(arg: u32, version: PythonVersion) -> usize {
    if version.at_least(3, 13) {
        (arg >> 5) as usize
    } else if version.tuple() == (3, 12) {
        (arg >> 4) as usize
    } else {
        arg as usize
    }
}

/// BINARY_OP (3.11+) argument -> operator text.
pub fn binary_op_name(arg: u32, _version: PythonVersion) -> Option<&'static str> {
    let id = arg;
    Some(match id {
        0 => "+",
        1 => "&",
        2 => "//",
        3 => "<<",
        4 => "@",
        5 => "*",
        6 => "%",
        7 => "|",
        8 => "**",
        9 => ">>",
        10 => "-",
        11 => "/",
        12 => "^",
        13 => "+=",
        14 => "&=",
        15 => "//=",
        16 => "<<=",
        17 => "@=",
        18 => "*=",
        19 => "%=",
        20 => "|=",
        21 => "**=",
        22 => ">>=",
        23 => "-=",
        24 => "/=",
        25 => "^=",
        _ => return None,
    })
}

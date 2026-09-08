//! Normalized code object: one representation across all Python versions.
//!
//! The marshal reader fills in whatever fields exist for the target version;
//! consumers (disassembler, decompiler) never need to know the layout.

use std::cell::OnceCell;
use std::rc::Rc;

use crate::object::ObjectRef;

/// `co_flags` bits (stable across versions).
pub const CO_OPTIMIZED: u32 = 0x0001;
pub const CO_NEWLOCALS: u32 = 0x0002;
pub const CO_VARARGS: u32 = 0x0004;
pub const CO_VARKEYWORDS: u32 = 0x0008;
pub const CO_NESTED: u32 = 0x0010;
pub const CO_GENERATOR: u32 = 0x0020;
pub const CO_NOFREE: u32 = 0x0040;
pub const CO_COROUTINE: u32 = 0x0080;
pub const CO_ITERABLE_COROUTINE: u32 = 0x0100;
pub const CO_ASYNC_GENERATOR: u32 = 0x0200;
pub const CO_FUTURE_DIVISION: u32 = 0x2000;
/// `from __future__ import annotations` (PEP 563): annotations are
/// stored as source-text strings; propagates to every code object in
/// the module
pub const CO_FUTURE_ANNOTATIONS: u32 = 0x1000000;

/// 3.11+ `co_localspluskinds` flags.
pub const CO_FAST_LOCAL: u8 = 0x20;
pub const CO_FAST_CELL: u8 = 0x40;
pub const CO_FAST_FREE: u8 = 0x80;

/// One entry of the 3.11+ exception table.
#[derive(Debug, Clone)]
pub struct ExceptionEntry {
    /// Start byte offset in co_code (inclusive).
    pub start: usize,
    /// End byte offset (exclusive).
    pub end: usize,
    /// Handler target byte offset.
    pub target: usize,
    /// Stack depth to restore.
    pub depth: u32,
    /// Whether `lasti` is pushed before the handler.
    pub lasti: bool,
}

#[derive(Debug)]
pub struct CodeObject {
    pub arg_count: u32,
    /// Positional-only args (3.8+); 0 for older versions.
    pub posonly_arg_count: u32,
    pub kwonly_arg_count: u32,
    pub n_locals: u32,
    pub stack_size: u32,
    pub flags: u32,
    /// Raw instruction bytes (`co_code`).
    pub code: Vec<u8>,
    pub consts: Vec<ObjectRef>,
    pub names: Vec<ObjectRef>,
    pub varnames: Vec<String>,
    pub freevars: Vec<String>,
    pub cellvars: Vec<String>,
    /// Names indexed by LOAD_DEREF/LOAD_CLOSURE: `cellvars + freevars` for
    /// Python <= 3.10, `co_localsplusnames` for 3.11+.
    pub deref_names: Vec<String>,
    pub filename: String,
    pub name: String,
    /// `co_qualname` (3.11+); empty when absent.
    pub qualname: String,
    pub first_line: u32,
    /// Raw lnotab (<= 3.9), linetable (3.10+).
    pub line_table: Vec<u8>,
    /// Raw exception table (3.11+).
    pub exception_table: Vec<u8>,
    /// Parsed exception table entries (3.11+), computed lazily.
    exception_entries: OnceCell<Vec<ExceptionEntry>>,
    /// Decoded (offset -> line) map, computed lazily.
    line_starts: OnceCell<Vec<(usize, u32)>>,
    /// Marker set by the marshal reader: the code object uses the 3.11+
    /// location-table encoding rather than lnotab.
    pub has_pep626_table: bool,
    /// lnotab line deltas are unsigned on Python 2, signed on Python 3.
    pub py2_line_table: bool,
}

impl CodeObject {
    /// `co_localsplusnames` (3.11+) already split into varnames/cellvars/
    /// freevars by the marshal reader. Kept for reference in tests.
    pub fn is_generator(&self) -> bool {
        self.flags & CO_GENERATOR != 0
    }

    pub fn is_coroutine(&self) -> bool {
        self.flags & CO_COROUTINE != 0
    }

    pub fn is_async_generator(&self) -> bool {
        self.flags & CO_ASYNC_GENERATOR != 0
    }

    pub fn has_varargs(&self) -> bool {
        self.flags & CO_VARARGS != 0
    }

    pub fn has_varkeywords(&self) -> bool {
        self.flags & CO_VARKEYWORDS != 0
    }

    /// All cell + free variable names in LOAD_DEREF index order.
    pub fn deref_name(&self, i: usize) -> Option<&str> {
        self.deref_names.get(i).map(|s| s.as_str())
    }

    pub fn exception_entries(&self) -> &[ExceptionEntry] {
        self.exception_entries.get_or_init(|| {
            parse_exception_table(&self.exception_table)
        })
    }

    /// (byte offset -> source line) pairs derived from the line table.
    pub fn line_starts(&self) -> &[(usize, u32)] {
        self.line_starts.get_or_init(|| {
            crate::linetable::decode_line_table(
                &self.line_table,
                self.first_line,
                if self.has_pep626_table {
                    crate::linetable::LineTableKind::Pep626
                } else if self.py2_line_table {
                    crate::linetable::LineTableKind::LnotabUnsigned
                } else {
                    crate::linetable::LineTableKind::LnotabSigned
                },
            )
        })
    }
}

/// Parse the 3.11+ co_exceptiontable into entries.
///
/// Encoding: a sequence of varints (6 bits per byte, high bit = continuation,
/// zigzag-ish signed for some fields):
///   `start` (code units, *2 for bytes), `length` (*2), `target` (*2),
///   `depth<<1 | lasti`.
pub fn parse_exception_table(data: &[u8]) -> Vec<ExceptionEntry> {
    // CPython parse_varint: 6-bit chunks, most significant first, bit 0x40
    // is the continuation flag; entry-start bytes additionally carry 0x80.
    fn read_varint(data: &[u8], pos: &mut usize) -> Option<u64> {
        let first = *data.get(*pos)?;
        let mut value = (first & 0x3F) as u64;
        let mut b = first;
        *pos += 1;
        while b & 0x40 != 0 {
            b = *data.get(*pos)?;
            *pos += 1;
            value = (value << 6) | (b & 0x3F) as u64;
        }
        Some(value)
    }

    let mut out = Vec::new();
    let mut pos = 0;
    while pos < data.len() {
        let (Some(start), Some(length), Some(target), Some(dl)) = (
            read_varint(data, &mut pos),
            read_varint(data, &mut pos),
            read_varint(data, &mut pos),
            read_varint(data, &mut pos),
        ) else {
            break;
        };
        out.push(ExceptionEntry {
            start: (start * 2) as usize,
            end: ((start + length) * 2) as usize,
            target: (target * 2) as usize,
            depth: (dl >> 1) as u32,
            lasti: dl & 1 != 0,
        });
    }
    out
}

/// Build the normalized code object shell (fields filled by the marshal
/// reader according to version).
impl CodeObject {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        arg_count: u32,
        posonly_arg_count: u32,
        kwonly_arg_count: u32,
        n_locals: u32,
        stack_size: u32,
        flags: u32,
        code: Vec<u8>,
        consts: Vec<ObjectRef>,
        names: Vec<ObjectRef>,
        varnames: Vec<String>,
        freevars: Vec<String>,
        cellvars: Vec<String>,
        deref_names: Vec<String>,
        filename: String,
        name: String,
        qualname: String,
        first_line: u32,
        line_table: Vec<u8>,
        exception_table: Vec<u8>,
        has_pep626_table: bool,
        py2_line_table: bool,
    ) -> Rc<CodeObject> {
        Rc::new(CodeObject {
            arg_count,
            posonly_arg_count,
            kwonly_arg_count,
            n_locals,
            stack_size,
            flags,
            code,
            consts,
            names,
            varnames,
            freevars,
            cellvars,
            deref_names,
            filename,
            name,
            qualname,
            first_line,
            line_table,
            exception_table,
            exception_entries: OnceCell::new(),
            line_starts: OnceCell::new(),
            has_pep626_table,
            py2_line_table,
        })
    }
}

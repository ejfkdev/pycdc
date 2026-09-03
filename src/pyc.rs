//! pyc file header parsing and module loading.

use std::rc::Rc;

use crate::code::CodeObject;
use crate::error::{PycError, Result};
use crate::marshal::MarshalReader;
use crate::object::PyObject;
use crate::version::{
    header_kind, version_from_magic, HeaderKind, PythonVersion, FLAG_HASH_BASED,
};

#[derive(Debug, Clone)]
pub struct PycHeader {
    pub magic: u16,
    pub version: PythonVersion,
    pub kind: HeaderKind,
    /// PEP 552 flags (3.7+), 0 otherwise.
    pub flags: u32,
    /// Source mtime (timestamp-based headers).
    pub timestamp: u32,
    /// Source size mod 2^32 (3.3+).
    pub source_size: u32,
    /// SipHash of the source (hash-based 3.7+ headers).
    pub source_hash: u64,
    /// Total header size in bytes; the marshal payload starts here.
    pub header_size: usize,
}

#[derive(Debug, Clone)]
pub struct PycModule {
    pub header: PycHeader,
    pub code: Rc<CodeObject>,
}

fn u32_at(data: &[u8], off: usize) -> Result<u32> {
    let b = data
        .get(off..off + 4)
        .ok_or(PycError::UnexpectedEof(off))?;
    Ok(u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
}

fn u64_at(data: &[u8], off: usize) -> Result<u64> {
    let b = data
        .get(off..off + 8)
        .ok_or(PycError::UnexpectedEof(off))?;
    Ok(u64::from_le_bytes([
        b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
    ]))
}

impl PycModule {
    /// Parse a complete pyc file (header + marshal payload).
    pub fn from_bytes(data: &[u8]) -> Result<PycModule> {
        if data.len() < 4 {
            return Err(PycError::TooShort);
        }
        let magic = u16::from_le_bytes([data[0], data[1]]);
        // bytes 2..4 are the `\r\n` separator
        if data[2] != b'\r' || data[3] != b'\n' {
            return Err(PycError::Msg(format!(
                "bad magic separator: expected \\r\\n, got {:02x?} {:02x?}",
                data[2], data[3]
            )));
        }
        let version = version_from_magic(magic)
            .ok_or(PycError::UnsupportedMagic(magic))?;
        let kind = header_kind(version);

        let mut header = PycHeader {
            magic,
            version,
            kind,
            flags: 0,
            timestamp: 0,
            source_size: 0,
            source_hash: 0,
            header_size: kind.size(),
        };

        match kind {
            HeaderKind::Magic8 => {
                header.timestamp = u32_at(data, 4)?;
            }
            HeaderKind::Magic12 => {
                header.timestamp = u32_at(data, 4)?;
                header.source_size = u32_at(data, 8)?;
            }
            HeaderKind::Pep552 => {
                header.flags = u32_at(data, 4)?;
                if header.flags & FLAG_HASH_BASED != 0 {
                    header.source_hash = u64_at(data, 8)?;
                } else {
                    header.timestamp = u32_at(data, 8)?;
                    header.source_size = u32_at(data, 12)?;
                }
            }
        }

        if data.len() < header.header_size {
            return Err(PycError::TooShort);
        }
        let code = Self::unmarshal(&data[header.header_size..], version)?;
        Ok(PycModule { header, code })
    }

    /// Load a raw marshal stream (no pyc header) for a known version.
    pub fn unmarshal(data: &[u8], version: PythonVersion) -> Result<Rc<CodeObject>> {
        let mut reader = MarshalReader::new(data, version);
        let obj = reader.load()?;
        match &*obj {
            PyObject::Code(c) => Ok(c.clone()),
            other => Err(PycError::Msg(format!(
                "top-level object is not a code object (got {})",
                other.type_name()
            ))),
        }
    }

    pub fn version(&self) -> PythonVersion {
        self.header.version
    }
}

/// Resolve a Python version for `-v X.Y` style overrides by finding the
/// final-release magic number for that (major, minor).
pub fn version_from_tuple(major: u8, minor: u8) -> Option<PythonVersion> {
    // Prefer the highest magic that maps to this exact (major, minor) with
    // the CPython implementation, skipping interim alphas where possible.
    let raw: std::collections::HashMap<String, String> =
        serde_json::from_str(include_str!("../configs/magics.json")).ok()?;
    let mut best: Option<PythonVersion> = None;
    for (magic, vs) in raw {
        let magic: u16 = magic.parse().ok()?;
        if let Some(v) = version_from_magic(magic) {
            if v.major == major
                && v.minor == minor
                && v.implementation == crate::version::Implementation::CPython
            {
                let _ = vs;
                // final releases have the highest magic within a minor series
                if best.map_or(true, |b| v.magic > b.magic) {
                    best = Some(v);
                }
            }
        }
    }
    best
}

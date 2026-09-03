//! Error types shared across the crate.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum PycError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("not a pyc file: too short")]
    TooShort,

    #[error("unsupported pyc version (magic number {0})")]
    UnsupportedMagic(u16),

    #[error("unsupported Python version {0}")]
    UnsupportedVersion(String),

    #[error("unexpected end of data at offset {0}")]
    UnexpectedEof(usize),

    #[error("invalid marshal type code {0:#04x} ('{1}') at offset {2}")]
    BadMarshalType(u8, char, usize),

    #[error("invalid object reference {0} at offset {1}")]
    BadRef(u32, usize),

    #[error("invalid utf-8 in marshalled string at offset {0}")]
    BadUtf8(usize),

    #[error("truncated code object: expected {0}, got {1}")]
    TruncatedCode(&'static str, usize),

    #[error("unknown opcode {0} for Python {1} at offset {2}")]
    UnknownOpcode(u8, String, usize),

    #[error("{0}")]
    Msg(String),
}

impl From<std::fmt::Error> for PycError {
    fn from(e: std::fmt::Error) -> Self {
        PycError::Msg(format!("format error: {e}"))
    }
}

pub type Result<T> = std::result::Result<T, PycError>;

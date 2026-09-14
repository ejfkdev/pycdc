//! pycdc — Python pyc disassembler & decompiler in Rust.
//!
//! Design goals:
//! * support every CPython release from 2.0 through 3.x (1.x partially)
//! * keep version differences in *data* (JSON opcode configs generated from
//!   xdis / CPython's opcode modules) rather than in code paths
//! * normalize instruction streams at decode time (jump targets, EXTENDED_ARG,
//!   wordcode, CACHE) so the decompiler core is version-agnostic

pub mod ast;
pub mod bytecode;
pub mod cli_disasm;
pub mod code;
pub mod codegen;
pub mod decompiler;
pub mod disasm;
pub mod error;
pub mod linetable;
pub mod loader;
pub mod marshal;
pub mod object;
pub mod opcode;
pub mod pyc;
pub mod version;

pub use error::{PycError, Result};
pub use pyc::PycModule;

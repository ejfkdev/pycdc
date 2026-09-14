//! Shared CLI helpers: pyc loading with optional version override.

use std::path::Path;
use std::rc::Rc;

use crate::code::CodeObject;
use crate::pyc::{version_from_tuple, PycHeader, PycModule};
use crate::version::PythonVersion;
use crate::Result;

/// Load a pyc file; with `version_override` treat the file as a raw marshal
/// stream for the given (major, minor) — matching pycdc's `-c -v X.Y` mode.
pub fn load(path: &Path, version_override: Option<(u8, u8)>) -> Result<Loaded> {
    let data = std::fs::read(path)?;
    load_bytes(&data, version_override)
}

/// Load from an in-memory buffer (stdin input, embedded data).
pub fn load_bytes(data: &[u8], version_override: Option<(u8, u8)>) -> Result<Loaded> {
    match version_override {
        Some((maj, min)) => {
            let version = version_from_tuple(maj, min).ok_or_else(|| {
                crate::PycError::UnsupportedVersion(format!("{maj}.{min}"))
            })?;
            let code = PycModule::unmarshal(&data, version)?;
            Ok(Loaded { version, code, header: None })
        }
        None => {
            let module = PycModule::from_bytes(&data)?;
            Ok(Loaded {
                version: module.version(),
                code: module.code.clone(),
                header: Some(module.header.clone()),
            })
        }
    }
}

pub struct Loaded {
    pub version: PythonVersion,
    pub code: Rc<CodeObject>,
    pub header: Option<PycHeader>,
}

/// Read the input bytes for a CLI path: `-` means stdin.
pub fn read_input(path: &Path) -> std::io::Result<Vec<u8>> {
    use std::io::Read;
    if path == Path::new("-") {
        let mut buf = Vec::new();
        std::io::stdin().read_to_end(&mut buf)?;
        Ok(buf)
    } else {
        std::fs::read(path)
    }
}

/// Parse a `-v X.Y` argument.
pub fn parse_version_arg(s: &str) -> Option<(u8, u8)> {
    let mut parts = s.split('.');
    let major: u8 = parts.next()?.parse().ok()?;
    let minor: u8 = parts.next()?.parse().ok()?;
    Some((major, minor))
}

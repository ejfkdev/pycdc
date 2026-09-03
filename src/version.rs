//! Python version identification: magic number table and header layout rules.

use std::collections::HashMap;
use std::sync::OnceLock;

/// Which Python implementation produced a pyc file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Implementation {
    CPython,
    PyPy,
    Jython,
    Pyston,
    Graal,
    RustPython,
    Dropbox,
    Unknown,
}

impl Implementation {
    pub fn name(self) -> &'static str {
        match self {
            Implementation::CPython => "CPython",
            Implementation::PyPy => "PyPy",
            Implementation::Jython => "Jython",
            Implementation::Pyston => "Pyston",
            Implementation::Graal => "GraalPython",
            Implementation::RustPython => "RustPython",
            Implementation::Dropbox => "Dropbox",
            Implementation::Unknown => "Unknown",
        }
    }
}

/// A concrete Python version (major.minor.patch) plus the implementation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PythonVersion {
    pub major: u8,
    pub minor: u8,
    pub patch: u8,
    pub implementation: Implementation,
    /// The raw magic number this version info was derived from.
    pub magic: u16,
    /// The raw version string from the magic table (e.g. "3.8.0rc1+").
    pub raw: &'static str,
}

impl PythonVersion {
    /// Ordered `(major, minor)` tuple for comparisons.
    pub fn tuple(self) -> (u8, u8) {
        (self.major, self.minor)
    }

    /// `self >= (major, minor)` for CPython; alternative implementations are
    /// compared by their version tuple as well (best effort).
    pub fn at_least(self, major: u8, minor: u8) -> bool {
        (self.major, self.minor) >= (major, minor)
    }

    pub fn at_most(self, major: u8, minor: u8) -> bool {
        (self.major, self.minor) <= (major, minor)
    }

    /// Instruction stream uses fixed 2-byte "wordcode" (PEP 526).
    pub fn is_wordcode(self) -> bool {
        self.at_least(3, 6)
    }

    /// Jump operands are counted in instruction words, not bytes (bpo-27129).
    pub fn jumps_in_words(self) -> bool {
        self.at_least(3, 10)
    }

    /// Code objects have the inline CACHE entries after some instructions.
    pub fn has_cache_entries(self) -> bool {
        self.at_least(3, 11)
    }

    /// 3.12+ folded many special-form CALL instructions into CALL/CALL_KW.
    pub fn has_call_kw(self) -> bool {
        self.at_least(3, 13)
    }

    pub fn is_python2(self) -> bool {
        self.major == 2
    }

    pub fn display(self) -> String {
        if self.patch > 0 {
            format!("{}.{}.{}", self.major, self.minor, self.patch)
        } else {
            format!("{}.{}", self.major, self.minor)
        }
    }
}

impl std::fmt::Display for PythonVersion {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.display())
    }
}

/// Parse a version string from the xdis magic table, e.g.
/// "3.8.0rc1+", "2.7PyPy", "3.12.0.rust", "3.000+2", "3.8.5Graal (15)".
fn parse_version_string(s: &str, magic: u16) -> Option<PythonVersion> {
    let implementation = {
        let lower = s.to_ascii_lowercase();
        if lower.contains("pypy") {
            Implementation::PyPy
        } else if lower.contains("pyston") {
            Implementation::Pyston
        } else if lower.contains("jython") {
            Implementation::Jython
        } else if lower.contains("graal") {
            Implementation::Graal
        } else if lower.contains("rust") {
            Implementation::RustPython
        } else if lower.contains("dropbox") {
            Implementation::Dropbox
        } else {
            Implementation::CPython
        }
    };

    // Read the leading "N(.N)*" numeric portion.
    let bytes = s.as_bytes();
    let mut i = 0;
    let mut parts: Vec<u32> = Vec::new();
    while i < bytes.len() {
        let start = i;
        while i < bytes.len() && bytes[i].is_ascii_digit() {
            i += 1;
        }
        if start == i {
            break;
        }
        parts.push(s[start..i].parse().ok()?);
        if i < bytes.len() && bytes[i] == b'.' {
            i += 1;
            // A non-digit after the dot ends the numeric portion
            // (e.g. "3.12.0.rust" -> 3.12.0; "3.10.b1" -> 3.10).
            if i >= bytes.len() || !bytes[i].is_ascii_digit() {
                break;
            }
        } else {
            break;
        }
    }
    if parts.is_empty() {
        return None;
    }
    let major = *parts.first()? as u8;
    let minor = parts.get(1).copied().unwrap_or(0) as u8;
    let patch = parts.get(2).copied().unwrap_or(0) as u8;
    Some(PythonVersion {
        major,
        minor,
        patch,
        implementation,
        magic,
        raw: Box::leak(s.to_string().into_boxed_str()),
    })
}

fn magic_table() -> &'static HashMap<u16, PythonVersion> {
    static TABLE: OnceLock<HashMap<u16, PythonVersion>> = OnceLock::new();
    TABLE.get_or_init(|| {
        let raw: HashMap<String, String> =
            serde_json::from_str(include_str!("../configs/magics.json"))
                .expect("configs/magics.json is valid JSON");
        let mut table = HashMap::with_capacity(raw.len());
        for (magic, version) in raw {
            let magic: u16 = magic.parse().expect("magic key is a u16");
            if let Some(v) = parse_version_string(&version, magic) {
                table.entry(magic).or_insert(v);
            }
        }
        table
    })
}

/// Identify a Python version from the 2-byte magic integer of a pyc file.
pub fn version_from_magic(magic: u16) -> Option<PythonVersion> {
    magic_table().get(&magic).copied()
}

/// pyc header layout, per PEP 552 and earlier conventions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HeaderKind {
    /// magic(4) + mtime(4): Python 1.x - 3.2
    Magic8,
    /// magic(4) + mtime(4) + source_size(4): Python 3.3 - 3.6
    Magic12,
    /// magic(4) + flags(4) + {mtime(4)+source_size(4) | hash(8)}: Python 3.7+
    Pep552,
}

impl HeaderKind {
    pub fn size(self) -> usize {
        match self {
            HeaderKind::Magic8 => 8,
            HeaderKind::Magic12 => 12,
            HeaderKind::Pep552 => 16,
        }
    }
}

/// Determine the header layout for a version/magic combination.
/// Magic 3393 (3.7.0beta3) always uses the hash-based layout.
pub fn header_kind(version: PythonVersion) -> HeaderKind {
    if version.at_least(3, 7) || version.magic == 3393 {
        HeaderKind::Pep552
    } else if version.at_least(3, 3) {
        HeaderKind::Magic12
    } else {
        HeaderKind::Magic8
    }
}

/// PEP 552 pyc flags.
pub const FLAG_HASH_BASED: u32 = 1 << 0;
pub const FLAG_CHECK_SOURCE: u32 = 1 << 1;
pub const FLAG_UNCHECKED_HASH: u32 = 1 << 2;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_version_strings() {
        let v = parse_version_string("3.8.0rc1+", 3413).unwrap();
        assert_eq!((v.major, v.minor, v.patch), (3, 8, 0));
        assert_eq!(v.implementation, Implementation::CPython);

        let v = parse_version_string("2.7PyPy", 62218).unwrap();
        assert_eq!(v.tuple(), (2, 7));
        assert_eq!(v.implementation, Implementation::PyPy);

        let v = parse_version_string("3.12.0.rust", 12897).unwrap();
        assert_eq!(v.tuple(), (3, 12));
        assert_eq!(v.implementation, Implementation::RustPython);

        let v = parse_version_string("3.000+2", 3020).unwrap();
        assert_eq!(v.tuple(), (3, 0));

        let v = parse_version_string("3.10.b1", 3438).unwrap();
        assert_eq!(v.tuple(), (3, 10));

        let v = parse_version_string("3.8.5Graal (15)", 21150).unwrap();
        assert_eq!(v.implementation, Implementation::Graal);
    }

    #[test]
    fn known_magics() {
        assert_eq!(version_from_magic(62211).unwrap().tuple(), (2, 7));
        assert_eq!(version_from_magic(3394).unwrap().tuple(), (3, 7));
        assert_eq!(version_from_magic(3413).unwrap().tuple(), (3, 8));
        assert_eq!(version_from_magic(3531).unwrap().tuple(), (3, 12));
        assert_eq!(version_from_magic(3571).unwrap().tuple(), (3, 13));
        assert!(version_from_magic(1234).is_none());
    }

    #[test]
    fn header_kinds() {
        let v = |m: u16| header_kind(version_from_magic(m).unwrap());
        assert_eq!(v(62211), HeaderKind::Magic8); // 2.7
        assert_eq!(v(3230), HeaderKind::Magic12); // 3.3
        assert_eq!(v(3379), HeaderKind::Magic12); // 3.6
        assert_eq!(v(3394), HeaderKind::Pep552); // 3.7
    }
}

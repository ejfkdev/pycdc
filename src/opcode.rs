//! Per-version opcode tables, loaded from embedded JSON configs generated
//! by `tools/gen_configs.py` (data originally derived from xdis and the
//! CPython `opcode` modules).
//!
//! Version differences are *data*: the rest of the crate works against the
//! canonical [`Op`] enum and normalized [`Instruction`](crate::bytecode)
//! streams regardless of Python version.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use serde::Deserialize;

use crate::error::{PycError, Result};
use crate::version::PythonVersion;

#[allow(non_camel_case_types, clippy::all)]
mod gen_ops {
    include!(concat!(env!("OUT_DIR"), "/opnames.inc"));
}
pub use gen_ops::Op;

#[derive(Debug, Deserialize)]
struct OpcodeConfig {
    version: String,
    #[allow(dead_code)]
    implementation: String,
    have_argument: u16,
    wordcode: bool,
    opmap: HashMap<String, u16>,
    #[serde(default)]
    hasjrel: Vec<u16>,
    #[serde(default)]
    hasjabs: Vec<u16>,
    #[serde(default)]
    hasarg: Vec<u16>,
    #[serde(default)]
    hascompare: Vec<u16>,
    #[serde(default)]
    hasconst: Vec<u16>,
    #[serde(default)]
    hasname: Vec<u16>,
    #[serde(default)]
    haslocal: Vec<u16>,
    #[serde(default)]
    hasfree: Vec<u16>,
    #[serde(default)]
    nofollow: Vec<u16>,
    cmp_op: Vec<String>,
    #[serde(default)]
    cache_entries: HashMap<String, u16>,
}

/// A resolved, ready-to-use opcode table for one Python version.
pub struct OpcodeTable {
    pub version_label: String,
    pub have_argument: u16,
    pub wordcode: bool,
    /// byte -> name (empty string when unused)
    names: Vec<String>,
    /// byte -> canonical op
    ops: Vec<Op>,
    byte_of: HashMap<String, u8>,
    has_arg: Vec<bool>,
    jrel: Vec<bool>,
    jabs: Vec<bool>,
    compare: Vec<bool>,
    is_const: Vec<bool>,
    is_name: Vec<bool>,
    is_local: Vec<bool>,
    is_free: Vec<bool>,
    nofollow: Vec<bool>,
    cache: Vec<u8>,
    pub cmp_op: Vec<String>,
}

fn flags(len: usize, entries: &[u16]) -> Vec<bool> {
    let mut v = vec![false; len];
    for &b in entries {
        if (b as usize) < len {
            v[b as usize] = true;
        }
    }
    v
}

impl OpcodeTable {
    fn from_config(cfg: OpcodeConfig) -> Result<OpcodeTable> {
        let mut names = vec![String::new(); 256];
        let mut ops = vec![Op::Unknown; 256];
        let mut byte_of = HashMap::new();
        for (name, byte) in &cfg.opmap {
            // 3.12+ pseudo-instructions have codes >= 256; skip them.
            let b = *byte as usize;
            if b < 256 {
                names[b] = name.clone();
                ops[b] = Op::from_name(name);
                byte_of.insert(name.clone(), *byte as u8);
            }
        }
        let has_arg = if cfg.hasarg.is_empty() {
            (0..256u16).map(|b| b >= cfg.have_argument).collect()
        } else {
            flags(256, &cfg.hasarg)
        };
        let mut cache = vec![0u8; 256];
        for (k, n) in &cfg.cache_entries {
            if let Ok(b) = k.parse::<usize>() {
                if b < 256 {
                    cache[b] = *n as u8;
                }
            }
        }
        Ok(OpcodeTable {
            version_label: cfg.version,
            have_argument: cfg.have_argument,
            wordcode: cfg.wordcode,
            names,
            ops,
            byte_of,
            has_arg,
            jrel: flags(256, &cfg.hasjrel),
            jabs: flags(256, &cfg.hasjabs),
            compare: flags(256, &cfg.hascompare),
            is_const: flags(256, &cfg.hasconst),
            is_name: flags(256, &cfg.hasname),
            is_local: flags(256, &cfg.haslocal),
            is_free: flags(256, &cfg.hasfree),
            nofollow: flags(256, &cfg.nofollow),
            cache,
            cmp_op: cfg.cmp_op,
        })
    }

    pub fn name(&self, byte: u8) -> &str {
        let n = &self.names[byte as usize];
        if n.is_empty() {
            "<unknown>"
        } else {
            n
        }
    }

    pub fn op(&self, byte: u8) -> Op {
        self.ops[byte as usize]
    }

    pub fn byte_for(&self, name: &str) -> Option<u8> {
        self.byte_of.get(name).copied()
    }

    pub fn has_arg(&self, byte: u8) -> bool {
        self.has_arg[byte as usize]
    }

    pub fn is_jrel(&self, byte: u8) -> bool {
        self.jrel[byte as usize]
    }

    pub fn is_jabs(&self, byte: u8) -> bool {
        self.jabs[byte as usize]
    }

    pub fn is_jump(&self, byte: u8) -> bool {
        self.is_jrel(byte) || self.is_jabs(byte)
    }

    pub fn is_compare(&self, byte: u8) -> bool {
        self.compare[byte as usize]
    }

    pub fn takes_const(&self, byte: u8) -> bool {
        self.is_const[byte as usize]
    }

    pub fn takes_name(&self, byte: u8) -> bool {
        self.is_name[byte as usize]
    }

    pub fn takes_local(&self, byte: u8) -> bool {
        self.is_local[byte as usize]
    }

    pub fn takes_free(&self, byte: u8) -> bool {
        self.is_free[byte as usize]
    }

    pub fn is_nofollow(&self, byte: u8) -> bool {
        self.nofollow[byte as usize]
    }

    /// Number of CACHE code-units following this opcode (3.11+).
    pub fn cache_entries(&self, byte: u8) -> u8 {
        self.cache[byte as usize]
    }
}

/// Raw embedded config texts, keyed by (major, minor). Tables are parsed
/// lazily per version — a single-file run touches one config, not all 24
/// (the eager parse-everything map cost startup time and ~MBs of RSS).
fn embedded_raw() -> &'static [(u8, u8, &'static str)] {
    macro_rules! configs {
        ($(($maj:literal, $min:literal, $file:literal)),* $(,)?) => {{
            &[$(($maj, $min, include_str!(concat!("../configs/opcodes/", $file)))),*]
        }};
    }
    configs![
        (2, 0, "python_2_0.json"), (2, 1, "python_2_1.json"),
        (2, 2, "python_2_2.json"), (2, 3, "python_2_3.json"),
        (2, 4, "python_2_4.json"), (2, 5, "python_2_5.json"),
        (2, 6, "python_2_6.json"), (2, 7, "python_2_7.json"),
        (3, 0, "python_3_0.json"), (3, 1, "python_3_1.json"),
        (3, 2, "python_3_2.json"), (3, 3, "python_3_3.json"),
        (3, 4, "python_3_4.json"), (3, 5, "python_3_5.json"),
        (3, 6, "python_3_6.json"), (3, 7, "python_3_7.json"),
        (3, 8, "python_3_8.json"), (3, 9, "python_3_9.json"),
        (3, 10, "python_3_10.json"), (3, 11, "python_3_11.json"),
        (3, 12, "python_3_12.json"), (3, 13, "python_3_13.json"),
        (3, 14, "python_3_14.json"), (3, 15, "python_3_15.json"),
    ]
}

/// Parsed-table cache, one lock-free slot per (major, minor). Parsed tables
/// are leaked so they can be handed out as 'static references (the previous
/// eager map did the same via its 'static lifetime).
fn embedded_tables() -> &'static [OnceLock<Option<&'static OpcodeTable>>] {
    static TABLES: OnceLock<Vec<OnceLock<Option<&'static OpcodeTable>>>> = OnceLock::new();
    TABLES.get_or_init(|| (0..EMBEDDED_SLOTS).map(|_| OnceLock::new()).collect())
}

const EMBEDDED_SLOTS: usize = 16 * 16;

#[inline]
fn slot_key(major: u8, minor: u8) -> usize {
    (major as usize) * 16 + (minor as usize)
}

fn embedded_table(major: u8, minor: u8) -> Option<&'static OpcodeTable> {
    if major as usize * 16 + minor as usize >= EMBEDDED_SLOTS {
        return None;
    }
    let slot = &embedded_tables()[slot_key(major, minor)];
    *slot.get_or_init(|| {
        let text = embedded_raw()
            .iter()
            .find(|(ma, mi, _)| *ma == major && *mi == minor)
            .map(|(_, _, t)| *t)?;
        let cfg: OpcodeConfig = serde_json::from_str(text).expect("embedded config parses");
        // the embedded file names pin the version; still verify the content
        // agrees so a regenerated config can never land in the wrong slot
        let mut parts = cfg.version.split('.');
        let cfg_major: u8 = parts.next().unwrap().parse().expect("major");
        let cfg_minor: u8 = parts.next().unwrap().parse().expect("minor");
        assert!(
            (cfg_major, cfg_minor) == (major, minor),
            "embedded config version mismatch: slot {major}.{minor} vs {}.{}",
            cfg_major,
            cfg_minor
        );
        Some(Box::leak(Box::new(
            OpcodeTable::from_config(cfg).expect("table builds"),
        )))
    })
}

/// External config overrides, populated by `set_override_dir`. Tables are
/// leaked so they can be handed out as 'static references (CLI lifetime).
fn override_tables() -> &'static Mutex<HashMap<(u8, u8), &'static OpcodeTable>> {
    static OVERRIDES: OnceLock<Mutex<HashMap<(u8, u8), &'static OpcodeTable>>> = OnceLock::new();
    OVERRIDES.get_or_init(|| Mutex::new(HashMap::new()))
}

/// Load additional/override opcode configs from a directory of JSON files
/// (same schema as `configs/opcodes/`). Later files override embedded ones
/// for the same (major, minor).
pub fn set_override_dir(dir: &std::path::Path) -> Result<()> {
    let entries = std::fs::read_dir(dir).map_err(|e| {
        PycError::Msg(format!("cannot read opcode config dir {}: {e}", dir.display()))
    })?;
    let mut overrides = override_tables().lock().unwrap();
    for entry in entries {
        let path = entry.map_err(|e| PycError::Msg(e.to_string()))?.path();
        if path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let text = std::fs::read_to_string(&path)
            .map_err(|e| PycError::Msg(format!("{}: {e}", path.display())))?;
        let cfg: OpcodeConfig = serde_json::from_str(&text)
            .map_err(|e| PycError::Msg(format!("{}: {e}", path.display())))?;
        let mut parts = cfg.version.split('.');
        let major: u8 = parts
            .next()
            .and_then(|s| s.parse().ok())
            .ok_or_else(|| PycError::Msg(format!("{}: bad version", path.display())))?;
        let minor: u8 = parts
            .next()
            .and_then(|s| s.parse().ok())
            .ok_or_else(|| PycError::Msg(format!("{}: bad version", path.display())))?;
        let table = OpcodeTable::from_config(cfg)?;
        overrides.insert((major, minor), Box::leak(Box::new(table)));
    }
    Ok(())
}

/// Get the opcode table for a version. Interim releases (alphas/betas) and
/// alternative implementations fall back to the matching (major, minor)
/// CPython table.
pub fn table_for(version: PythonVersion) -> Result<&'static OpcodeTable> {
    let key = version.tuple();
    {
        let overrides = override_tables().lock().unwrap();
        if let Some(t) = overrides.get(&key) {
            return Ok(t);
        }
    }
    embedded_table(key.0, key.1).ok_or(PycError::UnsupportedVersion(version.display()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::version::version_from_magic;

    #[test]
    fn py27_table() {
        let v = version_from_magic(62211).unwrap();
        let t = table_for(v).unwrap();
        assert_eq!(t.byte_for("LOAD_CONST").unwrap(), 100);
        assert_eq!(t.op(100), Op::LOAD_CONST);
        assert!(t.has_arg(100));
        assert!(!t.has_arg(1)); // POP_TOP
        assert_eq!(t.name(1), "POP_TOP");
        assert!(t.is_jabs(t.byte_for("JUMP_ABSOLUTE").unwrap()));
        assert!(t.is_jrel(t.byte_for("JUMP_FORWARD").unwrap()));
    }

    #[test]
    fn py311_table() {
        let v = version_from_magic(3495).unwrap();
        let t = table_for(v).unwrap();
        assert!(t.wordcode);
        assert_eq!(t.op(t.byte_for("BINARY_OP").unwrap()), Op::BINARY_OP);
        assert!(t.cache_entries(t.byte_for("CALL").unwrap()) > 0);
        assert!(t.is_jrel(t.byte_for("JUMP_BACKWARD").unwrap()));
        assert!(t.hasjabs_empty());
    }

    #[test]
    fn all_versions_load() {
        for magic in [
            50823u16, 60202, 60717, 62041, 62061, 62131, 62161, 62211, // 2.0-2.7
            3131, 3151, 3180, 3230, 3310, 3351, 3379, 3394, 3413, 3425, 3439, 3495, 3531,
            3571, 3627,
        ] {
            let v = version_from_magic(magic).expect("magic known");
            let t = table_for(v).unwrap_or_else(|_| panic!("table for {}", v.display()));
            assert!(t.byte_for("LOAD_CONST").is_some(), "{}", v.display());
            assert!(t.byte_for("RETURN_VALUE").is_some(), "{}", v.display());
        }
    }

    impl OpcodeTable {
        fn hasjabs_empty(&self) -> bool {
            !self.jabs.iter().any(|b| *b)
        }
    }
}

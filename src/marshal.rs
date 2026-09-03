//! Marshal (pyc payload) deserializer for every Python version.
//!
//! One reader handles all format generations:
//!   * marshal v0 (< 2.4): string-encoded floats, no sets, no refs
//!   * py2: TYPE_INT64, interned-string table, 4-byte int encoding
//!   * 3.0-3.3: unicode strings, still no FLAG_REF
//!   * 3.4+: FLAG_REF high bit, object reference table, variable-length
//!     ints, short ascii strings, small tuples
//!   * 3.14+: TYPE_SLICE; 3.15: TYPE_FROZENDICT

use std::rc::Rc;

use crate::code::{CodeObject, CO_FAST_CELL, CO_FAST_FREE, CO_FAST_LOCAL};
use crate::error::{PycError, Result};
use crate::object::{ObjectRef, PycLong, PyObject};
use crate::version::PythonVersion;

// marshal type codes
const TYPE_NULL: u8 = b'0';
const TYPE_NONE: u8 = b'N';
const TYPE_STOPITER: u8 = b'S';
const TYPE_ELLIPSIS: u8 = b'.';
const TYPE_FALSE: u8 = b'F';
const TYPE_TRUE: u8 = b'T';
const TYPE_INT: u8 = b'i';
const TYPE_INT64: u8 = b'I';
const TYPE_LONG: u8 = b'l';
const TYPE_FLOAT: u8 = b'f';
const TYPE_BINARY_FLOAT: u8 = b'g';
const TYPE_COMPLEX: u8 = b'x';
const TYPE_BINARY_COMPLEX: u8 = b'y';
const TYPE_CODE: u8 = b'c';
const TYPE_INTERNED: u8 = b't';
const TYPE_UNICODE: u8 = b'u';
const TYPE_ASCII: u8 = b'a';
const TYPE_ASCII_INTERNED: u8 = b'A';
const TYPE_SHORT_ASCII: u8 = b'z';
const TYPE_SHORT_ASCII_INTERNED: u8 = b'Z';
const TYPE_STRING: u8 = b's';
const TYPE_STRINGREF: u8 = b'R';
const TYPE_REF: u8 = b'r';
const TYPE_TUPLE: u8 = b'(';
const TYPE_SMALL_TUPLE: u8 = b')';
const TYPE_LIST: u8 = b'[';
const TYPE_DICT: u8 = b'{';
const TYPE_FROZENDICT: u8 = b'}';
const TYPE_SLICE: u8 = b':';
const TYPE_SET: u8 = b'<';
const TYPE_FROZENSET: u8 = b'>';

const FLAG_REF: u8 = 0x80;

/// 3.8 alphas whose code objects lack the posonlyargcount field.
fn is_py38_alpha_without_posonly(magic: u16) -> bool {
    matches!(magic, 3400 | 3401 | 3410 | 3411)
}

pub struct MarshalReader<'a> {
    data: &'a [u8],
    pos: usize,
    version: PythonVersion,
    /// Object reference table (3.4+ TYPE_REF).
    refs: Vec<Option<ObjectRef>>,
    /// Interned string table (py2 TYPE_STRINGREF).
    interned: Vec<ObjectRef>,
}

impl<'a> MarshalReader<'a> {
    pub fn new(data: &'a [u8], version: PythonVersion) -> Self {
        MarshalReader {
            data,
            pos: 0,
            version,
            refs: Vec::new(),
            interned: Vec::new(),
        }
    }

    pub fn position(&self) -> usize {
        self.pos
    }

    pub fn at_eof(&self) -> bool {
        self.pos >= self.data.len()
    }

    fn byte(&mut self) -> Result<u8> {
        let b = *self.data.get(self.pos).ok_or(PycError::UnexpectedEof(self.pos))?;
        self.pos += 1;
        Ok(b)
    }

    fn peek_byte(&self) -> Result<u8> {
        self.data.get(self.pos).copied().ok_or(PycError::UnexpectedEof(self.pos))
    }

    fn bytes(&mut self, n: usize) -> Result<&'a [u8]> {
        let end = self.pos.checked_add(n).ok_or(PycError::UnexpectedEof(self.pos))?;
        if end > self.data.len() {
            return Err(PycError::UnexpectedEof(self.pos));
        }
        let s = &self.data[self.pos..end];
        self.pos = end;
        Ok(s)
    }

    fn u16(&mut self) -> Result<u16> {
        let b = self.bytes(2)?;
        Ok(u16::from_le_bytes([b[0], b[1]]))
    }

    fn u32(&mut self) -> Result<u32> {
        let b = self.bytes(4)?;
        Ok(u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
    }

    fn i32(&mut self) -> Result<i32> {
        let b = self.bytes(4)?;
        Ok(i32::from_le_bytes([b[0], b[1], b[2], b[3]]))
    }

    fn u64(&mut self) -> Result<u64> {
        let b = self.bytes(8)?;
        Ok(u64::from_le_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]]))
    }

    fn f64(&mut self) -> Result<f64> {
        let b = self.bytes(8)?;
        Ok(f64::from_le_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]]))
    }

    /// Integer header fields of code objects: u16 for Python 1.x/2.0-2.2,
    /// i32 for Python 2.3+.
    fn code_field_u32(&mut self) -> Result<u32> {
        if self.version.at_least(2, 3) || self.version.major >= 3 {
            Ok(self.i32()? as u32)
        } else {
            Ok(self.u16()? as u32)
        }
    }

    fn size(&mut self) -> Result<usize> {
        Ok(self.u32()? as usize)
    }

    fn flag_ref_enabled(&self) -> bool {
        self.version.at_least(3, 4)
    }

    fn r_ref(&mut self, obj: &ObjectRef) {
        self.refs.push(Some(obj.clone()));
    }

    /// Reserve a slot (containers may be referenced while under construction).
    fn r_ref_reserve(&mut self) -> usize {
        self.refs.push(None);
        self.refs.len() - 1
    }

    fn r_ref_insert(&mut self, slot: usize, obj: &ObjectRef) {
        if let Some(entry) = self.refs.get_mut(slot) {
            *entry = Some(obj.clone());
        }
    }

    /// Load the top-level object.
    pub fn load(&mut self) -> Result<ObjectRef> {
        self.load_object()
    }

    fn load_object(&mut self) -> Result<ObjectRef> {
        let start = self.pos;
        let raw = self.byte()?;
        let flag_ref = self.flag_ref_enabled() && raw & FLAG_REF != 0;
        let code = raw & 0x7F;

        // Types whose FLAG_REF registration happens inside their branch
        // (containers reserve a slot before recursing).
        macro_rules! self_registered {
            () => {
                matches!(
                    code,
                    TYPE_TUPLE
                        | TYPE_SMALL_TUPLE
                        | TYPE_LIST
                        | TYPE_SET
                        | TYPE_FROZENSET
                        | TYPE_CODE
                )
            };
        }

        let obj = match code {
            TYPE_NONE => Rc::new(PyObject::None),
            TYPE_STOPITER => Rc::new(PyObject::StopIteration),
            TYPE_ELLIPSIS => Rc::new(PyObject::Ellipsis),
            TYPE_FALSE => Rc::new(PyObject::False),
            TYPE_TRUE => Rc::new(PyObject::True),
            TYPE_INT => self.load_int()?,
            TYPE_INT64 => {
                if self.version.at_least(3, 4) {
                    return Err(PycError::BadMarshalType(code, 'I', start));
                }
                Rc::new(PyObject::Long(PycLong::from_digits(false, &u64_to_digits(self.u64()?))))
            }
            TYPE_LONG => self.load_long()?,
            TYPE_FLOAT => {
                // v0: 1-byte length + decimal repr
                let n = self.byte()? as usize;
                let s = std::str::from_utf8(self.bytes(n)?)
                    .map_err(|_| PycError::BadUtf8(self.pos))?
                    .to_string();
                let v: f64 = s.parse().map_err(|_| {
                    PycError::Msg(format!("invalid float literal {s:?} at offset {start}"))
                })?;
                Rc::new(PyObject::Float(v, Some(s)))
            }
            TYPE_BINARY_FLOAT => Rc::new(PyObject::Float(self.f64()?, None)),
            TYPE_COMPLEX => {
                let (re, im) = self.load_legacy_complex(start)?;
                Rc::new(PyObject::Complex(re, im))
            }
            TYPE_BINARY_COMPLEX => {
                let re = self.f64()?;
                let im = self.f64()?;
                Rc::new(PyObject::Complex(re, im))
            }
            TYPE_STRING => {
                let n = self.size()?;
                let b = self.bytes(n)?.to_vec();
                Rc::new(PyObject::Bytes(b))
            }
            TYPE_INTERNED | TYPE_UNICODE => self.load_utf8_string(code)?,
            TYPE_ASCII | TYPE_SHORT_ASCII => {
                if !self.version.at_least(3, 4) {
                    return Err(PycError::BadMarshalType(code, code as char, start));
                }
                let n = if code == TYPE_SHORT_ASCII {
                    self.byte()? as usize
                } else {
                    self.size()?
                };
                let b = self.bytes(n)?;
                Rc::new(PyObject::Str(
                    String::from_utf8(b.to_vec()).map_err(|_| PycError::BadUtf8(self.pos))?,
                ))
            }
            TYPE_ASCII_INTERNED | TYPE_SHORT_ASCII_INTERNED => {
                if !self.version.at_least(3, 4) {
                    return Err(PycError::BadMarshalType(code, code as char, start));
                }
                let n = if code == TYPE_SHORT_ASCII_INTERNED {
                    self.byte()? as usize
                } else {
                    self.size()?
                };
                let b = self.bytes(n)?;
                let s = Rc::new(PyObject::Str(
                    String::from_utf8(b.to_vec()).map_err(|_| PycError::BadUtf8(self.pos))?,
                ));
                self.interned.push(s.clone());
                s
            }
            TYPE_STRINGREF => {
                // py2 interned-string reference
                let idx = self.u32()? as usize;
                self.interned
                    .get(idx)
                    .cloned()
                    .ok_or(PycError::BadRef(idx as u32, start))?
            }
            TYPE_REF => {
                if !self.flag_ref_enabled() {
                    return Err(PycError::BadMarshalType(code, 'r', start));
                }
                let idx = self.u32()? as usize;
                self.refs
                    .get(idx)
                    .and_then(|o| o.clone())
                    .ok_or(PycError::BadRef(idx as u32, start))?
            }
            TYPE_TUPLE | TYPE_SMALL_TUPLE => {
                let n = if code == TYPE_SMALL_TUPLE {
                    if !self.version.at_least(3, 4) {
                        return Err(PycError::BadMarshalType(code, ')', start));
                    }
                    self.byte()? as usize
                } else {
                    self.size()?
                };
                let slot = if flag_ref { self.r_ref_reserve() } else { usize::MAX };
                let mut items = Vec::with_capacity(n);
                for _ in 0..n {
                    items.push(self.load_object()?);
                }
                let t = Rc::new(PyObject::Tuple(items));
                if flag_ref {
                    self.r_ref_insert(slot, &t);
                }
                return Ok(t);
            }
            TYPE_LIST => {
                let n = self.size()?;
                let slot = if flag_ref { self.r_ref_reserve() } else { usize::MAX };
                let mut items = Vec::with_capacity(n);
                for _ in 0..n {
                    items.push(self.load_object()?);
                }
                let l = Rc::new(PyObject::List(items));
                if flag_ref {
                    self.r_ref_insert(slot, &l);
                }
                return Ok(l);
            }
            TYPE_DICT | TYPE_FROZENDICT => {
                let mut entries = Vec::new();
                loop {
                    if self.peek_byte()? & 0x7F == TYPE_NULL {
                        self.pos += 1;
                        break;
                    }
                    let k = self.load_object()?;
                    let v = self.load_object()?;
                    entries.push((k, v));
                }
                Rc::new(PyObject::Dict(entries))
            }
            TYPE_SET | TYPE_FROZENSET => {
                let n = self.size()?;
                let slot = if flag_ref { self.r_ref_reserve() } else { usize::MAX };
                let mut items = Vec::with_capacity(n);
                for _ in 0..n {
                    items.push(self.load_object()?);
                }
                let s = Rc::new(if code == TYPE_SET {
                    PyObject::Set(items)
                } else {
                    PyObject::FrozenSet(items)
                });
                if flag_ref {
                    self.r_ref_insert(slot, &s);
                }
                return Ok(s);
            }
            TYPE_SLICE => {
                // 3.14+: (start, stop, step)
                let start_o = self.load_object()?;
                let stop_o = self.load_object()?;
                let step_o = self.load_object()?;
                Rc::new(PyObject::Slice(start_o, stop_o, step_o))
            }
            TYPE_CODE => {
                let slot = if flag_ref { self.r_ref_reserve() } else { usize::MAX };
                let c = self.load_code()?;
                let obj: ObjectRef = Rc::new(PyObject::Code(c));
                if flag_ref {
                    self.r_ref_insert(slot, &obj);
                }
                return Ok(obj);
            }
            TYPE_NULL => {
                return Err(PycError::Msg(format!("unexpected TYPE_NULL at offset {start}")))
            }
            _ => {
                return Err(PycError::BadMarshalType(
                    code,
                    if code.is_ascii_graphic() { code as char } else { '?' },
                    start,
                ))
            }
        };

        if flag_ref && !self_registered!() {
            self.r_ref(&obj);
        }
        Ok(obj)
    }

    fn load_int(&mut self) -> Result<ObjectRef> {
        // TYPE_INT is a fixed 4-byte little-endian i32 in every CPython
        // version (verified against real 3.11/3.12 marshal dumps).
        Ok(Rc::new(PyObject::Int(self.i32()?)))
    }

    fn load_long(&mut self) -> Result<ObjectRef> {
        let ndigits = self.i32()?;
        let negative = ndigits < 0;
        let n = ndigits.unsigned_abs() as usize;
        let mut digits = Vec::with_capacity(n);
        for _ in 0..n {
            digits.push(self.u16()?);
        }
        Ok(Rc::new(PyObject::Long(PycLong::from_digits(negative, &digits))))
    }

    /// v0 complex: two decimal strings; length prefix is 1 byte for
    /// <= 2.4 (magic <= 62061) and i32 afterwards.
    fn load_legacy_complex(&mut self, start: usize) -> Result<(f64, f64)> {
        let read_one = |r: &mut Self| -> Result<f64> {
            let n = if r.version.magic <= 62061 {
                r.byte()? as usize
            } else {
                r.i32()? as usize
            };
            let s = std::str::from_utf8(r.bytes(n)?).map_err(|_| PycError::BadUtf8(r.pos))?;
            s.parse::<f64>()
                .map_err(|_| PycError::Msg(format!("invalid complex part {s:?} at offset {start}")))
        };
        let re = read_one(self)?;
        let im = read_one(self)?;
        Ok((re, im))
    }

    fn load_utf8_string(&mut self, code: u8) -> Result<ObjectRef> {
        let n = self.size()?;
        let b = self.bytes(n)?.to_vec();
        // CPython writes with surrogatepass; replace invalid sequences.
        let s = String::from_utf8_lossy(&b).into_owned();
        let obj = Rc::new(PyObject::Str(s));
        // py2.4+: interned strings (and unicode on 2.x) join the
        // TYPE_STRINGREF table.
        if self.version.major == 2
            && self.version.at_least(2, 4)
            && (code == TYPE_INTERNED || code == TYPE_UNICODE)
        {
            self.interned.push(obj.clone());
        }
        Ok(obj)
    }

    fn load_string_field(&mut self) -> Result<String> {
        let obj = self.load_object()?;
        match &*obj {
            PyObject::Str(s) => Ok(s.clone()),
            PyObject::Bytes(b) => Ok(String::from_utf8_lossy(b).into_owned()),
            other => Err(PycError::Msg(format!(
                "expected string field in code object, got {}",
                other.type_name()
            ))),
        }
    }

    fn load_bytes_field(&mut self) -> Result<Vec<u8>> {
        let obj = self.load_object()?;
        match &*obj {
            PyObject::Bytes(b) => Ok(b.clone()),
            PyObject::Str(s) => Ok(s.as_bytes().to_vec()),
            other => Err(PycError::Msg(format!(
                "expected bytes field in code object, got {}",
                other.type_name()
            ))),
        }
    }

    fn load_tuple_field(&mut self) -> Result<Vec<ObjectRef>> {
        let obj = self.load_object()?;
        match &*obj {
            PyObject::Tuple(items) => Ok(items.clone()),
            other => Err(PycError::Msg(format!(
                "expected tuple field in code object, got {}",
                other.type_name()
            ))),
        }
    }

    fn load_tuple_of_strings(&mut self) -> Result<Vec<String>> {
        let items = self.load_tuple_field()?;
        let mut out = Vec::with_capacity(items.len());
        for it in &items {
            match &**it {
                PyObject::Str(s) => out.push(s.clone()),
                PyObject::Bytes(b) => out.push(String::from_utf8_lossy(b).into_owned()),
                other => {
                    return Err(PycError::Msg(format!(
                        "expected string in code object tuple, got {}",
                        other.type_name()
                    )))
                }
            }
        }
        Ok(out)
    }

    fn load_code(&mut self) -> Result<Rc<CodeObject>> {
        let v = self.version;

        if v.major == 1 && v.minor < 3 {
            return Err(PycError::UnsupportedVersion(v.display()));
        }

        let arg_count = self.code_field_u32()?;

        // 3.8+ adds posonlyargcount (except early alphas)
        let posonly = if v.at_least(3, 8) && !is_py38_alpha_without_posonly(v.magic) {
            self.code_field_u32()?
        } else {
            0
        };
        let kwonly = if v.major >= 3 { self.code_field_u32()? } else { 0 };

        // nlocals: present from 1.3 through 3.10 (removed in 3.11)
        let mut n_locals = if v.at_least(3, 11) { 0 } else { self.code_field_u32()? };
        let stack_size = self.code_field_u32()?;
        let flags = self.code_field_u32()?;

        let code = self.load_bytes_field()?;
        let consts = self.load_tuple_field()?;
        let names = self.load_tuple_field()?;

        let varnames;
        let mut freevars = Vec::new();
        let mut cellvars = Vec::new();
        let mut deref_names;

        if v.at_least(3, 11) {
            // localsplusnames + localspluskinds replace varnames/freevars/cellvars
            let localsplus = self.load_tuple_of_strings()?;
            let kinds = self.load_bytes_field()?;
            deref_names = localsplus.clone();
            let mut var = Vec::new();
            let mut cell = Vec::new();
            let mut free = Vec::new();
            for (i, name) in localsplus.iter().enumerate() {
                let kind = kinds.get(i).copied().unwrap_or(CO_FAST_LOCAL);
                if kind & CO_FAST_LOCAL != 0 {
                    var.push(name.clone());
                    if kind & CO_FAST_CELL != 0 {
                        cell.push(name.clone());
                    }
                } else if kind & CO_FAST_CELL != 0 {
                    cell.push(name.clone());
                } else if kind & CO_FAST_FREE != 0 {
                    free.push(name.clone());
                }
            }
            n_locals = var.len() as u32;
            varnames = var;
            cellvars = cell;
            freevars = free;
        } else {
            varnames = self.load_tuple_of_strings()?;
            // co_freevars/co_cellvars were added in Python 2.1 (PEP 227)
            if v.at_least(2, 1) {
                freevars = self.load_tuple_of_strings()?;
                cellvars = self.load_tuple_of_strings()?;
            }
            deref_names = cellvars.clone();
            deref_names.extend(freevars.iter().cloned());
        }

        let filename = self.load_string_field()?;
        let name = self.load_string_field()?;
        let qualname = if v.at_least(3, 11) {
            self.load_string_field()?
        } else {
            String::new()
        };

        // firstlineno + line table exist since 1.5
        let (first_line, line_table) = if v.major == 1 && v.minor < 5 {
            (0u32, Vec::new())
        } else {
            (self.code_field_u32()?, self.load_bytes_field()?)
        };

        let exception_table = if v.at_least(3, 11) {
            self.load_bytes_field()?
        } else {
            Vec::new()
        };

        Ok(CodeObject::new(
            arg_count,
            posonly,
            kwonly,
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
            v.at_least(3, 11),
            v.major == 2,
        ))
    }
}

/// Split u64 into base-2^15 digits for TYPE_INT64 (rare legacy path).
fn u64_to_digits(value: u64) -> Vec<u16> {
    let mut digits = Vec::new();
    let mut v = value;
    while v > 0 {
        digits.push((v & 0x7FFF) as u16);
        v >>= 15;
    }
    digits
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::version::version_from_magic;

    fn py(magic: u16) -> PythonVersion {
        version_from_magic(magic).unwrap()
    }

    #[test]
    fn py27_simple_module() {
        // Generated by CPython 2.7: `x = 1` compiled to a module code object.
        // We build the expected structure by hand-marshalling known bytes:
        // (see tests/fixtures for real files; here just test primitives)
        let data = b"i\xfe\xff\xff\xff"; // TYPE_INT -2 (py2 fixed i32)
        let mut r = MarshalReader::new(data, py(62211));
        match &*r.load().unwrap() {
            PyObject::Int(v) => assert_eq!(*v, -2),
            o => panic!("unexpected {o:?}"),
        }
    }

    #[test]
    fn py311_int() {
        let v311 = py(3495);
        // 'i'|FLAG_REF + fixed i32 LE
        let data = [0xe9, 0x01, 0x00, 0x00, 0x00];
        let mut r = MarshalReader::new(&data, v311);
        assert!(matches!(&*r.load().unwrap(), PyObject::Int(1)));

        let data = [0xe9, 0xfe, 0xff, 0xff, 0xff]; // -2
        let mut r = MarshalReader::new(&data, v311);
        assert!(matches!(&*r.load().unwrap(), PyObject::Int(-2)));
    }

    #[test]
    fn py311_ref_table() {
        // small tuple with flag ref, then a TYPE_REF to index 0
        let data = [
            b')' | FLAG_REF, 2, b'N', b'N', // tuple(None, None) registered at 0
            b'r', 0, 0, 0, 0, // ref to it
        ];
        let mut r = MarshalReader::new(&data, py(3495));
        let first = r.load().unwrap();
        let second = r.load().unwrap();
        assert!(Rc::ptr_eq(&first, &second));
    }
}

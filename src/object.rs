//! The marshalled Python object model.

use std::fmt;
use std::rc::Rc;

use crate::code::CodeObject;

pub type ObjectRef = Rc<PyObject>;

/// A Python object as deserialized from a pyc file's marshal data.
#[derive(Debug, Clone)]
pub enum PyObject {
    None,
    Ellipsis,
    StopIteration,
    False,
    True,
    /// TYPE_INT (32-bit) — Python 2 int / small Python 3 int.
    Int(i32),
    /// TYPE_LONG — arbitrary precision integer, kept as decimal digits.
    Long(PycLong),
    /// Float with its original textual repr when marshalled as a string
    /// (Python 2 style); `None` when it came from the binary format.
    Float(f64, Option<String>),
    Complex(f64, f64),
    /// TYPE_STRING: bytes on Python 3, str on Python 2.
    Bytes(Vec<u8>),
    /// TYPE_UNICODE / TYPE_ASCII: text.
    Str(String),
    Tuple(Vec<ObjectRef>),
    List(Vec<ObjectRef>),
    Dict(Vec<(ObjectRef, ObjectRef)>),
    Set(Vec<ObjectRef>),
    FrozenSet(Vec<ObjectRef>),
    /// TYPE_SLICE (3.14+): start, stop, step.
    Slice(ObjectRef, ObjectRef, ObjectRef),
    Code(Rc<CodeObject>),
}

/// Arbitrary-precision integer. CPython marshals longs as base-2^15 digits;
/// we convert once to a decimal string, which is all the decompiler needs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PycLong {
    pub negative: bool,
    /// Decimal representation without sign, e.g. "12345678901234567890".
    pub decimal: String,
}

impl PycLong {
    /// Convert CPython's marshal long encoding (sign-magnitude, base 2^15
    /// little-endian digits) to decimal.
    pub fn from_digits(negative: bool, digits: &[u16]) -> PycLong {
        // value = sum(digits[i] << (15*i)); do schoolbook base conversion.
        let mut acc: Vec<u8> = vec![0]; // little-endian decimal digits
        for &digit in digits.iter().rev() {
            // acc = acc * 32768 + digit
            let mut carry: u32 = digit as u32;
            for d in acc.iter_mut() {
                let v = (*d as u32) * 32768 + carry;
                *d = (v % 10) as u8;
                carry = v / 10;
            }
            while carry > 0 {
                acc.push((carry % 10) as u8);
                carry /= 10;
            }
        }
        while acc.len() > 1 && *acc.last().unwrap() == 0 {
            acc.pop();
        }
        let decimal = acc.iter().rev().map(|d| (b'0' + d) as char).collect();
        PycLong { negative: negative && decimal != "0", decimal }
    }

    pub fn is_zero(&self) -> bool {
        self.decimal == "0"
    }
}

impl fmt::Display for PycLong {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.negative {
            f.write_str("-")?;
        }
        f.write_str(&self.decimal)?;
        // Python 2 appends an L suffix to longs; handled by the printer
        // which knows the target version.
        Ok(())
    }
}

impl PyObject {
    pub fn is_none(&self) -> bool {
        matches!(self, PyObject::None)
    }

    pub fn is_code(&self) -> bool {
        matches!(self, PyObject::Code(_))
    }

    pub fn as_code(&self) -> Option<&Rc<CodeObject>> {
        match self {
            PyObject::Code(c) => Some(c),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            PyObject::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_bytes(&self) -> Option<&[u8]> {
        match self {
            PyObject::Bytes(b) => Some(b),
            _ => None,
        }
    }

    /// Interpret a string-ish constant as raw bytes regardless of whether it
    /// was marshalled as Str or Bytes.
    pub fn as_raw_bytes(&self) -> Option<&[u8]> {
        match self {
            PyObject::Bytes(b) => Some(b),
            PyObject::Str(s) => Some(s.as_bytes()),
            _ => None,
        }
    }

    pub fn as_int(&self) -> Option<i64> {
        match self {
            PyObject::Int(i) => Some(*i as i64),
            PyObject::Long(l) => l.decimal.parse().ok().map(|v: i64| if l.negative { -v } else { v }),
            PyObject::False => Some(0),
            PyObject::True => Some(1),
            _ => None,
        }
    }

    pub fn as_tuple(&self) -> Option<&[ObjectRef]> {
        match self {
            PyObject::Tuple(v) => Some(v),
            _ => None,
        }
    }

    /// Short type name, useful for error messages and disassembly.
    pub fn type_name(&self) -> &'static str {
        match self {
            PyObject::None => "None",
            PyObject::Ellipsis => "ellipsis",
            PyObject::StopIteration => "StopIteration",
            PyObject::False | PyObject::True => "bool",
            PyObject::Int(_) => "int",
            PyObject::Long(_) => "long",
            PyObject::Float(..) => "float",
            PyObject::Complex(..) => "complex",
            PyObject::Bytes(_) => "bytes",
            PyObject::Str(_) => "str",
            PyObject::Tuple(_) => "tuple",
            PyObject::List(_) => "list",
            PyObject::Dict(_) => "dict",
            PyObject::Set(_) => "set",
            PyObject::FrozenSet(_) => "frozenset",
            PyObject::Slice(..) => "slice",
            PyObject::Code(_) => "code",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn long_from_digits() {
        assert_eq!(PycLong::from_digits(false, &[]).decimal, "0");
        assert_eq!(PycLong::from_digits(false, &[1]).decimal, "1");
        assert_eq!(PycLong::from_digits(true, &[1]).decimal, "1");
        assert!(PycLong::from_digits(true, &[0]).is_zero());
        // 32768 = digit[1]=1
        assert_eq!(PycLong::from_digits(false, &[0, 1]).decimal, "32768");
        // 2^64 = 18446744073709551616 ; digits: 2^64 = 32768^4 * 16 -> [0,0,0,0,16]
        assert_eq!(
            PycLong::from_digits(false, &[0, 0, 0, 0, 16]).decimal,
            "18446744073709551616"
        );
        // -123456789012345678901234567890
        let digits: Vec<u16> = {
            // compute via python-known value: just check roundtrip display
            let mut n: u128 = 123456789012345678901234567890u128;
            let mut d = Vec::new();
            while n > 0 {
                d.push((n & 0x7fff) as u16);
                n >>= 15;
            }
            d
        };
        let l = PycLong::from_digits(true, &digits);
        assert!(l.negative);
        assert_eq!(l.decimal, "123456789012345678901234567890");
    }
}

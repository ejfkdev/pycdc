//! Line number table decoding across the three historical formats:
//!
//! * `lnotab` (Python 1.5 - 3.9): `(byte_delta, line_delta)` pairs; the line
//!   delta is unsigned on Python 2 and signed on Python 3.
//! * 3.10 (PEP 626): same pair format, signed deltas.
//! * 3.11+ (`co_linetable`): per-entry header byte (kind + code-unit count)
//!   followed by varint/svarint payloads. Only line starts are decoded here;
//!   column and end-line information is ignored by the decompiler.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LineTableKind {
    LnotabUnsigned,
    LnotabSigned,
    Pep626,
}

/// Decode a line table into `(byte_offset, line)` pairs, one entry per
/// instruction group where the line number changes.
pub fn decode_line_table(table: &[u8], first_line: u32, kind: LineTableKind) -> Vec<(usize, u32)> {
    match kind {
        LineTableKind::Pep626 => decode_311(table, first_line),
        LineTableKind::LnotabUnsigned => decode_lnotab(table, first_line, false),
        LineTableKind::LnotabSigned => decode_lnotab(table, first_line, true),
    }
}

fn decode_lnotab(table: &[u8], first_line: u32, signed: bool) -> Vec<(usize, u32)> {
    let mut out = Vec::new();
    let mut addr = 0usize;
    let mut line = first_line as i64;
    out.push((addr, line as u32));
    let mut i = 0;
    while i + 1 < table.len() {
        let addr_delta = table[i] as usize;
        let line_delta = if signed {
            table[i + 1] as i8 as i64
        } else {
            table[i + 1] as i64
        };
        i += 2;
        // CPython quirk: a 255 address delta means "add 255 and continue
        // without emitting a new line entry".
        if addr_delta == 255 {
            addr += 255;
            continue;
        }
        addr += addr_delta;
        if line_delta != 0 {
            line += line_delta;
            out.push((addr, line as u32));
        } else if addr_delta != 0 {
            // line unchanged; keep last entry authoritative
            if let Some(last) = out.last_mut() {
                // no new entry needed
                let _ = last;
            }
        }
    }
    out
}

/// Python 3.11+ location table (`co_linetable`).
///
/// Each entry starts with a byte: bit 7 set, bits 3-6 = kind code,
/// bits 0-2 = (code units covered) - 1. Kind codes:
///   0..=9  short form: line unchanged, one column byte follows
///   10..=12 one-line form: line delta = code - 10, two column bytes follow
///   13     no column info: svarint line delta
///   14     long form: svarint line delta, varint end-line delta,
///          varint start/end columns
///   15     no location
/// Integers use 6-bit varints; signed values are zigzag encoded.
fn decode_311(table: &[u8], first_line: u32) -> Vec<(usize, u32)> {
    let mut out = Vec::new();
    let mut addr = 0usize;
    let mut line = first_line as i64;
    let mut i = 0;

    fn read_uvarint(table: &[u8], i: &mut usize) -> Option<u64> {
        let mut value: u64 = 0;
        let mut shift = 0;
        loop {
            let b = *table.get(*i)?;
            *i += 1;
            value |= ((b & 0x3F) as u64) << shift;
            if b & 0x40 == 0 {
                return Some(value);
            }
            shift += 6;
        }
    }

    fn read_svarint(table: &[u8], i: &mut usize) -> Option<i64> {
        let v = read_uvarint(table, i)?;
        let s = (v >> 1) as i64;
        Some(if v & 1 != 0 { -s } else { s })
    }

    while i < table.len() {
        let b0 = table[i];
        i += 1;
        if b0 & 0x80 == 0 {
            break; // malformed
        }
        let code = (b0 >> 3) & 0x0F;
        let units = ((b0 & 0x07) + 1) as usize * 2;
        match code {
            0..=9 => {
                if i < table.len() {
                    i += 1; // column byte
                }
                out.push((addr, line as u32));
            }
            10..=12 => {
                line += code as i64 - 10;
                i += 2; // two column bytes
                out.push((addr, line as u32));
            }
            13 => {
                if let Some(d) = read_svarint(table, &mut i) {
                    line += d;
                    out.push((addr, line as u32));
                } else {
                    break;
                }
            }
            14 => {
                let Some(d) = read_svarint(table, &mut i) else { break };
                let Some(end_delta) = read_uvarint(table, &mut i) else { break };
                let _ = end_delta;
                if read_uvarint(table, &mut i).is_none() {
                    break;
                }
                if read_uvarint(table, &mut i).is_none() {
                    break;
                }
                line += d;
                out.push((addr, line as u32));
            }
            _ => {} // 15: no location
        }
        addr += units;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lnotab_basic() {
        // addr += 4, line += 1 ; addr += 6, line += 2
        let table = [4u8, 1, 6, 2];
        let out = decode_lnotab(&table, 1, true);
        assert_eq!(out, vec![(0, 1), (4, 2), (10, 4)]);
    }

    #[test]
    fn lnotab_unsigned_py2() {
        // py2: line delta 200 stays positive
        let table = [2u8, 200];
        let out = decode_lnotab(&table, 1, false);
        assert_eq!(out, vec![(0, 1), (2, 201)]);
    }

    #[test]
    fn pep626_real_311_vector() {
        // Real co_linetable from CPython 3.11 (`def f(x): if/else/for/return`),
        // expected findlinestarts: (0,1),(2,2),(14,3),(20,5),(24,6),(58,7),(70,8)
        let hex = "8000d80708883182758075d80c0d88018801e00c0d8801dd0d12903289598c59f00001050ff00001050f8801d808098851890688018801d80b0c8048";
        let table: Vec<u8> = (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect();
        let entries = decode_311(&table, 1);
        let mut changes: Vec<(usize, u32)> = Vec::new();
        let mut prev = None;
        for (off, ln) in entries {
            if prev != Some(ln) {
                changes.push((off, ln));
            }
            prev = Some(ln);
        }
        assert_eq!(
            changes,
            vec![(0, 1), (2, 2), (14, 3), (20, 5), (24, 6), (58, 7), (70, 8)]
        );
    }

    #[test]
    fn lnotab_signed_py3() {
        // py3: 200 as i8 = -56
        let table = [2u8, 200];
        let out = decode_lnotab(&table, 100, true);
        assert_eq!(out, vec![(0, 100), (2, 44)]);
    }
}

#[cfg(test)]
mod tests_314 {
    use super::*;

    #[test]
    fn pep626_real_314_vector() {
        let hex = "f003010101d804058001d804058001df0304d808098241f103000405";
        let table: Vec<u8> = (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect();
        let entries = decode_311(&table, 1);
        let mut changes: Vec<(usize, u32)> = Vec::new();
        let mut prev = None;
        for (off, ln) in entries {
            if prev != Some(ln) {
                changes.push((off, ln));
            }
            prev = Some(ln);
        }
        assert_eq!(changes, vec![(0, 0), (2, 1), (6, 2), (10, 3), (26, 4), (34, 3)]);
    }
}

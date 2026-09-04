//! AST -> Python source rendering.
//!
//! One printer for all versions; syntax differences (py2 print statement,
//! `except E, e:`, long literals, annotations, f-strings) are selected from
//! the `PythonVersion` carried in the printer.

use std::fmt::Write as _;

use crate::ast::*;
use crate::bytecode::float_repr;
use crate::object::{ObjectRef, PyObject};
use crate::version::PythonVersion;

/// Operator precedence levels (higher binds tighter).
mod prec {
    pub const YIELD: u8 = 0;
    pub const LAMBDA: u8 = 1;
    pub const TERNARY: u8 = 2;
    pub const OR: u8 = 3;
    pub const AND: u8 = 4;
    pub const NOT: u8 = 5;
    pub const CMP: u8 = 6;
    pub const BOR: u8 = 7;
    pub const BXOR: u8 = 8;
    pub const BAND: u8 = 9;
    pub const SHIFT: u8 = 10;
    pub const ADD: u8 = 11;
    pub const MUL: u8 = 12;
    pub const UNARY: u8 = 13;
    pub const POW: u8 = 14;
    pub const AWAIT: u8 = 15;
    pub const ATOM: u8 = 16;
}

pub fn expr_precedence(e: &Expr) -> u8 {
    use prec::*;
    match e {
        Expr::Yield(_) | Expr::YieldFrom(_) => YIELD,
        Expr::Lambda { .. } => LAMBDA,
        Expr::Ternary { .. } => TERNARY,
        Expr::BoolOp { op, .. } => match op {
            BoolOpKind::Or => OR,
            BoolOpKind::And => AND,
        },
        Expr::Unary { op, .. } => match op {
            UnaryOp::Not => NOT,
            _ => UNARY,
        },
        // bare comma tuples bind looser than anything except lambda bodies
        Expr::Tuple(v) if v.len() != 1 => 1,
        Expr::Compare { .. } => CMP,
        Expr::Binary { op, .. } => match op {
            BinaryOp::BitOr => BOR,
            BinaryOp::BitXor => BXOR,
            BinaryOp::BitAnd => BAND,
            BinaryOp::LShift | BinaryOp::RShift => SHIFT,
            BinaryOp::Add | BinaryOp::Sub => ADD,
            BinaryOp::Mult | BinaryOp::Div | BinaryOp::FloorDiv | BinaryOp::Mod
            | BinaryOp::MatMult => MUL,
            BinaryOp::Pow => POW,
        },
        Expr::Await(_) => AWAIT,
        // Named always renders parenthesized — ATOM keeps outer parens off
        Expr::Named { .. } => ATOM,
        _ => ATOM,
    }
}

pub struct Printer {
    out: String,
    indent: usize,
    version: PythonVersion,
    at_line_start: bool,
    /// inside a lambda body: suppress statement rendering quirks
    in_lambda: bool,
    /// nested f-string depth: alternate quote characters (pre-3.12 cannot
    /// reuse the outer quote inside an f-string)
    fstring_depth: usize,
    /// quote characters of the enclosing f-strings (innermost last)
    fstring_quotes: Vec<char>,
    /// inside a loop body: break/continue are only legal when > 0
    loop_depth: usize,
}

pub fn generate(body: &[Stmt], version: PythonVersion, clean: bool) -> String {
    let mut p = Printer {
        out: String::new(),
        indent: 0,
        version,
        at_line_start: true,
        in_lambda: false,
        fstring_depth: 0,
        fstring_quotes: Vec::new(),
        loop_depth: 0,
    };
    p.module(body);
    if !clean {
        p.write_line("# WARNING: Decompyle incomplete");
    }
    // py2 refuses non-ASCII source without a PEP 263 coding declaration
    if version.major < 3 && !p.out.is_ascii() {
        return format!("# -*- coding: utf-8 -*-\n{}", p.out);
    }
    p.out
}

impl Printer {
    fn write(&mut self, s: &str) {
        if self.at_line_start && !s.is_empty() {
            for _ in 0..self.indent {
                self.out.push_str("    ");
            }
            self.at_line_start = false;
        }
        self.out.push_str(s);
    }

    fn newline(&mut self) {
        self.out.push('\n');
        self.at_line_start = true;
    }

    fn write_line(&mut self, s: &str) {
        self.write(s);
        self.newline();
    }

    fn module(&mut self, body: &[Stmt]) {
        // module docstring
        let mut start = 0;
        if let Some(Stmt::Expr(e)) = body.first() {
            if let Expr::Const(o) = &**e {
                if matches!(&**o, PyObject::Str(_) | PyObject::Bytes(_)) {
                    let s = const_str_content(o);
                    self.write_str_literal(&s, true);
                    self.newline();
                    self.newline();
                    start = 1;
                }
            }
        }
        for (i, stmt) in body.iter().enumerate().skip(start) {
            if i > start && needs_blank_line(stmt, body.get(i - 1)) {
                if !self.out.ends_with("\n\n") {
                    self.newline();
                }
            }
            self.stmt(stmt);
        }
    }

    fn block(&mut self, stmts: &[Stmt]) {
        self.indent += 1;
        if stmts.is_empty() {
            self.write_line("pass");
        } else {
            let before = self.out.len();
            for s in stmts {
                self.stmt(s);
            }
            // a block whose statements all collapsed into comments (e.g.
            // break/continue outside any loop) still needs a real statement
            let produced = self.out[before..]
                .lines()
                .any(|l| !l.trim().is_empty() && !l.trim_start().starts_with('#'));
            if !produced {
                self.write_line("pass");
            }
        }
        self.indent -= 1;
    }

    fn stmt(&mut self, s: &Stmt) {
        match s {
            Stmt::Expr(e) => {
                self.expr(e, 0);
                self.newline();
            }
            Stmt::Assign { targets, value } => {
                for t in targets {
                    self.expr(t, 0);
                    self.write(" = ");
                }
                // `a, b = 0, 1` — const tuple RHS of a tuple unpack
                if targets.len() == 1 {
                    if let (Expr::Tuple(_), Expr::Const(o)) = (&*targets[0], &**value) {
                        if let PyObject::Tuple(items) = &**o {
                            for (i, it) in items.iter().enumerate() {
                                if i > 0 {
                                    self.write(", ");
                                }
                                self.const_expr(it);
                            }
                            self.newline();
                            return;
                        }
                    }
                }
                self.expr(value, 0);
                self.newline();
            }
            Stmt::AugAssign { target, op, value } => {
                self.expr(target, prec::ATOM);
                self.write(&format!(" {}= ", binop_text(op)));
                self.expr(value, 0);
                self.newline();
            }
            Stmt::AnnAssign {
                target,
                annotation,
                value,
            } => {
                self.expr(target, prec::ATOM);
                self.write(": ");
                self.expr(annotation, 0);
                if let Some(v) = value {
                    self.write(" = ");
                    self.expr(v, 0);
                }
                self.newline();
            }
            Stmt::Print {
                dest,
                values,
                newline,
            } => {
                self.write("print");
                if let Some(d) = dest {
                    self.write(" >>");
                    self.expr(d, 0);
                    if !values.is_empty() {
                        self.write(",");
                    }
                }
                for (i, v) in values.iter().enumerate() {
                    if i > 0 || dest.is_some() {
                        self.write(" ");
                    } else {
                        self.write(" ");
                    }
                    self.expr(v, 0);
                    if i + 1 < values.len() {
                        self.write(",");
                    }
                }
                if !newline {
                    self.write(",");
                }
                self.newline();
            }
            Stmt::Exec {
                code,
                globals,
                locals,
            } => {
                self.write("exec ");
                self.expr(code, 0);
                if let Some(g) = globals {
                    self.write(" in ");
                    self.expr(g, 0);
                    if let Some(l) = locals {
                        self.write(", ");
                        self.expr(l, 0);
                    }
                }
                self.newline();
            }
            Stmt::Return(None) => self.write_line("return"),
            Stmt::Return(Some(e)) => {
                self.write("return ");
                self.expr(e, 0);
                self.newline();
            }
            Stmt::Delete(targets) => {
                self.write("del ");
                for (i, t) in targets.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.expr(t, prec::ATOM);
                }
                self.newline();
            }
            Stmt::Pass => self.write_line("pass"),
            Stmt::Break | Stmt::Continue => {
                let kw = if matches!(s, Stmt::Break) { "break" } else { "continue" };
                if self.loop_depth == 0 {
                    // structural recovery failed somewhere upstream; emit a
                    // comment so the output still compiles
                    self.write_line(&format!("# WARNING: {kw} outside loop (unrecovered structure)"));
                } else {
                    self.write_line(kw);
                }
            }
            Stmt::Import { names } => {
                self.write("import ");
                for (i, (m, a)) in names.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.write(m);
                    if let Some(a) = a {
                        self.write(&format!(" as {a}"));
                    }
                }
                self.newline();
            }
            Stmt::ImportFrom {
                module,
                level,
                names,
            } => {
                self.write(&format!("from {}{}", ".".repeat(*level as usize), module));
                self.write(" import ");
                if names.len() == 1 && names[0].0 == "*" {
                    self.write("*");
                } else {
                    let paren = names.len() > 2;
                    if paren {
                        self.write("(");
                    }
                    for (i, (n, a)) in names.iter().enumerate() {
                        if i > 0 {
                            self.write(", ");
                        }
                        self.write(n);
                        if let Some(a) = a {
                            self.write(&format!(" as {a}"));
                        }
                    }
                    if paren {
                        self.write(")");
                    }
                }
                self.newline();
            }
            Stmt::Global(names) => {
                self.write_line(&format!("global {}", names.join(", ")));
            }
            Stmt::Nonlocal(names) => {
                self.write_line(&format!("nonlocal {}", names.join(", ")));
            }
            Stmt::If { cond, body, orelse } => {
                self.write("if ");
                self.expr(cond, 0);
                self.write(":");
                self.newline();
                self.block(body);
                self.print_elif_chain(orelse);
            }
            Stmt::While { cond, body, orelse } => {
                self.write("while ");
                self.expr(cond, 0);
                self.write(":");
                self.newline();
                self.loop_depth += 1;
                self.block(body);
                self.loop_depth -= 1;
                if !orelse.is_empty() {
                    self.write_line("else:");
                    self.block(orelse);
                }
            }
            Stmt::For {
                target,
                iter,
                body,
                orelse,
                is_async,
            } => {
                if *is_async {
                    self.write("async ");
                }
                self.write("for ");
                self.expr(target, 0);
                self.write(" in ");
                self.expr(iter, 0);
                self.write(":");
                self.newline();
                self.loop_depth += 1;
                self.block(body);
                self.loop_depth -= 1;
                if !orelse.is_empty() {
                    self.write_line("else:");
                    self.block(orelse);
                }
            }
            Stmt::Try {
                body,
                handlers,
                orelse,
                finalbody,
            } => {
                // a bare `except:` must be last (and unique); drop extras
                let mut handlers = handlers.clone();
                handlers.sort_by_key(|h| if h.type_.is_none() { 1 } else { 0 });
                let bare_pos = handlers.iter().position(|h| h.type_.is_none());
                if let Some(bp) = bare_pos {
                    handlers.truncate(bp + 1);
                }
                if handlers.is_empty() && finalbody.is_empty() {
                    // A try without except/finally is invalid Python — the
                    // structure was only partially recovered; keep the body
                    // statements AT THE CURRENT INDENT so the output stays
                    // compilable.
                    self.write_line("# WARNING: unrecovered try/except structure");
                    for s in body.iter().chain(orelse.iter()) {
                        self.stmt(s);
                    }
                    return;
                }
                self.write_line("try:");
                self.block(body);
                for h in &handlers {
                    self.write("except");
                    if let Some(t) = &h.type_ {
                        self.write(" ");
                        self.expr(t, prec::OR);
                        if let Some(n) = &h.name {
                            if self.version.major >= 3 {
                                self.write(" as ");
                            } else {
                                self.write(", ");
                            }
                            self.expr(n, prec::ATOM);
                        }
                    }
                    self.write(":");
                    self.newline();
                    self.block(&h.body);
                }
                if !orelse.is_empty() {
                    self.write_line("else:");
                    self.block(orelse);
                }
                if !finalbody.is_empty() {
                    self.write_line("finally:");
                    self.block(finalbody);
                }
            }
            Stmt::With {
                items,
                body,
                is_async,
            } => {
                if *is_async {
                    self.write("async ");
                }
                self.write("with ");
                for (i, item) in items.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.expr(&item.ctx, 0);
                    if let Some(t) = &item.target {
                        self.write(" as ");
                        self.expr(t, prec::ATOM);
                    }
                }
                self.write(":");
                self.newline();
                self.block(body);
            }
            Stmt::Raise { exc, cause } => {
                match exc {
                    None => self.write("raise"),
                    Some(e) => {
                        self.write("raise ");
                        self.expr(e, 0);
                        if let Some(c) = cause {
                            if self.version.major >= 3 {
                                self.write(" from ");
                                self.expr(c, 0);
                            } else {
                                self.write(" # WARNING: raise cause dropped (py2)");
                            }
                        }
                    }
                }
                self.newline();
            }
            Stmt::Assert { test, msg } => {
                self.write("assert ");
                self.expr(test, 0);
                if let Some(m) = msg {
                    self.write(", ");
                    self.expr(m, 0);
                }
                self.newline();
            }
            Stmt::FuncDef(fdef, body) => {
                for d in &fdef.decorators {
                    self.write("@");
                    self.expr(d, 0);
                    self.newline();
                }
                if fdef.is_async {
                    self.write("async ");
                }
                self.write(&format!("def {}(", fdef.name));
                self.parameters(&fdef.params);
                self.write(")");
                let ret = fdef
                    .returns
                    .as_ref()
                    .or(fdef.params.returns_annotation.as_ref());
                if let Some(r) = ret {
                    self.write(" -> ");
                    self.expr(r, 0);
                }
                self.write(":");
                self.newline();
                self.func_body(body);
                self.newline();
            }
            Stmt::ClassDef {
                name,
                bases,
                keywords,
                star_args,
                star_kwargs,
                decorators,
                body,
            } => {
                for d in decorators {
                    self.write("@");
                    self.expr(d, 0);
                    self.newline();
                }
                self.write(&format!("class {name}"));
                let has_args = !bases.is_empty()
                    || !keywords.is_empty()
                    || star_args.is_some()
                    || star_kwargs.is_some();
                if has_args {
                    self.write("(");
                    let mut first = true;
                    for b in bases {
                        if !first {
                            self.write(", ");
                        }
                        first = false;
                        self.expr(b, 0);
                    }
                    if let Some(sa) = star_args {
                        if !first {
                            self.write(", ");
                        }
                        first = false;
                        self.write("*");
                        self.expr(sa, prec::ATOM);
                    }
                    for (k, v) in keywords {
                        if !first {
                            self.write(", ");
                        }
                        first = false;
                        if let Some(kn) = k {
                            self.write(&format!("{kn}="));
                        }
                        self.expr(v, 0);
                    }
                    if let Some(sk) = star_kwargs {
                        if !first {
                            self.write(", ");
                        }
                        self.write("**");
                        self.expr(sk, prec::ATOM);
                    }
                    self.write(")");
                }
                self.write(":");
                self.newline();
                self.func_body(body);
                self.newline();
            }
            Stmt::Unimplemented(text) => {
                self.write_line(text);
            }
        }
    }

    fn print_elif_chain(&mut self, orelse: &[Stmt]) {
        if orelse.is_empty() {
            return;
        }
        if orelse.len() == 1 {
            if let Stmt::If { cond, body, orelse } = &orelse[0] {
                self.write("elif ");
                self.expr(cond, 0);
                self.write(":");
                self.newline();
                self.block(body);
                self.print_elif_chain(orelse);
                return;
            }
        }
        self.write_line("else:");
        self.block(orelse);
    }

    /// Body of a def/class: docstring first, then statements.
    fn func_body(&mut self, body: &[Stmt]) {
        self.indent += 1;
        let mut start = 0;
        if let Some(Stmt::Expr(e)) = body.first() {
            if let Expr::Const(o) = &**e {
                if matches!(&**o, PyObject::Str(_) | PyObject::Bytes(_)) {
                    let s = const_str_content(o);
                    self.write_str_literal(&s, true);
                    self.newline();
                    start = 1;
                    if body.len() == 1 {
                        self.indent -= 1;
                        return;
                    }
                    self.newline();
                }
            }
        }
        if start >= body.len() && start == 0 {
            self.write_line("pass");
        }
        for s in &body[start..] {
            self.stmt(s);
        }
        self.indent -= 1;
    }

    fn parameters(&mut self, p: &Parameters) {
        let mut first = true;
        // clamp: defaults must never exceed the positional arg count
        let ndef = p.defaults.len().min(p.args.len());
        let nargs = p.args.len();
        for (i, a) in p.args.iter().enumerate() {
            if !first {
                self.write(", ");
            }
            first = false;
            self.write(&a.name);
            if let Some(ann) = &a.annotation {
                self.write(": ");
                self.expr(ann, 0);
            }
            if i >= nargs - ndef {
                let d = &p.defaults[i - (nargs - ndef)];
                if a.annotation.is_some() || self.version.major >= 3 {
                    self.write("=");
                } else {
                    self.write("=");
                }
                self.expr(d, 0);
            }
            if p.posonly_count > 0 && i + 1 == p.posonly_count {
                self.write(", /");
            }
        }
        if let Some(v) = &p.vararg {
            if !first {
                self.write(", ");
            }
            first = false;
            self.write(&format!("*{}", v.name));
            if let Some(ann) = &v.annotation {
                self.write(": ");
                self.expr(ann, 0);
            }
        } else if !p.kwonly.is_empty() {
            if !first {
                self.write(", ");
            }
            first = false;
            self.write("*");
        }
        for (i, k) in p.kwonly.iter().enumerate() {
            if !first {
                self.write(", ");
            }
            first = false;
            self.write(&k.name);
            if let Some(ann) = &k.annotation {
                self.write(": ");
                self.expr(ann, 0);
            }
            if let Some(Some(d)) = p.kw_defaults.get(i) {
                self.write("=");
                self.expr(d, 0);
            }
        }
        if let Some(k) = &p.kwarg {
            if !first {
                self.write(", ");
            }
            self.write(&format!("**{}", k.name));
            if let Some(ann) = &k.annotation {
                self.write(": ");
                self.expr(ann, 0);
            }
        }
    }

    /// Render an expression, parenthesizing when below `min_prec`.
    fn expr(&mut self, e: &ExprRef, min_prec: u8) {
        let p = expr_precedence(e);
        if p < min_prec {
            self.write("(");
            self.expr_inner(e);
            self.write(")");
        } else {
            self.expr_inner(e);
        }
    }

    fn expr_inner(&mut self, e: &ExprRef) {
        match &**e {
            Expr::Const(o) => self.const_expr(o),
            Expr::Name(n) => self.write(n),
            Expr::Attribute { value, attr } => {
                // `0.attr` parses as a float literal — parenthesize numeric
                // constant receivers
                let needs_paren = matches!(&**value, Expr::Const(o)
                    if matches!(&**o, crate::object::PyObject::Int(_)));
                if needs_paren {
                    self.write("(");
                    self.expr(value, prec::ATOM);
                    self.write(")");
                } else {
                    self.expr(value, prec::ATOM);
                }
                self.write(&format!(".{attr}"));
            }
            Expr::Subscript { value, index } => {
                self.expr(value, prec::ATOM);
                self.write("[");
                self.expr(index, 0);
                self.write("]");
            }
            Expr::Slice(s) => {
                if let Some(a) = &s.start {
                    self.expr(a, 0);
                }
                self.write(":");
                if let Some(b) = &s.stop {
                    self.expr(b, 0);
                }
                if let Some(c) = &s.step {
                    self.write(":");
                    self.expr(c, 0);
                }
            }
            Expr::Unary { op, operand } => {
                let t = match op {
                    UnaryOp::Neg => "-",
                    UnaryOp::Pos => "+",
                    UnaryOp::Invert => "~",
                    UnaryOp::Not => {
                        self.write("not ");
                        self.expr(operand, prec::NOT);
                        return;
                    }
                };
                self.write(t);
                self.expr(operand, prec::UNARY);
            }
            Expr::Binary { op, left, right } => {
                let p = expr_precedence(e);
                self.expr(left, p);
                self.write(&format!(" {} ", binop_text(op)));
                // right operand of ** binds tighter (right associative)
                let rp = if *op == BinaryOp::Pow { p } else { p + 1 };
                self.expr(right, rp);
            }
            Expr::Compare { operands, ops } => {
                for (i, o) in operands.iter().enumerate() {
                    if i > 0 {
                        self.write(&format!(" {} ", cmpop_text(&ops[i - 1])));
                    }
                    self.expr(o, prec::CMP + 1);
                }
            }
            Expr::BoolOp { op, values } => {
                let p = expr_precedence(e);
                let sep = match op {
                    BoolOpKind::And => " and ",
                    BoolOpKind::Or => " or ",
                };
                for (i, v) in values.iter().enumerate() {
                    if i > 0 {
                        self.write(sep);
                    }
                    self.expr(v, p + 1);
                }
            }
            Expr::Call {
                func,
                args,
                keywords,
                star_args,
                star_kwargs,
            } => {
                self.expr(func, prec::ATOM);
                self.write("(");
                let mut first = true;
                for a in args {
                    if !first {
                        self.write(", ");
                    }
                    first = false;
                    self.expr(a, prec::TERNARY);
                }
                if let Some(sa) = star_args {
                    if !is_empty_tuple(sa) {
                        if !first {
                            self.write(", ");
                        }
                        first = false;
                        self.write("*");
                        self.expr(sa, prec::ATOM);
                    }
                }
                for (k, v) in keywords {
                    if !first {
                        self.write(", ");
                    }
                    first = false;
                    if let Some(kn) = k {
                        self.write(&format!("{kn}="));
                    }
                    self.expr(v, prec::TERNARY);
                }
                if let Some(sk) = star_kwargs {
                    if !is_empty_tuple(sk) {
                        if !first {
                            self.write(", ");
                        }
                        self.write("**");
                        self.expr(sk, prec::ATOM);
                    }
                }
                self.write(")");
            }
            Expr::Tuple(items) => {
                if items.is_empty() {
                    self.write("()");
                } else if items.len() == 1 {
                    self.write("(");
                    self.expr(&items[0], 0);
                    self.write(",)");
                } else {
                    let mut first = true;
                    for it in items {
                        if !first {
                            self.write(", ");
                        }
                        first = false;
                        // nested tuples/lambdas need parens inside a tuple
                        self.expr(it, 2);
                    }
                }
            }
            Expr::List(items) => {
                self.write("[");
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.expr(it, prec::TERNARY);
                }
                self.write("]");
            }
            Expr::Set(items) => {
                self.write("{");
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.expr(it, prec::TERNARY);
                }
                self.write("}");
            }
            Expr::Dict(entries) => {
                self.write("{");
                for (i, (k, v)) in entries.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    if let Expr::Starred(inner) = &**k {
                        self.write("**");
                        self.expr(inner, 0);
                        continue;
                    }
                    self.expr(k, prec::TERNARY);
                    self.write(": ");
                    self.expr(v, prec::TERNARY);
                }
                self.write("}");
            }
            Expr::Starred(inner) => {
                self.write("*");
                self.expr(inner, prec::ATOM);
            }
            Expr::Comprehension {
                kind,
                elt,
                key,
                generators,
            } => {
                let (open, close) = match kind {
                    CompKind::List => ("[", "]"),
                    _ => ("{", "}"),
                };
                if matches!(kind, CompKind::Generator) {
                    self.write("(");
                } else {
                    self.write(open);
                }
                if let Some(k) = key {
                    self.expr(k, 2);
                    self.write(": ");
                }
                // bare tuple elements need parens: `[(x, y) for ...]`
                self.expr(elt, 2);
                for g in generators {
                    if g.is_async {
                        self.write(" async for ");
                    } else {
                        self.write(" for ");
                    }
                    self.expr(&g.target, 0);
                    self.write(" in ");
                    self.expr(&g.iter, prec::OR);
                    for cond in &g.ifs {
                        self.write(" if ");
                        self.expr(cond, prec::OR);
                    }
                }
                if matches!(kind, CompKind::Generator) {
                    self.write(")");
                } else {
                    self.write(close);
                }
            }
            Expr::Lambda { params, body } => {
                let old = self.in_lambda;
                self.in_lambda = true;
                self.write("lambda");
                if !params.is_empty() {
                    self.write(" ");
                }
                self.parameters(params);
                self.write(": ");
                // yield bodies need parens inside a lambda
                self.expr(body, 1);
                self.in_lambda = old;
            }
            Expr::Function(fd) => {
                // a function object used as a value outside a def binding
                self.write(&format!("/* <function {}> */None", fd.name));
            }
            Expr::Ternary {
                cond,
                then_expr,
                else_expr,
            } => {
                self.expr(then_expr, prec::TERNARY + 1);
                self.write(" if ");
                self.expr(cond, prec::TERNARY + 1);
                self.write(" else ");
                self.expr(else_expr, prec::TERNARY);
            }
            Expr::Await(inner) => {
                self.write("await ");
                self.expr(inner, prec::AWAIT);
            }
            Expr::Named { target, value } => {
                self.write("(");
                self.expr(target, 0);
                self.write(" := ");
                self.expr(value, 0);
                self.write(")");
            }
            Expr::Yield(None) => self.write("yield"),
            Expr::Yield(Some(v)) => {
                self.write("yield ");
                self.expr(v, prec::ATOM);
            }
            Expr::YieldFrom(v) => {
                self.write("yield from ");
                self.expr(v, prec::ATOM);
            }
            Expr::FString(fs) => self.fstring(fs),
            Expr::Backquote(inner) => {
                if self.version.major >= 3 {
                    self.write("repr(");
                    self.expr(inner, 0);
                    self.write(")");
                } else {
                    self.write("`");
                    self.expr(inner, 0);
                    self.write("`");
                }
            }
        }
    }

    fn fstring(&mut self, fs: &FString) {
        // pick a quote that appears in NO literal of the whole f-string tree
        // (pre-3.12 forbids reusing the outer quote anywhere inside) and
        // differs from every enclosing f-string's quote
        let mut text = String::new();
        collect_fstring_literals(fs, &mut text);
        let quote = if self.version.at_least(3, 12) {
            if !text.contains('\'') {
                '\''
            } else if !text.contains('"') {
                '"'
            } else {
                '\''
            }
        } else {
            // embedded string constants (pre-3.12) cannot escape quotes and
            // cannot reuse the outer quote: each forces the outer choice
            let mut consts = Vec::new();
            for p in &fs.parts {
                if let FStringPart::Value { value, .. } = p {
                    collect_expr_strings(value, &mut consts);
                }
            }
            let mut ok_single = !self.fstring_quotes.contains(&'\'');
            let mut ok_double = !self.fstring_quotes.contains(&'"');
            let mut impossible = false;
            for c in &consts {
                let (hs, hd) = (c.contains('\''), c.contains('"'));
                match (hs, hd) {
                    (true, true) => impossible = true,
                    // inner must use the other quote -> outer is forced
                    (true, false) => ok_double = false,
                    (false, true) => ok_single = false,
                    (false, false) => {}
                }
            }
            if impossible || (!ok_single && !ok_double) {
                // unrenderable as an f-string: fall back to concatenation
                self.fstring_concat(fs);
                return;
            }
            match (ok_single, ok_double) {
                (true, _) => '\'',
                (_, true) => '"',
                _ => '\'',
            }
        };
        self.fstring_quotes.push(quote);
        self.write(&format!("f{quote}"));
        for part in &fs.parts {
            match part {
                FStringPart::Literal(s) => {
                    for ch in s.chars() {
                        match ch {
                            '{' => self.write("{{"),
                            '}' => self.write("}}"),
                            '\n' => self.write("\\n"),
                            '\t' => self.write("\\t"),
                            '\r' => self.write("\\r"),
                            '\\' => self.write("\\\\"),
                            c if c == quote => {
                                self.write("\\");
                                self.write(&c.to_string());
                            }
                            c => self.write(&c.to_string()),
                        }
                    }
                }
                FStringPart::Value {
                    value,
                    conversion,
                    format_spec,
                } => {
                    self.write("{");
                    self.fstring_depth += 1;
                    self.expr(value, prec::YIELD + 1);
                    self.fstring_depth -= 1;
                    if let Some(c) = conversion {
                        self.write(&format!("!{c}"));
                    }
                    if let Some(spec) = format_spec {
                        self.write(":");
                        for p in &spec.parts {
                            match p {
                                FStringPart::Literal(s) => self.write(s),
                                FStringPart::Value {
                                    value: v,
                                    conversion: c2,
                                    format_spec: fs2,
                                } => {
                                    self.write("{");
                                    self.fstring_depth += 1;
                                    self.expr(v, 0);
                                    self.fstring_depth -= 1;
                                    if let Some(c) = c2 {
                                        self.write(&format!("!{c}"));
                                    }
                                    let _ = fs2;
                                    self.write("}");
                                }
                            }
                        }
                    }
                    self.write("}");
                }
            }
        }
        self.write(&quote.to_string());
        self.fstring_quotes.pop();
    }

    /// Render an f-string that cannot be quoted legally (pre-3.12 with
    /// embedded constants needing both quote characters) as a concatenation.
    fn fstring_concat(&mut self, fs: &FString) {
        self.write("(");
        let mut first = true;
        for part in &fs.parts {
            match part {
                FStringPart::Literal(s) => {
                    if s.is_empty() {
                        continue;
                    }
                    if !first {
                        self.write(" + ");
                    }
                    first = false;
                    self.write_str_literal(s, false);
                }
                FStringPart::Value { value, conversion, format_spec } => {
                    if !first {
                        self.write(" + ");
                    }
                    first = false;
                    match format_spec {
                        Some(spec) => {
                            let mut spec_text = String::new();
                            for p in &spec.parts {
                                match p {
                                    FStringPart::Literal(t) => spec_text.push_str(t),
                                    FStringPart::Value { .. } => {}
                                }
                            }
                            self.write("format(");
                            self.expr(value, 0);
                            self.write(", ");
                            self.write_str_literal(&spec_text, false);
                            self.write(")");
                        }
                        None => {
                            let f = match conversion {
                                Some('r') => "repr",
                                Some('a') => "ascii",
                                _ => "str",
                            };
                            self.write(&format!("{f}("));
                            self.expr(value, 0);
                            self.write(")");
                        }
                    }
                }
            }
        }
        self.write(")");
    }

    fn const_expr(&mut self, o: &ObjectRef) {
        match &**o {
            PyObject::None => self.write("None"),
            PyObject::True => self.write("True"),
            PyObject::False => self.write("False"),
            PyObject::Ellipsis => self.write("..."),
            PyObject::StopIteration => self.write("StopIteration"),
            PyObject::Int(i) => self.write(&i.to_string()),
            PyObject::Long(l) => {
                if self.version.major == 2 && !l.is_zero() {
                    let text = if l.negative {
                        format!("-{}L", l.decimal)
                    } else {
                        format!("{}L", l.decimal)
                    };
                    self.write(&text);
                } else {
                    let text = if l.negative {
                        format!("-{}", l.decimal)
                    } else {
                        l.decimal.clone()
                    };
                    self.write(&text);
                }
            }
            PyObject::Float(_, Some(s)) => self.write(s),
            PyObject::Float(f, None) => self.write(&float_repr(*f)),
            PyObject::Complex(re, im) => {
                self.write("(");
                self.write(&float_repr(*re));
                if *im >= 0.0 {
                    self.write("+");
                    self.write(&float_repr(*im));
                } else {
                    self.write("-");
                    self.write(&float_repr(-*im));
                }
                self.write("j)");
            }
            PyObject::Str(s) => {
                if self.version.major == 2 {
                    let all_ascii = s.is_ascii();
                    if !all_ascii {
                        self.write("u");
                    }
                }
                self.write_str_literal(s, false);
            }
            PyObject::Bytes(b) => {
                if self.version.major >= 3 {
                    self.write("b");
                }
                self.write_raw_bytes_literal(b);
            }
            PyObject::Tuple(items) => {
                if items.len() == 1 {
                    self.write("(");
                    if let Some(i0) = items.first() {
                        self.const_expr(i0);
                    }
                    self.write(",)");
                } else {
                    self.write("(");
                    for (i, it) in items.iter().enumerate() {
                        if i > 0 {
                            self.write(", ");
                        }
                        self.const_expr(it);
                    }
                    self.write(")");
                }
            }
            PyObject::List(items) => {
                self.write("[");
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.const_expr(it);
                }
                self.write("]");
            }
            PyObject::Set(items) => {
                self.write("{");
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.const_expr(it);
                }
                self.write("}");
            }
            PyObject::FrozenSet(items) => {
                self.write("frozenset({");
                for (i, it) in items.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.const_expr(it);
                }
                self.write("})");
            }
            PyObject::Dict(entries) => {
                self.write("{");
                for (i, (k, v)) in entries.iter().enumerate() {
                    if i > 0 {
                        self.write(", ");
                    }
                    self.const_expr(k);
                    self.write(": ");
                    self.const_expr(v);
                }
                self.write("}");
            }
            PyObject::Slice(a, b, c) => {
                self.write("slice(");
                self.const_expr(a);
                self.write(", ");
                self.const_expr(b);
                self.write(", ");
                self.const_expr(c);
                self.write(")");
            }
            PyObject::Code(c) => {
                let _ = self;
                write!(self.out, "/* code {} */None", c.name).ok();
            }
        }
    }

    fn write_str_literal(&mut self, s: &str, docstring: bool) {
        let mut quote = choose_quote(s);
        if !docstring && self.fstring_depth > 0 && !self.version.at_least(3, 12) {
            // pre-3.12 f-strings forbid backslashes and reusing an enclosing
            // quote: switch to an alternate quote when possible
            let bad = |q: &str| q.contains(|c| self.fstring_quotes.contains(&c));
            if bad(quote) {
                let alt = if quote == "'" { "\"" } else { "'" };
                if !bad(alt) && !s.contains(alt.chars().next().unwrap()) {
                    quote = alt;
                }
            }
        }
        if docstring {
            let q3 = quote.to_string().repeat(3);
            self.write(&q3);
            // escape backslashes so \uXXXX etc. in the original text survive;
            // keep real newlines as-is
            let mut body = String::new();
            for ch in s.chars() {
                if ch == '\\' {
                    body.push_str("\\\\");
                } else if quote.starts_with(ch) && (s.ends_with(quote) || s.contains(&q3)) {
                    body.push('\\');
                    body.push(ch);
                } else {
                    body.push(ch);
                }
            }
            self.write(&body);
            self.write(&q3);
            return;
        }
        self.write(quote);
        for ch in s.chars() {
            match ch {
                '\n' => self.write("\\n"),
                '\r' => self.write("\\r"),
                '\t' => self.write("\\t"),
                '\\' => self.write("\\\\"),
                c if quote.starts_with(c) => {
                    self.write("\\");
                    self.write(&c.to_string());
                }
                c if (c as u32) < 0x20 || c as u32 == 0x7f => {
                    let _ = write!(self.out, "\\x{:02x}", c as u32);
                }
                c => {
                    let _ = write!(self.out, "{c}");
                }
            }
        }
        self.write(quote);
    }

    /// Render raw bytes with proper \xNN escapes (never lossy).
    fn write_raw_bytes_literal(&mut self, b: &[u8]) {
        // choose quote minimizing escapes
        let sq = b.iter().filter(|&&x| x == b'\'').count();
        let dq = b.iter().filter(|&&x| x == b'"').count();
        let quote = if sq <= dq { "\u{27}" } else { "\"" };
        let qch = quote.chars().next().unwrap();
        self.write(quote);
        for &byte in b {
            match byte {
                b'\n' => self.write("\\n"),
                b'\r' => self.write("\\r"),
                b'\t' => self.write("\\t"),
                b'\\' => self.write("\\\\"),
                x if x == qch as u8 => {
                    self.write("\\");
                    self.write(&qch.to_string());
                }
                x if x.is_ascii_graphic() || x == b' ' => self.out.push(x as char),
                x => {
                    let _ = write!(self.out, "\\x{x:02x}");
                }
            }
        }
        self.write(quote);
    }

    #[allow(dead_code)]
    fn write_bytes_literal(&mut self, s: &str) {
        let quote = choose_quote(s);
        self.write(quote);
        for ch in s.chars() {
            match ch {
                '\n' => self.write("\\n"),
                '\r' => self.write("\\r"),
                '\t' => self.write("\\t"),
                '\\' => self.write("\\\\"),
                c if quote.starts_with(c) => {
                    self.write("\\");
                    self.write(&c.to_string());
                }
                c if c.is_ascii() && ((c as u32) < 0x20 || c as u32 == 0x7f) => {
                    let _ = write!(self.out, "\\x{:02x}", c as u32);
                }
                c => {
                    // non-ascii bytes come through lossy conversion; emit \x
                    let mut buf = [0u8; 4];
                    let enc = c.encode_utf8(&mut buf);
                    for b in enc.bytes() {
                        if b.is_ascii_graphic() || b == b' ' {
                            self.out.push(b as char);
                        } else {
                            let _ = write!(self.out, "\\x{b:02x}");
                        }
                    }
                }
            }
        }
        self.write(quote);
    }
}

fn const_str_content(o: &ObjectRef) -> String {
    match &**o {
        PyObject::Str(s) => s.clone(),
        PyObject::Bytes(b) => String::from_utf8_lossy(b).into_owned(),
        _ => String::new(),
    }
}

fn choose_quote(s: &str) -> &'static str {
    let has_single = s.contains('\'');
    let has_double = s.contains('"');
    match (has_single, has_double) {
        (false, _) => "'",
        (true, false) => "\"",
        (true, true) => "'",
    }
}

pub fn binop_text(op: &BinaryOp) -> &'static str {
    match op {
        BinaryOp::Add => "+",
        BinaryOp::Sub => "-",
        BinaryOp::Mult => "*",
        BinaryOp::Div => "/",
        BinaryOp::FloorDiv => "//",
        BinaryOp::Mod => "%",
        BinaryOp::Pow => "**",
        BinaryOp::LShift => "<<",
        BinaryOp::RShift => ">>",
        BinaryOp::BitOr => "|",
        BinaryOp::BitXor => "^",
        BinaryOp::BitAnd => "&",
        BinaryOp::MatMult => "@",
    }
}

pub fn cmpop_text(op: &CmpOp) -> &'static str {
    match op {
        CmpOp::Lt => "<",
        CmpOp::LtE => "<=",
        CmpOp::Eq => "==",
        CmpOp::NotEq => "!=",
        CmpOp::Gt => ">",
        CmpOp::GtE => ">=",
        CmpOp::In => "in",
        CmpOp::NotIn => "not in",
        CmpOp::Is => "is",
        CmpOp::IsNot => "is not",
        CmpOp::ExceptionMatch => "==",
    }
}

fn collect_fstring_literals(fs: &FString, out: &mut String) {
    for p in &fs.parts {
        match p {
            FStringPart::Literal(s) => out.push_str(s),
            FStringPart::Value { format_spec, .. } => {
                if let Some(spec) = format_spec {
                    collect_fstring_literals(spec, out);
                }
            }
        }
    }
}

/// Collect the raw contents of every string constant embedded in `e`
/// (these must be quotable inside the f-string pre-3.12).
fn collect_expr_strings(e: &ExprRef, out: &mut Vec<String>) {
    match &**e {
        Expr::Const(o) => match &**o {
            PyObject::Str(s) => out.push(s.clone()),
            PyObject::Tuple(items) | PyObject::List(items) | PyObject::Set(items) => {
                for it in items {
                    if let PyObject::Str(s) = &**it {
                        out.push(s.clone());
                    }
                }
            }
            _ => {}
        },
        Expr::Name(_) => {}
        Expr::Attribute { value, .. } | Expr::Starred(value) | Expr::Await(value) => {
            collect_expr_strings(value, out)
        }
        Expr::Subscript { value, index } => {
            collect_expr_strings(value, out);
            collect_expr_strings(index, out);
        }
        Expr::Unary { operand, .. } => collect_expr_strings(operand, out),
        Expr::Binary { left, right, .. } => {
            collect_expr_strings(left, out);
            collect_expr_strings(right, out);
        }
        Expr::Compare { operands, .. } | Expr::BoolOp { values: operands, .. } => {
            for o in operands {
                collect_expr_strings(o, out);
            }
        }
        Expr::Call { func, args, keywords, star_args, star_kwargs } => {
            collect_expr_strings(func, out);
            for a in args {
                collect_expr_strings(a, out);
            }
            for (_, v) in keywords {
                collect_expr_strings(v, out);
            }
            if let Some(x) = star_args { collect_expr_strings(x, out); }
            if let Some(x) = star_kwargs { collect_expr_strings(x, out); }
        }
        Expr::Tuple(v) | Expr::List(v) | Expr::Set(v) => {
            for it in v { collect_expr_strings(it, out); }
        }
        Expr::Dict(entries) => {
            for (k, v) in entries {
                collect_expr_strings(k, out);
                collect_expr_strings(v, out);
            }
        }
        Expr::Ternary { cond, then_expr, else_expr } => {
            collect_expr_strings(cond, out);
            collect_expr_strings(then_expr, out);
            collect_expr_strings(else_expr, out);
        }
        Expr::FString(fs) => {
            let mut text = String::new();
            collect_fstring_literals(fs, &mut text);
            out.push(text);
            for p in &fs.parts {
                if let FStringPart::Value { value, .. } = p {
                    collect_expr_strings(value, out);
                }
            }
        }
        _ => {}
    }
}

fn is_empty_tuple(e: &ExprRef) -> bool {
    matches!(&**e, Expr::Tuple(v) if v.is_empty())
}

fn needs_blank_line(cur: &Stmt, prev: Option<&Stmt>) -> bool {
    let is_def = |s: &Stmt| matches!(s, Stmt::FuncDef(..) | Stmt::ClassDef { .. });
    match (is_def(cur), prev.map(is_def)) {
        (true, Some(true)) => true,
        (true, _) => true,
        (_, Some(true)) => true,
        _ => false,
    }
}

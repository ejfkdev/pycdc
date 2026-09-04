//! Version-agnostic abstract syntax tree for decompiled Python code.
//!
//! The decompiler builds this tree from any version's bytecode; the code
//! generator renders it back to source using version-specific syntax rules.

use std::rc::Rc;

use crate::code::CodeObject;
use crate::object::ObjectRef;

pub type ExprRef = Rc<Expr>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UnaryOp {
    Neg,    // -x
    Pos,    // +x
    Invert, // ~x
    Not,    // not x
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinaryOp {
    Add,
    Sub,
    Mult,
    Div,
    FloorDiv,
    Mod,
    Pow,
    LShift,
    RShift,
    BitOr,
    BitXor,
    BitAnd,
    MatMult,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CmpOp {
    Lt,
    LtE,
    Eq,
    NotEq,
    Gt,
    GtE,
    In,
    NotIn,
    Is,
    IsNot,
    /// py2 `except A, e:` matching, rendered specially by codegen.
    ExceptionMatch,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BoolOpKind {
    And,
    Or,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CompKind {
    List,
    Set,
    Dict,
    Generator,
}

#[derive(Debug, Clone)]
pub struct Comprehension {
    pub target: ExprRef,
    pub iter: ExprRef,
    pub ifs: Vec<ExprRef>,
    pub is_async: bool,
}

#[derive(Debug, Clone)]
pub struct Parameters {
    pub args: Vec<Param>,
    pub vararg: Option<Param>,
    pub kwonly: Vec<Param>,
    pub kwarg: Option<Param>,
    /// Defaults align to the tail of `args`.
    pub defaults: Vec<ExprRef>,
    pub kw_defaults: Vec<Option<ExprRef>>,
    /// posonlyargcount (3.8+)
    pub posonly_count: usize,
    /// return annotation stored during MAKE_FUNCTION processing
    pub returns_annotation: Option<ExprRef>,
}

#[derive(Debug, Clone)]
pub struct Param {
    pub name: String,
    pub annotation: Option<ExprRef>,
}

impl Parameters {
    pub fn empty() -> Parameters {
        Parameters {
            args: Vec::new(),
            vararg: None,
            kwonly: Vec::new(),
            kwarg: None,
            defaults: Vec::new(),
            kw_defaults: Vec::new(),
            posonly_count: 0,
            returns_annotation: None,
        }
    }

    pub fn is_empty(&self) -> bool {
        self.args.is_empty()
            && self.vararg.is_none()
            && self.kwonly.is_empty()
            && self.kwarg.is_none()
    }
}

/// One f-string piece: literal text or a formatted replacement field.
#[derive(Debug, Clone)]
pub enum FStringPart {
    Literal(String),
    Value {
        value: ExprRef,
        /// 'r', 's', 'a' or none
        conversion: Option<char>,
        format_spec: Option<Box<FString>>,
    },
}

#[derive(Debug, Clone)]
pub struct FString {
    pub parts: Vec<FStringPart>,
}

#[derive(Debug, Clone)]
pub struct SliceExpr {
    pub start: Option<ExprRef>,
    pub stop: Option<ExprRef>,
    pub step: Option<ExprRef>,
}

#[derive(Debug, Clone)]
pub enum Expr {
    /// A marshalled constant (int, str, tuple of constants, ...).
    Const(ObjectRef),
    Name(String),
    Attribute {
        value: ExprRef,
        attr: String,
    },
    Subscript {
        value: ExprRef,
        index: ExprRef,
    },
    Slice(Box<SliceExpr>),
    Unary {
        op: UnaryOp,
        operand: ExprRef,
    },
    Binary {
        op: BinaryOp,
        left: ExprRef,
        right: ExprRef,
    },
    /// Chained comparisons: `a op0 b op1 c` -> operands.len() == ops.len()+1
    Compare {
        operands: Vec<ExprRef>,
        ops: Vec<CmpOp>,
    },
    BoolOp {
        op: BoolOpKind,
        values: Vec<ExprRef>,
    },
    Call {
        func: ExprRef,
        args: Vec<ExprRef>,
        keywords: Vec<(Option<String>, ExprRef)>,
        /// `*args` expression (CALL_FUNCTION_EX / py2 VAR forms)
        star_args: Option<ExprRef>,
        /// `**kwargs` expression
        star_kwargs: Option<ExprRef>,
    },
    Tuple(Vec<ExprRef>),
    List(Vec<ExprRef>),
    Set(Vec<ExprRef>),
    Dict(Vec<(ExprRef, ExprRef)>),
    Starred(ExprRef),
    Comprehension {
        kind: CompKind,
        elt: ExprRef,
        /// key expression for dict comprehensions
        key: Option<ExprRef>,
        generators: Vec<Comprehension>,
    },
    Lambda {
        params: Box<Parameters>,
        body: ExprRef,
    },
    /// A function object (code + signature) before it is bound by a def
    /// statement or used as a value.
    Function(Rc<FunctionDef>),
    Ternary {
        cond: ExprRef,
        then_expr: ExprRef,
        else_expr: ExprRef,
    },
    Await(ExprRef),
    /// 3.8+ walrus: `(target := value)`
    Named { target: ExprRef, value: ExprRef },
    Yield(Option<ExprRef>),
    YieldFrom(ExprRef),
    FString(Box<FString>),
    /// py2 backquote repr: `x`
    Backquote(ExprRef),
}

#[derive(Debug, Clone)]
pub struct FunctionDef {
    /// def name (from the binding target, since code.name may be mangled)
    pub name: String,
    pub code: Rc<CodeObject>,
    pub params: Parameters,
    pub decorators: Vec<ExprRef>,
    /// return annotation (`-> X`)
    pub returns: Option<ExprRef>,
    pub is_async: bool,
}

#[derive(Debug, Clone)]
pub struct ExceptHandler {
    /// None = bare `except:`
    pub type_: Option<ExprRef>,
    pub name: Option<ExprRef>,
    pub body: Vec<Stmt>,
}

/// 3.10+ `match` statement patterns
#[derive(Debug, Clone)]
pub enum Pattern {
    /// literal or dotted-name value pattern (`case 3:`, `case Color.RED:`)
    Value(ExprRef),
    /// capture pattern (`case x:`)
    Capture(String),
    /// wildcard (`case _:`)
    Wildcard,
    /// `case p1 | p2:`
    Or(Vec<Pattern>),
    /// `case [a, b]` / `case (a, b)`; `star` is the `*rest` element with
    /// the number of items that follow it
    Sequence {
        items: Vec<Pattern>,
        star: Option<(Box<Pattern>, usize)>,
    },
    /// `case {'k': v, **rest}`
    Mapping {
        items: Vec<(ExprRef, Pattern)>,
        rest: Option<String>,
    },
    /// `case Point(x, y=q)`
    Class {
        cls: ExprRef,
        patterns: Vec<Pattern>,
        keywords: Vec<(String, Pattern)>,
    },
}

#[derive(Debug, Clone)]
pub struct MatchCase {
    pub pattern: Pattern,
    pub guard: Option<ExprRef>,
    pub body: Vec<Stmt>,
}

#[derive(Debug, Clone)]
pub struct WithItem {
    pub ctx: ExprRef,
    pub target: Option<ExprRef>,
}

#[derive(Debug, Clone)]
pub enum Stmt {
    Expr(ExprRef),
    Assign {
        targets: Vec<ExprRef>,
        value: ExprRef,
    },
    AugAssign {
        target: ExprRef,
        op: BinaryOp,
        value: ExprRef,
    },
    AnnAssign {
        target: ExprRef,
        annotation: ExprRef,
        value: Option<ExprRef>,
    },
    /// py2 `print` statement
    Print {
        dest: Option<ExprRef>,
        values: Vec<ExprRef>,
        newline: bool,
    },
    /// py2 `exec` statement
    Exec {
        code: ExprRef,
        globals: Option<ExprRef>,
        locals: Option<ExprRef>,
    },
    Return(Option<ExprRef>),
    Delete(Vec<ExprRef>),
    Pass,
    Break,
    Continue,
    Import {
        /// (module, asname)
        names: Vec<(String, Option<String>)>,
    },
    ImportFrom {
        module: String,
        level: u32,
        /// (name, asname); single ("*", None) for star imports
        names: Vec<(String, Option<String>)>,
    },
    Global(Vec<String>),
    Nonlocal(Vec<String>),
    If {
        cond: ExprRef,
        body: Vec<Stmt>,
        orelse: Vec<Stmt>,
    },
    While {
        cond: ExprRef,
        body: Vec<Stmt>,
        orelse: Vec<Stmt>,
    },
    For {
        target: ExprRef,
        iter: ExprRef,
        body: Vec<Stmt>,
        orelse: Vec<Stmt>,
        is_async: bool,
    },
    Try {
        body: Vec<Stmt>,
        handlers: Vec<ExceptHandler>,
        orelse: Vec<Stmt>,
        finalbody: Vec<Stmt>,
    },
    With {
        items: Vec<WithItem>,
        body: Vec<Stmt>,
        is_async: bool,
    },
    Raise {
        exc: Option<ExprRef>,
        cause: Option<ExprRef>,
    },
    Assert {
        test: ExprRef,
        msg: Option<ExprRef>,
    },
    FuncDef(Rc<FunctionDef>, Vec<Stmt>),
    ClassDef {
        name: String,
        bases: Vec<ExprRef>,
        keywords: Vec<(Option<String>, ExprRef)>,
        star_args: Option<ExprRef>,
        star_kwargs: Option<ExprRef>,
        decorators: Vec<ExprRef>,
        body: Vec<Stmt>,
    },
    /// 3.10+ `match subject: case ...:`
    Match {
        subject: ExprRef,
        cases: Vec<MatchCase>,
    },
    /// Fallback for bytecode we could not model; keeps the disassembly text
    /// so output stays informative (graceful degradation).
    Unimplemented(String),
}

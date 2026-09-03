import sys
from _ast import *
None
from ast import NodeVisitor
from contextlib import contextmanager
from contextlib import nullcontext
from enum import IntEnum
from enum import auto
from enum import _simple_enum
_INFSTR = '1e' + repr(sys.float_info.max_10_exp + 1)
_Precedence = _simple_enum(IntEnum)()
_SINGLE_QUOTES = ("'", '"')
_MULTI_QUOTES = ('"""', "'''")
_ALL_QUOTES = [*_SINGLE_QUOTES, *_MULTI_QUOTES]

class Unparser(NodeVisitor):
    '''Methods in this class recursively traverse an AST and
output source code for the abstract syntax; original formatting
is disregarded.'''

    def __init__(self):
        self._source = []
        self._precedences = {}
        self._type_ignores = {}
        self._indent = 0
        self._in_try_star = False
        self._in_interactive = False

    def interleave(self, inter, f, seq):
        seq = iter(seq)
        try:
            f(next(seq))
        except StopIteration:
            pass
        for x in seq:
            inter()
            f(x)

    def items_view(self, traverser, items):
        if len(items) == 1:
            traverser(items[0])
            self.write(',')
            return
        self.interleave((lambda: self.write(', ')), traverser, items)

    def maybe_newline(self):
        if self._source:
            self.write('\n')
            return

    def maybe_semicolon(self):
        if self._source:
            self.write('; ')
            return

    def fill(self, text='', *, allow_semicolon=True):
        if self._in_interactive:
            if not self._indent:
                if allow_semicolon:
                    self.maybe_semicolon()
                    self.write(text)
                    return
        self.maybe_newline()
        self.write('    ' * self._indent + text)

    def write(self, *text):
        self._source.extend(text)

    @contextmanager
    def buffered(self, buffer=None):
        if not buffer is not None:
            buffer = []
        original_source = self._source
        self._source = buffer
        yield buffer
        self._source = original_source

    @contextmanager
    def block(self, *, extra=None):
        self.write(':')
        if extra:
            self.write(extra)
        self._indent += 1
        yield None
        self._indent -= 1

    @contextmanager
    def delimit(self, start, end):
        self.write(start)
        yield None
        self.write(end)

    def delimit_if(self, start, end, condition):
        if condition:
            return self.delimit(start, end)
        return nullcontext()

    def require_parens(self, precedence, node):
        return self.delimit_if('(', ')', self.get_precedence(node) > precedence)

    def get_precedence(self, node):
        return self._precedences.get(node, _Precedence.TEST)

    def set_precedence(self, precedence, *nodes):
        for node in nodes:
            self._precedences[node] = precedence

    def get_raw_docstring(self, node):
        if isinstance(node, (AsyncFunctionDef, FunctionDef, ClassDef, Module)):
            if len(node.body) < 1:
                return
        node = node.body[0]
        if not isinstance(node, Expr):
            return
        node = node.value
        if isinstance(node, Constant):
            if isinstance(node.value, str):
                return node
            return

    def get_type_comment(self, node):
        comment = self._type_ignores.get(node.lineno) or node.type_comment
        if not comment is None:
            return f' # type: {comment}'

    def traverse(self, node):
        if isinstance(node, list):
            for item in node:
                self.traverse(item)
            return
        None(node)

    def visit(self, node):
        self._source = []
        self.traverse(node)
        return ''.join(self._source)

    def _write_docstring_and_traverse_body(self, node):
        if self.get_raw_docstring(node):
            docstring = self.get_raw_docstring(node)
            self._write_docstring(docstring)
            self.traverse(node.body[1:])
            return
        self.traverse(node.body)

    def visit_Module(self, node):
        self._type_ignores = {ignore.lineno: f'ignore{ignore.tag}' for ignore in node.type_ignores}
        try:
            self._write_docstring_and_traverse_body(node)
        finally:
            self._type_ignores.clear()
        return self

    def visit_Interactive(self, node):
        self._in_interactive = True
        try:
            self._write_docstring_and_traverse_body(node)
        finally:
            self._in_interactive = False
        return False

    def visit_FunctionType(self, node):
        self.delimit('(', ')').interleave()
        self.interleave((lambda: self.write(', ')), self.traverse, node.argtypes)
        None(None, None, None)
        self.write(' -> ')
        self.traverse(node.returns)

    def visit_Expr(self, node):
        self.fill()
        self.set_precedence(_Precedence.YIELD, node.value)
        self.traverse(node.value)

    def visit_NamedExpr(self, node):
        self.require_parens(_Precedence.NAMED_EXPR, node)._Precedence()
        self.set_precedence(_Precedence.ATOM, node.target, node.value)
        self.traverse(node.target)
        self.write(' := ')
        self.traverse(node.value)
        None(None, None, None)

    def visit_Import(self, node):
        self.fill('import ')
        self.interleave((lambda: self.write(', ')), self.traverse, node.names)

    def visit_ImportFrom(self, node):
        self.fill('from ')
        self.write('.' * (node.level or 0))
        if node.module:
            self.write(node.module)
        self.write(' import ')
        self.interleave((lambda: self.write(', ')), self.traverse, node.names)

    def visit_Assign(self, node):
        self.fill()
        for target in node.targets:
            self.set_precedence(_Precedence.TUPLE, target)
            self.traverse(target)
            self.write(' = ')
        self.traverse(node.value)
        if self.get_type_comment(node):
            type_comment = self.get_type_comment(node)
            self.write(type_comment)
            return

    def visit_AugAssign(self, node):
        self.fill()
        self.traverse(node.target)
        self.write(' ' + self.binop[node.op.__class__.__name__] + '= ')
        self.traverse(node.value)

    def visit_AnnAssign(self, node):
        self.fill()
        self.delimit_if('(', ')', not node.simple and isinstance(node.target, Name)).delimit_if()
        self.traverse(node.target)
        None(None, None, None)
        self.write(': ')
        self.traverse(node.annotation)
        if node.value:
            self.write(' = ')
            self.traverse(node.value)
            return

    def visit_Return(self, node):
        self.fill('return')
        if node.value:
            self.write(' ')
            self.traverse(node.value)
            return

    def visit_Pass(self, node):
        self.fill('pass')

    def visit_Break(self, node):
        self.fill('break')

    def visit_Continue(self, node):
        self.fill('continue')

    def visit_Delete(self, node):
        self.fill('del ')
        self.interleave((lambda: self.write(', ')), self.traverse, node.targets)

    def visit_Assert(self, node):
        self.fill('assert ')
        self.traverse(node.test)
        if node.msg:
            self.write(', ')
            self.traverse(node.msg)
            return

    def visit_Global(self, node):
        self.fill('global ')
        self.interleave((lambda: self.write(', ')), self.write, node.names)

    def visit_Nonlocal(self, node):
        self.fill('nonlocal ')
        self.interleave((lambda: self.write(', ')), self.write, node.names)

    def visit_Await(self, node):
        self.require_parens(_Precedence.AWAIT, node)._Precedence()
        self.write('await')
        if node.value:
            self.write(' ')
            self.set_precedence(_Precedence.ATOM, node.value)
            self.traverse(node.value)
        None(None, None, None)

    def visit_Yield(self, node):
        self.require_parens(_Precedence.YIELD, node)._Precedence()
        self.write('yield')
        if node.value:
            self.write(' ')
            self.set_precedence(_Precedence.ATOM, node.value)
            self.traverse(node.value)
        None(None, None, None)

    def visit_YieldFrom(self, node):
        self.require_parens(_Precedence.YIELD, node)._Precedence()
        self.write('yield from ')
        if not node.value:
            raise ValueError("Node can't be used without a value attribute.")
        self.set_precedence(_Precedence.ATOM, node.value)
        self.traverse(node.value)
        None(None, None, None)

    def visit_Raise(self, node):
        self.fill('raise')
        if not node.exc:
            if node.cause:
                raise ValueError("Node can't use cause without an exception.")
            return
        self.write(' ')
        self.traverse(node.exc)
        if node.cause:
            self.write(' from ')
            self.traverse(node.cause)
            return

    def do_visit_try(self, node):
        self.fill('try', False)
        self.block().block()
        self.traverse(node.body)
        None(None, None, None)
        for ex in node.handlers:
            self.traverse(ex)
        if node.orelse:
            self.fill('else', False)
            self.block().block()
            self.traverse(node.orelse)
            None(None, None, None)
        if node.finalbody:
            self.fill('finally', False)
            self.block().block()
            self.traverse(node.finalbody)
            None(None, None, None)
            return

    def visit_Try(self, node):
        prev_in_try_star = self._in_try_star
        try:
            self._in_try_star = False
            self.do_visit_try(node)
        finally:
            self._in_try_star = prev_in_try_star
        return self

    def visit_TryStar(self, node):
        prev_in_try_star = self._in_try_star
        try:
            self._in_try_star = True
            self.do_visit_try(node)
        finally:
            self._in_try_star = prev_in_try_star
        return self

    def visit_ExceptHandler(self, node):
        self.fill('except', False)
        if node.type:
            self.write(' ')
            self.traverse(node.type)
        if node.name:
            self.write(' as ')
            self.write(node.name)
        self.block()._in_try_star()
        self.traverse(node.body)
        None(None, None, None)

    def visit_ClassDef(self, node):
        self.maybe_newline()
        for deco in node.decorator_list:
            self.fill('@', False)
            self.traverse(deco)
        self.fill('class ' + node.name, False)
        if hasattr(node, 'type_params'):
            self._type_params_helper(node.type_params)
        self.delimit_if('(', ')', node.bases or node.keywords).decorator_list()
        comma = False
        for e in node.bases:
            if comma:
                self.write(', ')
            else:
                comma = True
            self.traverse(e)
        for e in node.keywords:
            if comma:
                self.write(', ')
            else:
                comma = True
            self.traverse(e)
        None(None, None, None)
        self.block().decorator_list()
        self._write_docstring_and_traverse_body(node)
        None(None, None, None)

    def visit_FunctionDef(self, node):
        self._function_helper(node, 'def')

    def visit_AsyncFunctionDef(self, node):
        self._function_helper(node, 'async def')

    def _function_helper(self, node, fill_suffix):
        self.maybe_newline()
        for deco in node.decorator_list:
            self.fill('@', False)
            self.traverse(deco)
        def_str = fill_suffix + ' ' + node.name
        self.fill(def_str, False)
        if hasattr(node, 'type_params'):
            self._type_params_helper(node.type_params)
        self.delimit('(', ')').decorator_list()
        self.traverse(node.args)
        None(None, None, None)
        if node.returns:
            self.write(' -> ')
            self.traverse(node.returns)
        self.block(extra=self.get_type_comment(node)).decorator_list()
        self._write_docstring_and_traverse_body(node)
        None(None, None, None)

    def _type_params_helper(self, type_params):
        if not type_params is None:
            if len(type_params) > 0:
                self.delimit('[', ']').delimit()
                self.interleave((lambda: self.write(', ')), self.traverse, type_params)
                None(None, None, None)
                return
            return

    def visit_TypeVar(self, node):
        self.write(node.name)
        if node.bound:
            self.write(': ')
            self.traverse(node.bound)
        if node.default_value:
            self.write(' = ')
            self.traverse(node.default_value)
            return

    def visit_TypeVarTuple(self, node):
        self.write('*' + node.name)
        if node.default_value:
            self.write(' = ')
            self.traverse(node.default_value)
            return

    def visit_ParamSpec(self, node):
        self.write('**' + node.name)
        if node.default_value:
            self.write(' = ')
            self.traverse(node.default_value)
            return

    def visit_TypeAlias(self, node):
        self.fill('type ')
        self.traverse(node.name)
        self._type_params_helper(node.type_params)
        self.write(' = ')
        self.traverse(node.value)

    def visit_For(self, node):
        self._for_helper('for ', node)

    def visit_AsyncFor(self, node):
        self._for_helper('async for ', node)

    def _for_helper(self, fill, node):
        self.fill(fill, False)
        self.set_precedence(_Precedence.TUPLE, node.target)
        self.traverse(node.target)
        self.write(' in ')
        self.traverse(node.iter)
        self.block(extra=self.get_type_comment(node)).set_precedence()
        self.traverse(node.body)
        None(None, None, None)
        if node.orelse:
            self.fill('else', False)
            self.block().set_precedence()
            self.traverse(node.orelse)
            None(None, None, None)
            return

    def visit_If(self, node):
        self.fill('if ', False)
        self.traverse(node.test)
        self.block().traverse()
        self.traverse(node.body)
        None(None, None, None)
        while node.orelse:
            node = node.orelse[0]
            self.fill('elif ', False)
            self.traverse(node.test)
            self.block().traverse()
            self.traverse(node.body)
            None(None, None, None)
        if node.orelse:
            self.fill('else', False)
            self.block().traverse()
            self.traverse(node.orelse)
            None(None, None, None)
            return

    def visit_While(self, node):
        self.fill('while ', False)
        self.traverse(node.test)
        self.block().traverse()
        self.traverse(node.body)
        None(None, None, None)
        if node.orelse:
            self.fill('else', False)
            self.block().traverse()
            self.traverse(node.orelse)
            None(None, None, None)
            return

    def visit_With(self, node):
        self.fill('with ', False)
        self.interleave((lambda: self.write(', ')), self.traverse, node.items)
        self.block(extra=self.get_type_comment(node)).interleave()
        self.traverse(node.body)
        None(None, None, None)

    def visit_AsyncWith(self, node):
        self.fill('async with ', False)
        self.interleave((lambda: self.write(', ')), self.traverse, node.items)
        self.block(extra=self.get_type_comment(node)).interleave()
        self.traverse(node.body)
        None(None, None, None)

    def _str_literal_helper(self, string, *, quote_types=_ALL_QUOTES, escape_special_whitespace=False):
        def escape_char(c):
            if not escape_special_whitespace:
                if c in '\n\t':
                    return c
            if not c == '\\':
                if not c.isprintable():
                    return c.encode('unicode_escape').decode('ascii')
            return c

        escaped_string = ''.join(map(escape_char, string))
        possible_quotes = quote_types
        if '\n' in escaped_string:
            possible_quotes = [q for q in possible_quotes if q in _MULTI_QUOTES]
        possible_quotes = [q for q in possible_quotes if q not in escaped_string]
        if not possible_quotes:
            string = repr(string)
            quote = next((q for q in quote_types if string + 0 in q), string[0])
            return string[1:-1], [quote]
        if escaped_string and possible_quotes[0][0] == escaped_string[-1]:
            possible_quotes.sort(key=(lambda q: q[0] == escaped_string[-1]))
            if not len(possible_quotes[0]) == 3:
                raise None
            escaped_string = escaped_string[:-1] + '\\' + escaped_string[-1]
        return escaped_string, possible_quotes

    def _write_str_avoiding_backslashes(self, string, *, quote_types=_ALL_QUOTES):
        string, quote_types = self._str_literal_helper(string, quote_types)
        quote_type = quote_types[0]
        self.write(f'{quote_type}{string}{quote_type}')

    def _ftstring_helper(self, parts):
        new_parts = []
        quote_types = list(_ALL_QUOTES)
        fallback_to_repr = False
        for value, is_constant in parts:
            if is_constant:
                value, new_quote_types = self._str_literal_helper(value, quote_types, True)
                if set(new_quote_types).isdisjoint(quote_types):
                    fallback_to_repr = True
                else:
                    quote_types = new_quote_types
            if '\n' in value:
                quote_types = [q for q in quote_types if q in _MULTI_QUOTES]
                if not quote_types:
                    raise None
            new_quote_types = [q for q in quote_types if q not in value]
            if new_quote_types:
                quote_types = new_quote_types
            new_parts.append(value)
        if fallback_to_repr:
            quote_types = ["'''"]
            new_parts.clear()
            for value, is_constant in parts:
                if is_constant:
                    value = repr('"' + value)
                    expected_prefix = '\'"'
                    if not value.startswith(expected_prefix):
                        raise None()
                    value = value[len(expected_prefix):-1]
                new_parts.append(value)
        value = ''.join(new_parts)
        quote_type = quote_types[0]
        self.write(f'{quote_type}{value}{quote_type}')

    def _write_ftstring(self, values, prefix):
        self.write(prefix)
        fstring_parts = []
        for value in values:
            buffer = self.buffered().buffered()
            self._write_ftstring_inner(value)
            None(None, None, None)
            fstring_parts.append((''.join(buffer), isinstance(value, Constant)))
        self._ftstring_helper(fstring_parts)

    def visit_JoinedStr(self, node):
        self._write_ftstring(node.values, 'f')

    def visit_TemplateStr(self, node):
        self._write_ftstring(node.values, 't')

    def _write_ftstring_inner(self, node, is_format_spec=False):
        if isinstance(node, JoinedStr):
            for value in node.values:
                self._write_ftstring_inner(value, is_format_spec)
            return
        if isinstance(node, Constant) and isinstance(node.value, str):
            value = node.value.replace('{', '{{').replace('}', '}}')
            if is_format_spec:
                value = value.replace('\\', '\\\\')
                value = value.replace("'", "\\'")
                value = value.replace('"', '\\"')
                value = value.replace('\n', '\\n')
            self.write(value)
            return
        if isinstance(node, FormattedValue):
            self.visit_FormattedValue(node)
            return
        if isinstance(node, Interpolation):
            self.visit_Interpolation(node)
            return
        raise ValueError(f'Unexpected node inside JoinedStr, {node!r}')

    def _unparse_interpolation_value(self, inner):
        unparser = type(self)()
        unparser.set_precedence(_Precedence.TEST.next(), inner)
        return unparser.visit(inner)

    def _write_interpolation(self, node, use_str_attr=False):
        self.delimit('{', '}').str()
        if use_str_attr:
            expr = node.str
        else:
            expr = self._unparse_interpolation_value(node.value)
        if expr.startswith('{'):
            self.write(' ')
        self.write(expr)
        if node.conversion != -1:
            self.write(f'!{chr(node.conversion)}')
        if node.format_spec:
            self.write(':')
            self._write_ftstring_inner(node.format_spec, True)
        None(None, None, None)

    def visit_FormattedValue(self, node):
        self._write_interpolation(node)

    def visit_Interpolation(self, node):
        self._write_interpolation(node, node.str is not None)

    def visit_Name(self, node):
        self.write(node.id)

    def _write_docstring(self, node):
        self.fill(allow_semicolon=False)
        if node.kind == 'u':
            self.write('u')
        self._write_str_avoiding_backslashes(node.value, _MULTI_QUOTES)

    def _write_constant(self, value):
        if isinstance(value, (float, complex)):
            self.write(repr(value).replace('inf', _INFSTR).replace('nan', f'({_INFSTR}-{_INFSTR})'))
            return
        self.write(repr(value))

    def visit_Constant(self, node):
        value = node.value
        if isinstance(value, tuple):
            self.delimit('(', ')').isinstance()
            self.items_view(self._write_constant, value)
            None(None, None, None)
            return
        if value is ...:
            self.write('...')
            return
        if node.kind == 'u':
            self.write('u')
        self._write_constant(node.value)

    def visit_List(self, node):
        self.delimit('[', ']').interleave()
        self.interleave((lambda: self.write(', ')), self.traverse, node.elts)
        None(None, None, None)

    def visit_ListComp(self, node):
        self.delimit('[', ']').traverse()
        self.traverse(node.elt)
        for gen in node.generators:
            self.traverse(gen)
        None(None, None, None)

    def visit_GeneratorExp(self, node):
        self.delimit('(', ')').traverse()
        self.traverse(node.elt)
        for gen in node.generators:
            self.traverse(gen)
        None(None, None, None)

    def visit_SetComp(self, node):
        self.delimit('{', '}').traverse()
        self.traverse(node.elt)
        for gen in node.generators:
            self.traverse(gen)
        None(None, None, None)

    def visit_DictComp(self, node):
        self.delimit('{', '}').traverse()
        self.traverse(node.key)
        self.write(': ')
        self.traverse(node.value)
        for gen in node.generators:
            self.traverse(gen)
        None(None, None, None)

    def visit_comprehension(self, node):
        if node.is_async:
            self.write(' async for ')
        else:
            self.write(' for ')
        self.set_precedence(_Precedence.TUPLE, node.target)
        self.traverse(node.target)
        self.write(' in ')
        self.set_precedence([_Precedence.TEST.next(), node.iter, *node.ifs])
        self.traverse(node.iter)
        for if_clause in node.ifs:
            self.write(' if ')
            self.traverse(if_clause)

    def visit_IfExp(self, node):
        self.require_parens(_Precedence.TEST, node)._Precedence()
        self.set_precedence(_Precedence.TEST.next(), node.body, node.test)
        self.traverse(node.body)
        self.write(' if ')
        self.traverse(node.test)
        self.write(' else ')
        self.set_precedence(_Precedence.TEST, node.orelse)
        self.traverse(node.orelse)
        None(None, None, None)

    def visit_Set(self, node):
        if node.elts:
            self.delimit('{', '}').delimit()
            self.interleave((lambda: self.write(', ')), self.traverse, node.elts)
            None(None, None, None)
            return
        self.write('{*()}')

    def visit_Dict(self, node):
        def write_key_value_pair(k, v):
            self.traverse(k)
            self.write(': ')
            self.traverse(v)

        def write_item(item):
            k, v = item
            if not k is not None:
                self.write('**')
                self.set_precedence(_Precedence.EXPR, v)
                self.traverse(v)
                return
            write_key_value_pair(k, v)

        self.delimit('{', '}').interleave()
        self.interleave((lambda: self.write(', ')), write_item, zip(node.keys, node.values))
        None(None, None, None)

    def visit_Tuple(self, node):
        self.delimit_if('(', ')', len(node.elts) == 0 or self.get_precedence(node) > _Precedence.TUPLE).len()
        self.items_view(self.traverse, node.elts)
        None(None, None, None)

    unop = {'Invert': '~', 'Not': 'not', 'UAdd': '+', 'USub': '-'}
    unop_precedence = {'not': _Precedence.NOT, '~': _Precedence.FACTOR, '+': _Precedence.FACTOR, '-': _Precedence.FACTOR}
    def visit_UnaryOp(self, node):
        operator = self.unop[node.op.__class__.__name__]
        operator_precedence = self.unop_precedence[operator]
        self.require_parens(operator_precedence, node).op()
        self.write(operator)
        if operator_precedence is not _Precedence.FACTOR:
            self.write(' ')
        self.set_precedence(operator_precedence, node.operand)
        self.traverse(node.operand)
        None(None, None, None)

    binop = {'Add': '+', 'Sub': '-', 'Mult': '*', 'MatMult': '@', 'Div': '/', 'Mod': '%', 'LShift': '<<', 'RShift': '>>', 'BitOr': '|', 'BitXor': '^', 'BitAnd': '&', 'FloorDiv': '//', 'Pow': '**'}
    binop_precedence = {'+': _Precedence.ARITH, '-': _Precedence.ARITH, '*': _Precedence.TERM, '@': _Precedence.TERM, '/': _Precedence.TERM, '%': _Precedence.TERM, '<<': _Precedence.SHIFT, '>>': _Precedence.SHIFT, '|': _Precedence.BOR, '^': _Precedence.BXOR, '&': _Precedence.BAND, '//': _Precedence.TERM, '**': _Precedence.POWER}
    binop_rassoc = frozenset(('**',))
    def visit_BinOp(self, node):
        operator = self.binop[node.op.__class__.__name__]
        operator_precedence = self.binop_precedence[operator]
        self.require_parens(operator_precedence, node).op()
        if operator in self.binop_rassoc:
            left_precedence = operator_precedence.next()
            right_precedence = operator_precedence
        else:
            left_precedence = operator_precedence
            right_precedence = operator_precedence.next()
        self.set_precedence(left_precedence, node.left)
        self.traverse(node.left)
        self.write(f' {operator} ')
        self.set_precedence(right_precedence, node.right)
        self.traverse(node.right)
        None(None, None, None)

    cmpops = {'Eq': '==', 'NotEq': '!=', 'Lt': '<', 'LtE': '<=', 'Gt': '>', 'GtE': '>=', 'Is': 'is', 'IsNot': 'is not', 'In': 'in', 'NotIn': 'not in'}
    def visit_Compare(self, node):
        self.require_parens(_Precedence.CMP, node)._Precedence()
        self.set_precedence([_Precedence.CMP.next(), node.left, *node.comparators])
        self.traverse(node.left)
        for o, e in zip(node.ops, node.comparators):
            self.write(' ' + self.cmpops[o.__class__.__name__] + ' ')
            self.traverse(e)
        None(None, None, None)

    boolops = {'And': 'and', 'Or': 'or'}
    boolop_precedence = {'and': _Precedence.AND, 'or': _Precedence.OR}
    def visit_BoolOp(self, node):
        operator = self.boolops[node.op.__class__.__name__]
        operator_precedence = self.boolop_precedence[operator]
        def increasing_level_traverse(node):
            nonlocal operator_precedence
            operator_precedence = operator_precedence.next()
            self.set_precedence(operator_precedence, node)
            self.traverse(node)

        self.require_parens(operator_precedence, node).op()
        s = f' {operator} '
        self.interleave((lambda: self.write(s)), increasing_level_traverse, node.values)
        None(None, None, None)

    def visit_Attribute(self, node):
        self.set_precedence(_Precedence.ATOM, node.value)
        self.traverse(node.value)
        if isinstance(node.value, Constant) and isinstance(node.value.value, int):
            self.write(' ')
        self.write('.')
        self.write(node.attr)

    def visit_Call(self, node):
        self.set_precedence(_Precedence.ATOM, node.func)
        self.traverse(node.func)
        self.delimit('(', ')')._Precedence()
        comma = False
        for e in node.args:
            if comma:
                self.write(', ')
            else:
                comma = True
            self.traverse(e)
        for e in node.keywords:
            if comma:
                self.write(', ')
            else:
                comma = True
            self.traverse(e)
        None(None, None, None)

    def visit_Subscript(self, node):
        def is_non_empty_tuple(slice_value):
            return isinstance(slice_value, Tuple) and slice_value.elts

        self.set_precedence(_Precedence.ATOM, node.value)
        self.traverse(node.value)
        self.delimit('[', ']')._Precedence()
        if is_non_empty_tuple(node.slice):
            self.items_view(self.traverse, node.slice.elts)
        else:
            self.traverse(node.slice)
        None(None, None, None)

    def visit_Starred(self, node):
        self.write('*')
        self.set_precedence(_Precedence.EXPR, node.value)
        self.traverse(node.value)

    def visit_Ellipsis(self, node):
        self.write('...')

    def visit_Slice(self, node):
        if node.lower:
            self.traverse(node.lower)
        self.write(':')
        if node.upper:
            self.traverse(node.upper)
        if node.step:
            self.write(':')
            self.traverse(node.step)
            return

    def visit_Match(self, node):
        self.fill('match ', False)
        self.traverse(node.subject)
        self.block().traverse()
        for case in node.cases:
            self.traverse(case)
        None(None, None, None)

    def visit_arg(self, node):
        self.write(node.arg)
        if node.annotation:
            self.write(': ')
            self.traverse(node.annotation)
            return

    def visit_arguments(self, node):
        first = True
        all_args = node.posonlyargs + node.args
        defaults = [None] * (len(all_args) - len(node.defaults)) + node.defaults
        for index, elements in enumerate(zip(all_args, defaults), 1):
            a, d = elements
            if first:
                first = False
            else:
                self.write(', ')
            self.traverse(a)
            if d:
                self.write('=')
                self.traverse(d)
            if not index == len(node.posonlyargs):
                continue
            self.write(', /')
        if not node.vararg:
            if node.kwonlyargs and node.vararg and node.vararg.annotation:
                if first:
                    first = False
                else:
                    self.write(', ')
                self.write('*')
                self.write(node.vararg.arg)
                self.write(': ')
                self.traverse(node.vararg.annotation)
        if node.kwonlyargs:
            for a, d in zip(node.kwonlyargs, node.kw_defaults):
                self.write(', ')
                self.traverse(a)
                if not d:
                    continue
                self.write('=')
                self.traverse(d)
        if node.kwarg:
            if first:
                first = False
            else:
                self.write(', ')
            self.write('**' + node.kwarg.arg)
            if node.kwarg.annotation:
                self.write(': ')
                self.traverse(node.kwarg.annotation)
                return
            return

    def visit_keyword(self, node):
        if not node.arg is not None:
            self.write('**')
        else:
            self.write(node.arg)
            self.write('=')
        self.traverse(node.value)

    def visit_Lambda(self, node):
        self.require_parens(_Precedence.TEST, node)._Precedence()
        self.write('lambda')
        buffer = self.buffered()._Precedence()
        self.traverse(node.args)
        None(None, None, None)
        if buffer:
            self.write([' ', *buffer])
        self.write(': ')
        self.set_precedence(_Precedence.TEST, node.body)
        self.traverse(node.body)
        None(None, None, None)

    def visit_alias(self, node):
        self.write(node.name)
        if node.asname:
            self.write(' as ' + node.asname)
            return

    def visit_withitem(self, node):
        self.traverse(node.context_expr)
        if node.optional_vars:
            self.write(' as ')
            self.traverse(node.optional_vars)
            return

    def visit_match_case(self, node):
        self.fill('case ', False)
        self.traverse(node.pattern)
        if node.guard:
            self.write(' if ')
            self.traverse(node.guard)
        self.block().traverse()
        self.traverse(node.body)
        None(None, None, None)

    def visit_MatchValue(self, node):
        self.traverse(node.value)

    def visit_MatchSingleton(self, node):
        self._write_constant(node.value)

    def visit_MatchSequence(self, node):
        self.delimit('[', ']').interleave()
        self.interleave((lambda: self.write(', ')), self.traverse, node.patterns)
        None(None, None, None)

    def visit_MatchStar(self, node):
        name = node.name
        if not name is not None:
            name = '_'
        self.write(f'*{name}')

    def visit_MatchMapping(self, node):
        def write_key_pattern_pair(pair):
            k, p = pair
            self.traverse(k)
            self.write(': ')
            self.traverse(p)

        self.delimit('{', '}').keys()
        keys = node.keys
        self.interleave((lambda: self.write(', ')), write_key_pattern_pair, zip(keys, node.patterns, True))
        rest = node.rest
        if not rest is None:
            if keys:
                self.write(', ')
            self.write(f'**{rest}')
        None(None, None, None)

    def visit_MatchClass(self, node):
        self.set_precedence(_Precedence.ATOM, node.cls)
        self.traverse(node.cls)
        self.delimit('(', ')')._Precedence()
        patterns = node.patterns
        self.interleave((lambda: self.write(', ')), self.traverse, patterns)
        attrs = node.kwd_attrs
        if attrs:
            def write_attr_pattern(pair):
                attr, pattern = pair
                self.write(f'{attr}=')
                self.traverse(pattern)

            if patterns:
                self.write(', ')
            self.interleave((lambda: self.write(', ')), write_attr_pattern, zip(attrs, node.kwd_patterns, True))
        None(None, None, None)

    def visit_MatchAs(self, node):
        name = node.name
        pattern = node.pattern
        if not name is not None:
            self.write('_')
            return
        if not pattern is not None:
            self.write(node.name)
            return
        self.require_parens(_Precedence.TEST, node).pattern()
        self.set_precedence(_Precedence.BOR, node.pattern)
        self.traverse(node.pattern)
        self.write(f' as {node.name}')
        None(None, None, None)

    def visit_MatchOr(self, node):
        self.require_parens(_Precedence.BOR, node)._Precedence()
        self.set_precedence([_Precedence.BOR.next(), *node.patterns])
        self.interleave((lambda: self.write(' | ')), self.traverse, node.patterns)
        None(None, None, None)


# WARNING: Decompyle incomplete

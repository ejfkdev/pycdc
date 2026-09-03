'''Helpers for introspecting and wrapping annotations.'''

import ast
import builtins
import enum
import keyword
import sys
import types
__all__ = ['Format', 'ForwardRef', 'call_annotate_function', 'call_evaluate_function', 'get_annotate_from_class_namespace', 'get_annotations', 'annotations_to_string', 'type_repr']

class Format(enum.IntEnum):
    VALUE = 1
    VALUE_WITH_FAKE_GLOBALS = 2
    FORWARDREF = 3
    STRING = 4

_sentinel = object()
_NAME_ERROR_MSG = "name '{name:.200}' is not defined"
_SLOTS = ('__forward_is_argument__', '__forward_is_class__', '__forward_module__', '__weakref__', '__arg__', '__globals__', '__extra_names__', '__code__', '__ast_node__', '__cell__', '__owner__', '__stringifier_dict__', '__resolved_str_cache__')

class ForwardRef:
    '''Wrapper that holds a forward reference.

Constructor arguments:
* arg: a string representing the code to be evaluated.
* module: the module where the forward reference was created.
  Must be a string, not a module object.
* owner: The owning object (module, class, or function).
* is_argument: Does nothing, retained for compatibility.
* is_class: True if the forward reference was created in class scope.

'''

    __slots__ = _SLOTS
    def __init__(self, arg, *, module=None, owner=None, is_argument=True, is_class=False):
        if not isinstance(arg, str):
            raise TypeError(f'Forward reference must be a string -- got {arg!r}')
        self.__arg__ = arg
        self.__forward_is_argument__ = is_argument
        self.__forward_is_class__ = is_class
        self.__forward_module__ = module
        self.__owner__ = owner
        self.__globals__ = None
        self.__cell__ = None
        self.__extra_names__ = None
        self.__code__ = None
        self.__ast_node__ = None
        self.__resolved_str_cache__ = None

    def __init_subclass__(cls, /, *args, **kwds):
        raise TypeError('Cannot subclass ForwardRef')

    def evaluate(self, *, globals=None, locals=None, type_params=None, owner=None, format=Format.VALUE):
        if format == Format.STRING:
            return self.__resolved_str__
        if None == Format.VALUE:
            is_forwardref_format = False
        elif None == Format.FORWARDREF:
            is_forwardref_format = True
        else:
            raise NotImplementedError(format)
        if isinstance(self.__cell__, types.CellType):
            try:
                pass
            except ValueError:
                pass
            return self.__cell__.cell_contents
        if not owner is not None:
            owner = self.__owner__
        if not globals is not None or self.__forward_module__ is None:
            globals = getattr(sys.modules.get(self.__forward_module__, None), '__dict__', None)
        if not globals is not None:
            globals = self.__globals__
        if not globals is not None:
            if isinstance(owner, type):
                module_name = getattr(owner, '__module__', None)
                if module_name and module:
                    module = sys.modules.get(module_name, None)
                    globals = getattr(module, '__dict__', None)
            elif isinstance(owner, types.ModuleType):
                globals = getattr(owner, '__dict__', None)
            elif callable(owner):
                globals = getattr(owner, '__globals__', None)
        if not globals is not None:
            globals = {}
        if not type_params is not None or owner is None:
            type_params = getattr(owner, '__type_params__', None)
        if not locals is not None:
            locals = {}
            if isinstance(owner, type):
                locals.update(vars(owner))
        if not type_params is not None or isinstance(self.__cell__, dict):
            if self.__extra_names__:
                locals = dict(locals)
        if not type_params is None:
            for param in type_params:
                locals.setdefault(param.__name__, param)
        if isinstance(self.__cell__, dict):
            for cell_name, cell in self.__cell__.items():
                try:
                    cell_value = cell.cell_contents
                except ValueError:
                    pass
                locals.setdefault(cell_name, cell_value)
        if self.__extra_names__:
            locals.update(self.__extra_names__)
        arg = self.__forward_arg__
        if arg.isidentifier():
            if not keyword.iskeyword(arg):
                if arg in locals:
                    return locals[arg]
                if arg in globals:
                    return globals[arg]
                if hasattr(builtins, arg):
                    return getattr(builtins, arg)
                if is_forwardref_format:
                    return self
                raise NameError(_NAME_ERROR_MSG.format(name=arg), arg)
        code = self.__forward_code__
        try:
            pass
        except Exception:
            if not is_forwardref_format:
                raise
        return eval(code, globals, locals)

    def _evaluate(self, globalns, localns, type_params=_sentinel, *, recursive_guard):
        import typing
        import warnings
        if type_params is _sentinel:
            typing._deprecation_warning_for_no_type_params_passed('typing.ForwardRef._evaluate')
            type_params = ()
        warnings._deprecated('ForwardRef._evaluate', '{name} is a private API and is retained for compatibility, but will be removed in Python 3.16. Use ForwardRef.evaluate() or typing.evaluate_forward_ref() instead.', (3, 16))
        return typing.evaluate_forward_ref(self, globalns, localns, type_params, recursive_guard)

    @property
    def __forward_arg__(self):
        if not self.__arg__ is None:
            return self.__arg__
        if not self.__ast_node__ is None:
            self.__arg__ = ast.unparse(self.__ast_node__)
            return self.__arg__
        raise AssertionError("Attempted to access '__forward_arg__' on an uninitialized ForwardRef")

    @property
    def __resolved_str__(self):
        if not self.__resolved_str_cache__ is not None:
            resolved_str = self.__forward_arg__
            names = self.__extra_names__
            if names:
                visitor = _ExtraNameFixer(names)
                ast_expr = ast.parse(resolved_str, 'eval').body
                node = visitor.visit(ast_expr)
                resolved_str = ast.unparse(node)
            self.__resolved_str_cache__ = resolved_str
        return self.__resolved_str_cache__

    @property
    def __forward_code__(self):
        if not self.__code__ is None:
            return self.__code__
        arg = self.__forward_arg__
        try:
            self.__code__ = compile(_rewrite_star_unpack(arg), '<string>', 'eval')
        except SyntaxError:
            raise SyntaxError(f'Forward reference must be an expression -- got {arg!r}')
        return self.__code__

    def __eq__(self, other):
        if not isinstance(other, ForwardRef):
            return NotImplemented
        return self.__forward_arg__ == other.__forward_arg__ and self.__forward_module__ == other.__forward_module__ and self.__globals__ is other.__globals__ and self.__forward_is_class__ == other.__forward_is_class__ and (name == cell if isinstance(self.__cell__, dict) and isinstance(other.__cell__, dict) else self.__cell__ is other.__cell__) and self.__owner__ == other.__owner__ and ((tuple(sorted(self.__extra_names__.items())) if self.__extra_names__ else None) if other.__extra_names__ else tuple(sorted(other.__extra_names__.items()))) == None

    def __hash__(self):
        if self.__extra_names__:
            return None((None, hash, self.__forward_arg__, self.__forward_module__ if isinstance(self.__cell__, dict) else id(self.__globals__)(tuple(name)), (id,), self.__owner__, tuple(sorted(self.__extra_names__.items()))))
        return None((None, None, None, None, None, None, None))

    def __or__(self, other):
        return types.UnionType[self, other]

    def __ror__(self, other):
        return types.UnionType[other, self]

    def __repr__(self):
        extra = []
        if not self.__forward_module__ is None:
            extra.append(f', module={self.__forward_module__!r}')
        if self.__forward_is_class__:
            extra.append(', is_class=True')
        if not self.__owner__ is None:
            extra.append(f', owner={self.__owner__!r}')
        return f'ForwardRef({self.__resolved_str__!r}{''.join(extra)})'


/* unknown opcode: BUILD_TEMPLATE  @154 */
_Template = type(())

class _Stringifier:
    __slots__ = _SLOTS
    def __init__(self, node, globals=None, owner=None, is_class=False, cell=None, *, stringifier_dict, extra_names=None):
        if not isinstance(node, (ast.AST, str)):
            raise None
        self.__arg__ = None
        self.__forward_is_argument__ = False
        self.__forward_is_class__ = is_class
        self.__forward_module__ = None
        self.__code__ = None
        self.__ast_node__ = node
        self.__globals__ = globals
        self.__extra_names__ = extra_names
        self.__cell__ = cell
        self.__owner__ = owner
        self.__stringifier_dict__ = stringifier_dict
        self.__resolved_str_cache__ = None

    def _Stringifier__convert_to_ast(self, other):
        if isinstance(other, _Stringifier):
            if isinstance(other.__ast_node__, str):
                return ast.Name(id=other.__ast_node__), other.__extra_names__
            return other.__ast_node__, other.__extra_names__
        if type(other) is _Template:
            return _template_to_ast(other), None
        if not self.__stringifier_dict__.format == Format.STRING or other is None:
            if type(other) in (str, int, float, bool, complex):
                return ast.Constant(value=other), None
        if type(other) is dict:
            extra_names = {}
            keys = []
            values = []
            for key, value in other.items():
                new_key, new_extra_names = self._Stringifier__convert_to_ast(key)
                if not new_extra_names is None:
                    extra_names.update(new_extra_names)
                keys.append(new_key)
                new_value, new_extra_names = self._Stringifier__convert_to_ast(value)
                if not new_extra_names is None:
                    extra_names.update(new_extra_names)
                values.append(new_value)
            return ast.Dict(keys, values), extra_names
        if type(other) in (list, tuple, set):
            extra_names = {}
            elts = []
            for elt in other:
                new_elt, new_extra_names = self._Stringifier__convert_to_ast(elt)
                if not new_extra_names is None:
                    extra_names.update(new_extra_names)
                elts.append(new_elt)
            ast_class = {list: ast.List, tuple: ast.Tuple, set: ast.Set}[type(other)]
            return ast_class(elts), extra_names
        name = self.__stringifier_dict__.create_unique_name()
        return ast.Name(id=name), {name: other}

    def _Stringifier__convert_to_ast_getitem(self, other):
        if isinstance(other, slice):
            extra_names = {}
            def conv(obj):
                if not obj is not None:
                    return
                new_obj, new_extra_names = self._Stringifier__convert_to_ast(obj)
                if not new_extra_names is None:
                    extra_names.update(new_extra_names)
                return new_obj

            return ast.Slice(lower=conv(other.start), upper=conv(other.stop), step=conv(other.step)), extra_names
        return self._Stringifier__convert_to_ast(other)

    def _Stringifier__get_ast(self):
        node = self.__ast_node__
        if isinstance(node, str):
            return ast.Name(id=node)
        return node

    def _Stringifier__make_new(self, node, extra_names=None):
        new_extra_names = {}
        if not self.__extra_names__ is None:
            new_extra_names.update(self.__extra_names__)
        if not extra_names is None:
            new_extra_names.update(extra_names)
        stringifier = _Stringifier(node, self.__globals__, self.__owner__, self.__forward_is_class__, self.__stringifier_dict__, new_extra_names or None)
        self.__stringifier_dict__.stringifiers.append(stringifier)
        return stringifier

    def __hash__(self):
        return id(self)

    def __getitem__(self, other):
        if self.__ast_node__ == '__classdict__':
            raise KeyError
        if isinstance(other, tuple):
            extra_names = {}
            elts = []
            for elt in other:
                new_elt, new_extra_names = self._Stringifier__convert_to_ast_getitem(elt)
                if not new_extra_names is None:
                    extra_names.update(new_extra_names)
                elts.append(new_elt)
            other = ast.Tuple(elts)
        else:
            other, extra_names = self._Stringifier__convert_to_ast_getitem(other)
        if not isinstance(other, ast.AST):
            raise None()
        return self._Stringifier__make_new(ast.Subscript(self._Stringifier__get_ast(), other), extra_names)

    def __getattr__(self, attr):
        return self._Stringifier__make_new(ast.Attribute(self._Stringifier__get_ast(), attr))

    def __call__(self, *args, **kwargs):
        extra_names = {}
        ast_args = []
        for arg in args:
            new_arg, new_extra_names = self._Stringifier__convert_to_ast(arg)
            if not new_extra_names is None:
                extra_names.update(new_extra_names)
            ast_args.append(new_arg)
        ast_kwargs = []
        for key, value in kwargs.items():
            new_value, new_extra_names = self._Stringifier__convert_to_ast(value)
            if not new_extra_names is None:
                extra_names.update(new_extra_names)
            ast_kwargs.append(ast.keyword(key, new_value))
        return self._Stringifier__make_new(ast.Call(self._Stringifier__get_ast(), ast_args, ast_kwargs), extra_names)

    def __iter__(self):
        yield self._Stringifier__make_new(ast.Starred(self._Stringifier__get_ast()))

    def __repr__(self):
        if isinstance(self.__ast_node__, str):
            return self.__ast_node__
        return ast.unparse(self.__ast_node__)

    def __format__(self, format_spec):
        raise TypeError('Cannot stringify annotation containing string formatting')

    def _make_binop(op: __classdict__.AST):
        def binop(self, other):
            rhs, extra_names = self._Stringifier__convert_to_ast(other)
            return self._Stringifier__make_new(ast.BinOp(self._Stringifier__get_ast(), op, rhs), extra_names)

        return binop

    __add__ = _make_binop(ast.Add())
    __sub__ = _make_binop(ast.Sub())
    __mul__ = _make_binop(ast.Mult())
    __matmul__ = _make_binop(ast.MatMult())
    __truediv__ = _make_binop(ast.Div())
    __mod__ = _make_binop(ast.Mod())
    __lshift__ = _make_binop(ast.LShift())
    __rshift__ = _make_binop(ast.RShift())
    __or__ = _make_binop(ast.BitOr())
    __xor__ = _make_binop(ast.BitXor())
    __and__ = _make_binop(ast.BitAnd())
    __floordiv__ = _make_binop(ast.FloorDiv())
    __pow__ = _make_binop(ast.Pow())
    del _make_binop
    def _make_rbinop(op: __classdict__.AST):
        def rbinop(self, other):
            new_other, extra_names = self._Stringifier__convert_to_ast(other)
            return self._Stringifier__make_new(ast.BinOp(new_other, op, self._Stringifier__get_ast()), extra_names)

        return rbinop

    __radd__ = _make_rbinop(ast.Add())
    __rsub__ = _make_rbinop(ast.Sub())
    __rmul__ = _make_rbinop(ast.Mult())
    __rmatmul__ = _make_rbinop(ast.MatMult())
    __rtruediv__ = _make_rbinop(ast.Div())
    __rmod__ = _make_rbinop(ast.Mod())
    __rlshift__ = _make_rbinop(ast.LShift())
    __rrshift__ = _make_rbinop(ast.RShift())
    __ror__ = _make_rbinop(ast.BitOr())
    __rxor__ = _make_rbinop(ast.BitXor())
    __rand__ = _make_rbinop(ast.BitAnd())
    __rfloordiv__ = _make_rbinop(ast.FloorDiv())
    __rpow__ = _make_rbinop(ast.Pow())
    del _make_rbinop
    def _make_compare(op):
        def compare(self, other):
            rhs, extra_names = self._Stringifier__convert_to_ast(other)
            return self._Stringifier__make_new(ast.Compare(left=self._Stringifier__get_ast(), ops=[op], comparators=[rhs]), extra_names)

        return compare

    __lt__ = _make_compare(ast.Lt())
    __le__ = _make_compare(ast.LtE())
    __eq__ = _make_compare(ast.Eq())
    __ne__ = _make_compare(ast.NotEq())
    __gt__ = _make_compare(ast.Gt())
    __ge__ = _make_compare(ast.GtE())
    del _make_compare
    def _make_unary_op(op):
        def unary_op(self):
            return self._Stringifier__make_new(ast.UnaryOp(op, self._Stringifier__get_ast()))

        return unary_op

    __invert__ = _make_unary_op(ast.Invert())
    __pos__ = _make_unary_op(ast.UAdd())
    __neg__ = _make_unary_op(ast.USub())
    del _make_unary_op

def _template_to_ast_constructor(template):
    args = []
    for part in template:
        /* match/case: MATCH_CLASS 0 @30 */
        if not () is None:
            args.append(ast.Constant(value=part))
            continue
        str
        interp = ast.Call(func=ast.Name(id='Interpolation'), args=[ast.Constant(value=part.value), ast.Constant(value=part.expression), ast.Constant(value=part.conversion), ast.Constant(value=part.format_spec)])
        args.append(interp)
    return ast.Call(func=ast.Name(id='Template'), args=args, keywords=[])

def _template_to_ast_literal(template, parsed):
    values = []
    interp_count = 0
    for part in template:
        /* match/case: MATCH_CLASS 0 @34 */
        if not () is None:
            values.append(ast.Constant(value=part))
            continue
        str
        interp = ast.Interpolation(str=part.expression, value=parsed[interp_count] if part.conversion else ord(part.conversion), conversion=-1 if part.format_spec else ast.Constant(value=part.format_spec), format_spec=None)
        values.append(interp)
        interp_count += 1
    return ast.TemplateStr(values=values)

def _template_to_ast(template):
    if any is None:
        for _ in (part.expression() == '' for part in template.interpolations):
            if not (part.expression() == '' for part in template.interpolations):
                continue
    if False((part.expression() == '' for part in template.interpolations)):
        return _template_to_ast_constructor(template)
    try:
        if tuple is None:
            try:
                for _ in (('mode',).body for part in template.interpolations):
                    pass
                parsed = None((('mode',).body for part in template.interpolations))
            except SyntaxError:
                pass
    finally:
        return _template_to_ast_literal(template, parsed)

class _StringifierDict(dict):
    def __init__(self, namespace, *, globals=None, owner=None, is_class=False, format):
        None(namespace)
        self.namespace = namespace
        self.globals = globals
        self.owner = owner
        self.is_class = is_class
        self.stringifiers = []
        self.next_id = 1
        self.format = format

    def __missing__(self, key):
        fwdref = _Stringifier(key, self.globals, self.owner, self.is_class, self)
        self.stringifiers.append(fwdref)
        return fwdref

    def transmogrify(self, cell_dict):
        for obj in self.stringifiers:
            obj.__class__ = ForwardRef
            obj.__stringifier_dict__ = None
            if isinstance(obj.__ast_node__, str):
                obj.__arg__ = obj.__ast_node__
                obj.__ast_node__ = None
            if not cell_dict is not None:
                continue
            if not obj.__cell__ is None:
                continue
            obj.__cell__ = cell_dict

    def create_unique_name(self):
        name = f'__annotationlib_name_{self.next_id}__'
        self.next_id += 1
        return name


def call_evaluate_function(evaluate, format, *, owner=None):
    return call_annotate_function(evaluate, format, owner, True)

def call_annotate_function(annotate, format, *, owner=None, _is_evaluate=False):
    if format == Format.VALUE_WITH_FAKE_GLOBALS:
        raise ValueError('The VALUE_WITH_FAKE_GLOBALS format is for internal use only')
    try:
        pass
    except NotImplementedError:
        pass
    return annotate(format)

def _build_closure(annotate, owner, is_class, stringifier_dict, *, allow_evaluation):
    if not annotate.__closure__:
        return (None, None)
    new_closure = []
    cell_dict = {}
    for name, cell in zip(annotate.__code__.co_freevars, annotate.__closure__, True):
        cell_dict[name] = cell
        new_cell = None
        if allow_evaluation:
            try:
                cell.cell_contents
            except ValueError:
                pass
            new_cell = cell
        if not new_cell is not None:
            fwdref = _Stringifier(name, cell, owner, annotate.__globals__, is_class, stringifier_dict)
            stringifier_dict.stringifiers.append(fwdref)
            new_cell = types.CellType(fwdref)
        new_closure.append(new_cell)
    return tuple(new_closure), cell_dict

def _stringify_single(anno):
    if anno is ...:
        return '...'
    if isinstance(anno, str):
        return anno
    if isinstance(anno, _Template):
        return ast.unparse(_template_to_ast(anno))
    return repr(anno)

def get_annotate_from_class_namespace(obj):
    try:
        pass
    except KeyError:
        pass
    return obj['__annotate__']

def get_annotations(obj, *, globals=None, locals=None, eval_str=False, format=Format.VALUE):
    if eval_str and format != Format.VALUE:
        raise ValueError('eval_str=True is only supported with format=Format.VALUE')
    if format == Format.VALUE:
        ann = _get_dunder_annotations(obj)
        if not ann is not None:
            ann = _get_and_call_annotate(obj, format)
            if None == Format.FORWARDREF:
                try:
                    ann = _get_dunder_annotations(obj)
                except Exception:
                    pass
                if not ann is None:
                    return dict(ann)
                ann = _get_and_call_annotate(obj, format)
                if not ann is not None:
                    ann = _get_dunder_annotations(obj)
                    if None == Format.STRING:
                        ann = _get_and_call_annotate(obj, format)
                        if not ann is None:
                            return dict(ann)
                        ann = _get_dunder_annotations(obj)
                        if not ann is None:
                            return annotations_to_string(ann)
                            if None == Format.VALUE_WITH_FAKE_GLOBALS:
                                raise ValueError('The VALUE_WITH_FAKE_GLOBALS format is for internal use only')
                            raise ValueError(f'Unsupported format {format!r}')
    if not ann is not None:
        if not isinstance(obj, type):
            if callable(obj):
                return {}
        raise TypeError(f'{obj!r} does not have annotations')
    if not ann:
        return {}
    if not eval_str:
        return dict(ann)
    if not globals is None:
        if not locals is not None or locals is not None:
            if isinstance(obj, type):
                obj_globals = None
                module_name = getattr(obj, '__module__', None)
                if module_name and module:
                    module = sys.modules.get(module_name, None)
                    obj_globals = getattr(module, '__dict__', None)
                obj_locals = dict(vars(obj))
                unwrap = obj
            elif isinstance(obj, types.ModuleType):
                obj_globals = getattr(obj, '__dict__')
                obj_locals = None
                unwrap = None
            elif callable(obj):
                obj_globals = getattr(obj, '__globals__', None)
                obj_locals = None
                unwrap = obj
            else:
                obj_globals = obj_locals = unwrap = None
            if not unwrap is None:
                _seen_ids = {id(unwrap)}
                if hasattr(unwrap, '__wrapped__'):
                    candidate = unwrap.__wrapped__
                    if id(candidate) in _seen_ids:
                        pass
                    else:
                        _seen_ids.add(id(candidate))
                        unwrap = candidate
                if sys.modules.get('functools') and isinstance(unwrap, functools.partial):
                    functools = sys.modules.get('functools')
                    candidate = unwrap.func
                    if id(candidate) in _seen_ids:
                        pass
                    else:
                        _seen_ids.add(id(candidate))
                        unwrap = candidate
                if hasattr(unwrap, '__globals__'):
                    obj_globals = unwrap.__globals__
            if not globals is not None:
                globals = obj_globals
            locals = obj_locals
    if getattr(obj, '__type_params__', ()):
        type_params = getattr(obj, '__type_params__', ())
        if not locals is not None:
            locals = {}
        locals = {param.__name__: param for param in type_params} | locals
    return return_value

def type_repr(value):
    if isinstance(value, (type, types.FunctionType, types.BuiltinFunctionType)):
        if value.__module__ == 'builtins':
            return value.__qualname__
        return f'{value.__module__}.{value.__qualname__}'
    if isinstance(value, _Template):
        tree = _template_to_ast(value)
        return ast.unparse(tree)
    if value is ...:
        return '...'
    return repr(value)

def annotations_to_string(annotations):
    return n

def _rewrite_star_unpack(arg):
    if arg.lstrip().startswith('*'):
        return f'({arg},)[0]'
    return arg

def _get_and_call_annotate(obj, format):
    annotate = getattr(obj, '__annotate__', None)
    if not annotate is None:
        ann = call_annotate_function(annotate, format, obj)
        if not isinstance(ann, dict):
            raise ValueError(f'{obj!r}.__annotate__ returned a non-dict')
        return ann

_BASE_GET_ANNOTATIONS = type.__dict__['__annotations__'].__get__

def _get_dunder_annotations(obj):
    if isinstance(obj, type):
        try:
            ann = _BASE_GET_ANNOTATIONS(obj)
        except AttributeError:
            pass
    ann = getattr(obj, '__annotations__', None)
    if not ann is not None:
        return
    if not isinstance(ann, dict):
        raise ValueError(f'{obj!r}.__annotations__ is neither a dict nor None')
    return ann

class _ExtraNameFixer(ast.NodeTransformer):
    '''Fixer for __extra_names__ items in ForwardRef __repr__ and string evaluation'''

    def __init__(self, extra_names):
        self.extra_names = extra_names

    def visit_Name(self, node: __classdict__.Name):
        new_name = self.extra_names.get(node.id, _sentinel)
        if self.extra_names.get(node.id, _sentinel) is not _sentinel:
            node = ast.Name(id=type_repr(new_name))
        return node


# WARNING: Decompyle incomplete

# MIN_VERSION: 3.14
def plain(value, bad, ready, make_error):
    if value is None or bad(value) or not ready(value):
        raise make_error("invalid", value=value)
    return value


def chained(value, read, invalid, make_error):
    if value is None or not 0 <= read(value) <= 10 or invalid(value):
        raise make_error("range failed")
    return value


def cause(value, reject, make_error, make_cause):
    if value is None or reject(value):
        raise make_error("invalid", value=value) from make_cause(value)
    return value


def suppress(value, reject, make_error):
    if value is None or reject(value):
        raise make_error("invalid", value=value) from None
    return value


def formatted(value, label, width, read, reject, make_error, make_cause):
    if value is None or not 0 <= read(value) <= 10 or reject(value):
        raise make_error(f"{label!r}: {value!s:>{width}}") from make_cause()
    return value


def ascii_spec(value, label, width, read, reject, make_error, make_cause):
    if value is None or not 0 <= read(value) <= 10 or reject(value):
        raise make_error(f"{label!a}: {value:{width}}") from make_cause()
    return value


def formatted_plain(value, label, width, read, reject, make_error):
    if value is None or not 0 <= read(value) <= 10 or reject(value):
        raise make_error(f"{label!r}: {value!s:>{width}}")
    return value


def constant_error(value, reject):
    if value is None or reject(value):
        raise ValueError
    return value

# Run the observation driver unchanged.
exec("""
from itertools import product

def outcome(function, *args):
    try:
        # Retain an active exception to check implicit context and suppression.
        try:
            raise LookupError('outer context')
        except LookupError:
            value = function(*args)
            return ('value', 'original object' if value is args[0] else value)
    except Exception as error:
        cause = error.__cause__
        context = error.__context__
        return (type(error).__name__, str(error),
                None if cause is None else (type(cause).__name__, str(cause)),
                None if context is None else (type(context).__name__, str(context)),
                error.__suppress_context__)

trace = []
for value, bad_value, ready_value, failure in product((None, 0, 7), (False, True), (False, True), ('', 'bad', 'ready', 'constructor')):
    trace.clear()
    def bad(item):
        trace.append(('bad', item))
        if failure == 'bad': raise KeyError('bad failed')
        return bad_value
    def ready(item):
        trace.append(('ready', item))
        if failure == 'ready': raise KeyError('ready failed')
        return ready_value
    def make_error(message, **keywords):
        trace.append(('error', message, keywords))
        if failure == 'constructor': raise TypeError('constructor failed')
        return ValueError(message)
    print('plain', value, bad_value, ready_value, failure, outcome(plain, value, bad, ready, make_error), trace)

for value, number, invalid_value, failure in product((None, 'value'), (-1, 0, 5, 10, 11, float('nan')), (False, True), ('', 'read', 'ge', 'le', 'invalid')):
    trace.clear()
    class Number:
        def __ge__(self, other):
            trace.append(('ge', other))
            if failure == 'ge': raise TypeError('ge failed')
            return number >= other
        def __le__(self, other):
            trace.append(('le', other))
            if failure == 'le': raise TypeError('le failed')
            return number <= other
        def __lt__(self, other): raise AssertionError('inverted comparison')
        def __gt__(self, other): raise AssertionError('inverted comparison')
    def read(item):
        trace.append(('read', item))
        if failure == 'read': raise TypeError('read failed')
        return Number()
    def invalid(item):
        trace.append(('invalid', item))
        if failure == 'invalid': raise TypeError('invalid failed')
        return invalid_value
    def make_error(message):
        trace.append(('error', message))
        return ValueError(message)
    print('chain', value, repr(number), invalid_value, failure, outcome(chained, value, read, invalid, make_error), trace)

for function, value, rejects, cause_mode in product((cause, suppress, constant_error), (None, 0, 7), (False, True), ('none', 'exception', 'class', 'invalid', 'failure')):
    trace.clear()
    def reject(item):
        trace.append(('reject', item)); return rejects
    def make_error(message, **keywords):
        trace.append(('error', message, keywords)); return ValueError(message)
    def make_cause(item):
        trace.append(('cause', item))
        if cause_mode == 'failure': raise KeyError('cause factory failed')
        if cause_mode == 'invalid': return 'invalid cause'
        if cause_mode == 'class': return RuntimeError
        return RuntimeError('original cause') if cause_mode == 'exception' else None
    args = (value, reject)
    if function is not constant_error: args += (make_error,)
    if function is cause: args += (make_cause,)
    print(function.__name__, value, rejects, cause_mode, outcome(function, *args), trace)

for function, number, rejects, failure in product((formatted, ascii_spec, formatted_plain), (None, 5, 11), (False, True), ('', 'repr', 'str', 'format', 'width', 'constructor', 'cause')):
    trace.clear()
    class Label:
        def __repr__(self):
            trace.append('repr')
            if failure == 'repr': raise TypeError('repr failed')
            return 'label-α'
    class Value:
        def __str__(self):
            trace.append('str')
            if failure == 'str': raise TypeError('str failed')
            return 'value'
        def __format__(self, spec):
            trace.append(('format', spec))
            if failure == 'format': raise TypeError('format failed')
            return 'formatted-' + spec
    class Width:
        def __format__(self, spec):
            trace.append(('width', spec))
            if failure == 'width': raise TypeError('width failed')
            return '6'
    def read(value):
        trace.append('read'); return number
    def reject(value):
        trace.append('reject'); return rejects
    def make_error(message):
        trace.append(('error', message))
        if failure == 'constructor': raise ValueError('constructor failed')
        return ValueError(message)
    def make_cause():
        trace.append('cause')
        if failure == 'cause': raise KeyError('cause failed')
        return RuntimeError('cause')
    value = None if number is None else Value()
    args = (value, Label(), Width(), read, reject, make_error)
    if function is not formatted_plain: args += (make_cause,)
    print(function.__name__, number, rejects, failure, outcome(function, *args), trace)
""")

# MIN_VERSION: 3.14
def constructed(value, build):
    if value is None or not 0.0 <= value <= 20.0:
        return build("reject", amount=0)
    return build("accept", amount=value)


def truth_guard(value, build):
    if not value or len(value) < 2:
        return build("reject", amount=0)
    return build("accept", amount=len(value))


def positive_guard(value, invalid, build):
    if invalid(value) or value < 2:
        return build("reject", amount=value)
    return build("accept", amount=value)


def constant_truth(value):
    if not value or len(value) < 2:
        return False
    return True


def list_result(value):
    if value is None or not 0.0 <= value <= 20.0:
        return ["reject", value]
    return ["accept", value]


def mapping_result(value):
    if value is None or not 0.0 <= value <= 20.0:
        return {"kind": "reject", "value": value}
    return {"kind": "accept", "value": value}


def generator_result(value, rows, collect, scale):
    if value is None or not 0.0 <= value <= 20.0:
        return collect(scale * item for item in rows)
    return collect(rows)


def stored_result(value, build):
    if not value or len(value) < 2:
        result = build("reject", amount=0)
        return result
    return build("accept", amount=len(value))


def effectful_body(value, build, log):
    if not value or len(value) < 2:
        log("rejected")
        return build("reject", amount=0)
    return build("accept", amount=len(value))

# Run the observation driver unchanged.
exec("""
trace = []
fail = None
def build(kind, **options):
    trace.append(('build', kind, options))
    if fail == 'build': raise RuntimeError('build')
    return kind, options

def log(message):
    trace.append(('log', message))
    if fail == 'log': raise RuntimeError('log')

def outcome(function, *args):
    try: return 'return', function(*args)
    except Exception as error: return 'raise', type(error).__name__, str(error)

class Values:
    def __init__(self, count): self.count = count
    def __bool__(self):
        trace.append('bool')
        if fail == 'bool': raise ValueError('bool')
        return self.count != 0
    def __len__(self):
        trace.append('len')
        if fail == 'len': raise ValueError('len')
        return self.count

for function in (constructed, list_result, mapping_result):
    for value in (None, -1.0, 0.0, 10.0, 20.0, 21.0, float('nan')):
        for fail in (None, 'build'):
            trace.clear()
            args = (value, build) if function is constructed else (value,)
            print(function.__name__, repr(value), fail, outcome(function, *args), trace)
for function in (truth_guard, constant_truth, stored_result, effectful_body):
    for count in (0, 1, 2, 3):
        for fail in (None, 'bool', 'len', 'build', 'log'):
            trace.clear()
            args = (Values(count),)
            if function is not constant_truth: args += (build,)
            if function is effectful_body: args += (log,)
            print(function.__name__, count, fail, outcome(function, *args), trace)
for invalid_result in (False, True):
    for value in (0, 2, 3):
        for fail in (None, 'invalid', 'build'):
            trace.clear()
            def invalid(value):
                trace.append(('invalid', value))
                if fail == 'invalid': raise RuntimeError('invalid')
                return invalid_result
            print('positive', invalid_result, value, fail, outcome(positive_guard, value, invalid, build), trace)
class Rows:
    def __iter__(self):
        trace.append('iter')
        if fail == 'iter': raise RuntimeError('iter')
        for value in (2, 3):
            trace.append(('next', value))
            yield value
        trace.append('exhausted')
def collect(values):
    trace.append('collect')
    if fail == 'collect': raise RuntimeError('collect')
    return list(values)
for value in (None, -1.0, 0.0, 20.0, 21.0, float('nan')):
    for fail in (None, 'iter', 'collect'):
        trace.clear()
        print('generator', repr(value), fail, outcome(generator_result, value, Rows(), collect, 10), trace)
""")

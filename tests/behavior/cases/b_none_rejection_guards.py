# MIN_VERSION: 3.14
def in_range(value):
    if value is None or not 0.0 <= value <= 15.0:
        return False
    return True


def called(read):
    if read is None or not 0.0 <= read() <= 15.0:
        return False
    return True


def multi(first, second):
    if first is None or not 0.0 <= first() <= second() <= 15.0:
        return False
    return True


def separate(read):
    if read is None or not (0.0 <= read() and read() <= 15.0):
        return False
    return True


def same_tail(value):
    if value is None or not 0.0 <= value <= 15.0:
        return False
    return False


def integer_tail(value):
    if value is None or not 0.0 <= value <= 15.0:
        return 3
    return 5


def string_tail(value):
    if value is None or not 0.0 <= value <= 15.0:
        return "reject"
    return "accept"


def collect(rows):
    result = []
    for row in rows:
        a = row.get("a")
        b = row.get("b")
        c = row.get("c")
        d = row.get("d")
        if a is None or b is None or c is None or d is None or d < 0.01:
            continue
        result.append(a + b + c + d)
    return result


def unpacked(rows):
    result = []
    for a, b, c, d in rows:
        if a is None or b is None or c is None or d is None or d < 0.01:
            continue
        result.append(a + b + c + d)
    return result

# Keep the driver out of the source being reconstructed.
exec("trace = []\ndef outcome(function, *args):\n    try:\n        return ('return', function(*args))\n    except Exception as error:\n        return ('raise', type(error).__name__, str(error))\n\nclass Number:\n    def __init__(self, label, value, fail=None):\n        self.label, self.value, self.fail = label, value, fail\n    def compare(self, op, other):\n        trace.append((self.label, op, getattr(other, 'label', other)))\n        if self.fail == op:\n            raise RuntimeError(self.label + ':' + op)\n        other = getattr(other, 'value', other)\n        return self.value <= other if op == 'le' else self.value >= other\n    def __le__(self, other): return self.compare('le', other)\n    def __ge__(self, other): return self.compare('ge', other)\n    def __lt__(self, other): raise AssertionError('rewritten lt')\n    def __gt__(self, other): raise AssertionError('rewritten gt')\n    def __bool__(self): raise AssertionError('unexpected truth conversion')\n\ndef reader(label, values):\n    pending = iter(values)\n    def read():\n        trace.append(label)\n        result = next(pending)\n        if isinstance(result, Exception): raise result\n        return result\n    return read\n\nfor function in (in_range, same_tail, integer_tail, string_tail):\n    for value in (None, -1.0, 0.0, 10.0, 15.0, 16.0, float('nan'), float('inf')):\n        print(function.__name__, repr(value), outcome(function, value))\n    for value in (-1.0, 3.0, 17.0, float('nan')):\n        for fail in (None, 'ge', 'le'):\n            trace.clear()\n            result = outcome(function, Number('value', value, fail))\n            print(function.__name__, repr(value), fail, result, trace)\nfor function in (called, separate):\n    print(function.__name__, 'none', outcome(function, None))\n    for values in ((1.0, 16.0), (-1.0, 5.0), (float('nan'), 2.0), (2.0, float('nan')), (ValueError('first'),), (2.0, ValueError('second'))):\n        trace.clear()\n        result = outcome(function, reader('read', values))\n        print(function.__name__, repr(values), result, trace)\nfor a, b in ((1.0, 2.0), (-1.0, 2.0), (3.0, 2.0), (2.0, 16.0), (float('nan'), 2.0), (2.0, float('nan')), (ValueError('first'), 2.0), (2.0, ValueError('second'))):\n    trace.clear()\n    result = outcome(multi, reader('first', (a,)), reader('second', (b,)))\n    print('multi', repr((a,b)), result, trace)\ntrace.clear()\nprint('multi-none', outcome(multi, None, reader('unused', (1,))), trace)\nclass Row(dict):\n    def get(self, key):\n        trace.append(key)\n        return super().get(key)\nrows = [(1,2,3,4), (1,2,3,0), (None,2,3,4), (1,None,3,4), (1,2,None,4), (1,2,3,None), (4,5,6,7)]\nfor values in ([], rows, rows[::-1]):\n    trace.clear()\n    mapped = [Row(zip('abcd', value)) for value in values]\n    print('collect', outcome(collect, mapped), trace)\n    print('unpacked', outcome(unpacked, values))\n")

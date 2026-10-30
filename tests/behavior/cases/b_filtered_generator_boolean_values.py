# MIN_VERSION: 3.12
# The modern statement route preserves filters and yielded Boolean values.

def or_value(rows):
    return tuple(row[1] or 0 for row in rows if row[0])


def and_value(rows):
    return tuple(row[1] and row[2] for row in rows if row[0])


def chained_or(rows):
    return tuple(row[1] or row[2] or 0 for row in rows if row[0])


def mixed_value(rows):
    return tuple((row[1] and row[2]) or 0 for row in rows if row[0])


def none_filter(rows):
    return tuple(row.get("amount") or 0.0 for row in rows if row.get("amount") is not None)


for rows in ([], [(False, 3, 4)], [(True, 0, 2)],
             [(True, 2, 3), (True, None, 4), (False, 5, 6)],
             [(True, "", 7), (True, "kept", 8)]):
    for function in (or_value, and_value, chained_or, mixed_value):
        print(function.__name__, function(rows))


events = []


class Value:
    def __init__(self, tag, truth):
        self.tag = tag
        self.truth = truth

    def __bool__(self):
        events.append(("bool", self.tag))
        return self.truth


class Row:
    def __init__(self, tag, value):
        self.tag = tag
        self.value = value

    def get(self, key):
        events.append(("get", self.tag, key))
        return self.value


rows = [Row("missing", None), Row("zero", 0), Row("false", Value("false", False)),
        Row("true", Value("true", True))]
result = []
for value in none_filter(rows):
    result.append(value.tag if isinstance(value, Value) else value)
print(result)
print(events)

# MIN_VERSION: 3.12
# This case exercises the inline-comprehension reconstruction path.

def mapping_value(values):
    return {value: 1 if 6 <= value <= 8 else 0 for value in values}


def mapping_key(values):
    return {(value if 6 <= value <= 8 else -value): value for value in values}


def arithmetic(values):
    return [0.6 + 0.4 * (1.0 if 4 <= value <= 8 < 10 else 0.3) for value in values]


def filtered(values):
    return [1 if value >= 6 else 0 for value in values if value <= 8]


def observed(values, base, coefficient, lower, probe, upper):
    return {value: base(value) + coefficient(value) * (1.0 if lower() <= probe(value) <= upper() else 0.3) for value in values}


for values in ([], list(range(24)), [0, 6, 8, 9, float("inf")]):
    for function in (mapping_value, mapping_key, arithmetic, filtered):
        print(function.__name__, function(values))

for failure in (None, "base", "coefficient", "lower", "probe", "upper"):
    events = []

    def record(label, value=None):
        events.append((label, value))
        if label == failure:
            raise ValueError("owned " + label)
        return {"base": 0.6, "coefficient": 0.4, "lower": 4, "upper": 8, "probe": value}[label]

    def base(value):
        return record("base", value)

    def coefficient(value):
        return record("coefficient", value)

    def lower():
        return record("lower")

    def probe(value):
        return record("probe", value)

    def upper():
        return record("upper")

    try:
        print(failure, observed(range(10), base, coefficient, lower, probe, upper))
    except ValueError as error:
        print(failure, str(error))
    print(events)

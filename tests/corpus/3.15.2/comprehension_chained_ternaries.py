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

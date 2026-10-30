def simple(value):
    return f"{value}"


def conversions(label, value, width):
    return f"{label!r}: {value!s:>{width}}"


def ascii_spec(label, value, width):
    return f"{label!a}: {value:{width}}"

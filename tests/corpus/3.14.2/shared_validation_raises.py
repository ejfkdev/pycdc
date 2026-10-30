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

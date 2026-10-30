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

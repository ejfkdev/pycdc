# A computed return can be outside the protected range but still use its value.


def call_return(value, make, fallback, default):
    if value:
        try:
            return make(value)
        except Exception:
            pass
    return fallback.read().result or default.result


def attribute_return(value, make, fallback, default):
    if value:
        try:
            return make(value).result
        except Exception:
            pass
    return fallback.read().result or default.result


def tuple_return(value, make, fallback, default):
    if value:
        try:
            return (make(value), 7)
        except Exception:
            pass
    return fallback.read().result or default.result


def mapping_return(value, make, fallback, default):
    if value:
        try:
            return {"value": make(value)}
        except Exception:
            pass
    return fallback.read().result or default.result


def bare_return(value, make, fallback, default):
    if value:
        try:
            make(value)
            return None
        except Exception:
            return "handled"
    return fallback.read().result or default.result

# MIN_VERSION: 3.11
from types import SimpleNamespace

# A computed return can be outside the protected range but still use its value.


def call_return(value, make, fallback, default):
    try:
        return make(value)
    except Exception:
        pass
    return fallback.read().result or default.result


def attribute_return(value, make, fallback, default):
    try:
        return make(value).result
    except Exception:
        pass
    return fallback.read().result or default.result


def tuple_return(value, make, fallback, default):
    try:
        return (make(value), 7)
    except Exception:
        pass
    return fallback.read().result or default.result


def mapping_return(value, make, fallback, default):
    try:
        return {"value": make(value)}
    except Exception:
        pass
    return fallback.read().result or default.result


def bare_return(value, make, fallback, default):
    try:
        make(value)
        return None
    except Exception:
        return "handled"
    return fallback.read().result or default.result

for function in (call_return, attribute_return, tuple_return, mapping_return, bare_return):
    for truth in (False, True):
        for result in (None, 0, "success"):
            for failure in ("", "truth", "attribute", "make", "base", "fallback"):
                events = []

                class Value:
                    def __bool__(self):
                        events.append("truth")
                        if failure == "truth":
                            raise ValueError("truth failed")
                        return truth

                class Result:
                    @property
                    def result(self):
                        events.append("attribute")
                        if failure == "attribute":
                            raise AttributeError("attribute failed")
                        return result

                class Fallback:
                    def read(self):
                        events.append("fallback")
                        if failure == "fallback":
                            raise RuntimeError("fallback failed")
                        return SimpleNamespace(result="fallback-result")

                def make(value):
                    events.append("make")
                    if failure == "make":
                        raise KeyError("make failed")
                    if failure == "base":
                        raise KeyboardInterrupt("owned interrupt")
                    return Result() if function is attribute_return else result

                try:
                    outcome = function(Value(), make, Fallback(), SimpleNamespace(result="default"))
                    print(function.__name__, truth, result, failure, outcome, events)
                except BaseException as error:
                    print(function.__name__, truth, result, failure, type(error).__name__, str(error), events)

# MIN_VERSION: 3.10

def call_only(values, test):
    result = []
    for value in values:
        if not test(value) or value < 0.2:
            result.append("dry")
    return result


def call_else(values, test):
    result = []
    for value in values:
        if not test(value) or value < 0.2:
            result.append("dry")
        else:
            result.append("wet")
    return result


def truth_only(values, test):
    result = []
    for value in values:
        if not value or value < 0.2:
            result.append("dry")
    return result


def truth_else(values, test):
    result = []
    for value in values:
        if not value or value < 0.2:
            result.append("dry")
        else:
            result.append("wet")
    return result


def none_only(values, test):
    result = []
    for value in values:
        if value is None or value < 0.2:
            result.append("dry")
    return result


def none_else(values, test):
    result = []
    for value in values:
        if value is None or value < 0.2:
            result.append("dry")
        else:
            result.append("wet")
    return result


def positive_only(values, test):
    result = []
    for value in values:
        if test(value) or value < 0.2:
            result.append("dry")
    return result


def positive_else(values, test):
    result = []
    for value in values:
        if test(value) or value < 0.2:
            result.append("dry")
        else:
            result.append("wet")
    return result


def rotated_while(values, test):
    result = []
    value = len(values)
    while value < 2 or value == 3:
        result.append(value)
        value += 2
    return result


def break_loop(values, test):
    result = []
    for value in values:
        if not test(value) or value < 0.2:
            break
        else:
            result.append(value)
    else:
        result.append('complete')
    result.append('tail')
    return result


def continue_loop(values, test):
    result = []
    for value in values:
        if not test(value) or value < 0.2:
            continue
        result.append(value)
    return result


def extended_loop(values, test):
    result = []
    for value in values:
        if not test(value) or value < 0.2:
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
            result.append("dry")
        else:
            result.append("wet")
    return result


for function in (
    call_only, call_else, truth_only, truth_else, none_only, none_else,
    positive_only, positive_else, rotated_while, break_loop, continue_loop,
    extended_loop,
):
    for values in ([], [0.1, 0.3, 0.1], [None, 0.1, 0.3], ["dry", 0.3]):
        events = []

        def test(value):
            events.append(value)
            return isinstance(value, (int, float))

        try:
            result = ("return", function(values, test))
        except TypeError as error:
            result = ("error", type(error).__name__)
        print(function.__name__, result, events)

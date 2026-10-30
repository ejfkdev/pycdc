def plain(values):
    return collect(value for value in values)


def captured(values, offset):
    return collect(value + offset for value in values)


def multiple(values, first, second):
    return collect((value + first) * second for value in values)


def ordinary_function(values):
    return (lambda value: value)(values)

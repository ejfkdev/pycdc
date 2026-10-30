# MIN_VERSION: 3.13

collect = tuple

def plain(values):
    return collect(value for value in values)


def captured(values, offset):
    return collect(value + offset for value in values)


def multiple(values, first, second):
    return collect((value + first) * second for value in values)


def ordinary_function(values):
    return (lambda value: value)(values)


for values in ([], [1, 2, 3], ["x"]):
    for function, args in ((plain, (values,)), (captured, (values, 5)),
                           (multiple, (values, 5, 3))):
        try:
            print(function.__name__, function(*args))
        except TypeError as error:
            print(function.__name__, type(error).__name__)


def values():
    print("outer")
    for value in (1, 2):
        print("yield", value)
        yield value


print(captured(values(), 5))
print(ordinary_function("unchanged"))

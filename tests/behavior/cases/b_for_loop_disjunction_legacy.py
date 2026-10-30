# MIN_VERSION: 3.8
# MAX_VERSION: 3.9


def select(values, test):
    result = []
    for value in values:
        if not test(value) or value < 0.2:
            result.append("dry")
        else:
            result.append("wet")
    return result


for values in ([], [0.1, 0.3, 0.1], [None, 0.1, 0.3], ["dry", 0.3]):
    events = []

    def test(value):
        events.append(value)
        return isinstance(value, (int, float))

    print(select(values, test), events)

# MIN_VERSION: 3.12
# Exercise the modern generator statement-parser route.

def repeated_targets(values):
    return tuple(value is not None for value, discarded, discarded, discarded in values)


def real_underscore(values):
    return tuple((value, discarded, _) for value, _, discarded, discarded in values)


def nested_calls(rows):
    return sorted(sum(value for value in row) / len(row) for row in rows)


def captured_cells(rows):
    deltas = rows
    factory = sum
    return sorted(sum(factory(deltas) for _ in deltas) / len(deltas) for _ in range(3))


for values in ([], [(None, 1, 2, 3)], [(1, 2, 3, 4), (None, 5, 6, 7)], [(1, 2)], [None]):
    for function in (repeated_targets, real_underscore):
        try:
            print(function.__name__, function(values))
        except (TypeError, ValueError) as error:
            print(function.__name__, type(error).__name__, str(error))

for rows in ([], [[1, 2, 3], [5, 9], [3]]):
    print(nested_calls(rows))
print(captured_cells([1, 2, 4]))


def observed_rows():
    print("outer called")
    for value in (1, None, 3):
        print("yield", value)
        yield (value, 1, 2, 3)


print(repeated_targets(observed_rows()))

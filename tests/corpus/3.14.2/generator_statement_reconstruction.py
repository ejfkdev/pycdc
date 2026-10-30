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

def in_range(value):
    if value is None or not 0.0 <= value <= 15.0:
        return False
    return True


def called(read):
    if read is None or not 0.0 <= read() <= 15.0:
        return False
    return True


def multi(first, second):
    if first is None or not 0.0 <= first() <= second() <= 15.0:
        return False
    return True


def separate(read):
    if read is None or not (0.0 <= read() and read() <= 15.0):
        return False
    return True


def same_tail(value):
    if value is None or not 0.0 <= value <= 15.0:
        return False
    return False


def integer_tail(value):
    if value is None or not 0.0 <= value <= 15.0:
        return 3
    return 5


def string_tail(value):
    if value is None or not 0.0 <= value <= 15.0:
        return "reject"
    return "accept"


def collect(rows):
    result = []
    for row in rows:
        a = row.get("a")
        b = row.get("b")
        c = row.get("c")
        d = row.get("d")
        if a is None or b is None or c is None or d is None or d < 0.01:
            continue
        result.append(a + b + c + d)
    return result


def unpacked(rows):
    result = []
    for a, b, c, d in rows:
        if a is None or b is None or c is None or d is None or d < 0.01:
            continue
        result.append(a + b + c + d)
    return result

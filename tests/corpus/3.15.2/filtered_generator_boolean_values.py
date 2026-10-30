def or_value(rows):
    return tuple(row[1] or 0 for row in rows if row[0])


def and_value(rows):
    return tuple(row[1] and row[2] for row in rows if row[0])


def chained_or(rows):
    return tuple(row[1] or row[2] or 0 for row in rows if row[0])


def mixed_value(rows):
    return tuple((row[1] and row[2]) or 0 for row in rows if row[0])


def none_filter(rows):
    return tuple(row.get("amount") or 0.0 for row in rows if row.get("amount") is not None)

def select(rows):
    return tuple(isinstance(row, dict) and (change := row.get("change")) is not None and change >= 0 for row in rows)


def last_binding(rows):
    change = "initial"
    results = tuple((change := row.get("change")) for row in rows)
    return results, change

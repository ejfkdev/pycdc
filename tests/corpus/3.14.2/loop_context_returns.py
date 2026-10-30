def sync_value(lock, rows, parse):
    with lock:
        result = []
        for row in rows:
            try:
                result.append(parse(row))
            except ValueError:
                continue
        return result


def sync_length(lock, rows, parse):
    with lock:
        result = []
        for row in rows:
            try:
                result.append(parse(row))
            except ValueError:
                continue
        return len(result)


def sync_mapping(lock, rows, parse):
    with lock:
        result = []
        for row in rows:
            try:
                result.append(parse(row))
            except ValueError:
                continue
        return {"rows": result}


async def async_value(lock, rows, parse):
    async with lock:
        result = []
        for row in rows:
            try:
                result.append(parse(row))
            except ValueError:
                continue
        return result


async def async_length(lock, rows, parse):
    async with lock:
        result = []
        for row in rows:
            try:
                result.append(parse(row))
            except ValueError:
                continue
        return len(result)


async def async_mapping(lock, rows, parse):
    async with lock:
        result = []
        for row in rows:
            try:
                result.append(parse(row))
            except ValueError:
                continue
        return {"rows": result}

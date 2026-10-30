# MIN_VERSION: 3.9
import asyncio

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


events = []

class Lock:
    def __enter__(self):
        events.append("enter")
        if mode == "open_error":
            raise RuntimeError("enter")
        return self

    def __exit__(self, kind, value, traceback):
        events.append(("exit", kind.__name__ if kind else None))
        if mode == "exit_error":
            raise RuntimeError("exit")
        return mode == "suppressed"

    async def __aenter__(self):
        await asyncio.sleep(0)
        return self.__enter__()

    async def __aexit__(self, kind, value, traceback):
        await asyncio.sleep(0)
        return self.__exit__(kind, value, traceback)


def parse(value):
    events.append(("parse", value))
    if mode == "rejected" and value <= 1:
        raise ValueError("row")
    if mode in ("failed", "suppressed"):
        raise RuntimeError("body")
    if mode == "cancelled":
        raise asyncio.CancelledError("cancelled")
    return value * 2


for rows in ([], [1, 2], [-1, 0, 3]):
    for mode in ("normal", "rejected", "failed", "cancelled", "open_error", "exit_error", "suppressed"):
        for function in (sync_value, sync_length, sync_mapping, async_value, async_length, async_mapping):
            events.clear()
            print(function.__name__, rows, mode)
            try:
                result = function(Lock(), rows, parse)
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                print("return", result)
            except (RuntimeError, asyncio.CancelledError) as error:
                print(type(error).__name__, str(error))
            print(events)

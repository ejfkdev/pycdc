# MIN_VERSION: 3.14
import asyncio

async def false(lock, pending, release, user_call):
    async with lock:
        record("body")
        if pending:
            return False
    record("outside")
    return True


async def bare(lock, pending, release, user_call):
    async with lock:
        record("body")
        if pending:
            return
    record("outside")
    return True


async def twice(lock, pending, release, user_call):
    async with lock:
        record("body")
        if pending:
            return False
        if release:
            return False
    record("outside")
    return True


async def value(lock, pending, release, user_call):
    async with lock:
        record("body")
        if pending:
            return release
    record("outside")
    return True


async def user_await(lock, pending, release, user_call):
    async with lock:
        record("body")
        await user_call(None, None, None)
    record("outside")
    return True


async def normal(lock, pending, release, user_call):
    async with lock:
        record("body")
        record("ready")
    record("outside")
    return True


events = []

class Lock:
    async def __aenter__(self):
        await asyncio.sleep(0)
        events.append("enter")
        if mode == "enter_error":
            raise RuntimeError("enter")
        return self

    async def __aexit__(self, kind, value, traceback):
        await asyncio.sleep(0)
        events.append(("exit", kind.__name__ if kind else None))
        if mode == "exit_error":
            raise RuntimeError("exit")
        return mode == "suppressed"


def record(value):
    events.append(value)
    if value == "body" and mode in ("body_error", "suppressed"):
        raise ValueError("body")
    if value == "body" and mode == "cancelled":
        raise asyncio.CancelledError("cancelled")


async def user_call(*args):
    await asyncio.sleep(0)
    events.append(("user_call", args))
    if mode == "user_error":
        raise RuntimeError("user")


for pending, release in ((False, False), (True, False), (False, True), (True, True)):
    for mode in ("normal", "body_error", "suppressed", "cancelled", "enter_error", "exit_error", "user_error"):
        for function in (false, bare, twice, value, user_await, normal):
            events.clear()
            print(function.__name__, pending, release, mode)
            try:
                print("return", asyncio.run(function(Lock(), pending, release, user_call)))
            except (ValueError, RuntimeError, asyncio.CancelledError) as error:
                print(type(error).__name__, str(error))
            print(events)

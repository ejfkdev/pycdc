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

def synchronous(manager):
    with manager as value:
        return value


def synchronous_attribute(manager):
    with manager as value:
        return value.result


async def asynchronous(manager):
    async with manager as value:
        return value


async def asynchronous_attribute(manager):
    async with manager as value:
        return value.result

async def sequential_contexts(manager, work, record, flag):
    async with manager:
        a = await work("a")
    async with manager:
        b = await work("b")
    return a, b


async def awaited_then_context(manager, work, record, flag):
    try:
        a = await work("a")
        async with manager:
            b = await work("b")
    except ValueError:
        return "handled"
    return a, b


async def outer_handler(manager, work, record, flag):
    try:
        async with manager:
            a = await work("a")
            b = await work("b")
    except ValueError:
        return "handled"
    return a, b

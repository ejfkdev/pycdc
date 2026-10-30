async def awaited_finally(manager, work, record, flag):
    async with manager:
        try:
            await work("a")
        finally:
            record("cleanup")
        await work("b")
        return "tail"


async def awaited_else(manager, work, record, flag):
    async with manager:
        try:
            a = await work("a")
        except ValueError:
            record("handled")
        else:
            await work("b")
        return "tail"

async def guarded_return(manager, work, record, flag):
    async with manager:
        if flag:
            return "early"
        try:
            return await work("a")
        finally:
            record("cleanup")


async def computed_return(manager, work, record, flag):
    async with manager:
        try:
            return await work("a")
        finally:
            record("cleanup")


async def none_guard(manager, work, record, flag):
    async with manager:
        if flag is None:
            return 3
        try:
            return await work("a")
        finally:
            record("cleanup")

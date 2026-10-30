def sync_call(contexts, value):
    with contexts[0]:
        with contexts[1]:
            return value()


def sync_mapping(contexts, value):
    with contexts[0]:
        with contexts[1]:
            with contexts[2]:
                return {"rows": value()}


async def async_call(contexts, value):
    async with contexts[0]:
        async with contexts[1]:
            return value()


async def async_await(contexts, value):
    async with contexts[0]:
        async with contexts[1]:
            async with contexts[2]:
                return await value()


async def async_tuple(contexts, value):
    async with contexts[0]:
        async with contexts[1]:
            return (value(),)


async def async_single(contexts, value):
    async with contexts[0]:
        return await value()


def sync_outer_return(contexts, value):
    with contexts[0]:
        with contexts[1]:
            result = value()
        return result


async def async_outer_return(contexts, value):
    async with contexts[0]:
        async with contexts[1]:
            result = await value()
        return result

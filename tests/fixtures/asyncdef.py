import asyncio


async def fetch(x):
    await asyncio.sleep(x)
    return x


async def gen2():
    yield 1
    await asyncio.sleep(0)


async def loops():
    for i in range(3):
        await asyncio.sleep(i)
    async with open_ctx():
        pass


def open_ctx():
    return None

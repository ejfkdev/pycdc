# -*- coding: utf-8 -*-
# MIN_VERSION: 3.5
# async/await/async for/async with
import asyncio

async def worker(n):
    await asyncio.sleep(0)
    return n * 2

async def chain():
    a = await worker(2)
    b = await worker(3)
    return a + b

async def agen():
    for i in range(3):
        yield i

class ACM:
    async def __aenter__(self):
        await asyncio.sleep(0)
        return 'ctx'

    async def __aexit__(self, *a):
        await asyncio.sleep(0)
        return False

async def amain():
    print(await chain())
    out = []
    async for v in agen():
        out.append(v)
    print(out)
    async with ACM() as c:
        print(c)
    try:
        await worker(1)
    except ZeroDivisionError:
        pass
    print('async done')

loop = asyncio.new_event_loop()
loop.run_until_complete(amain())
loop.close()

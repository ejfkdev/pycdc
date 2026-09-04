# -*- coding: utf-8 -*-
# MIN_VERSION: 3.7
# 异步进阶：async generator、async for-else、嵌套 async with、
# async 推导式、finally 中 await、athrow/aclose

import asyncio

async def agen(n):
    for i in range(n):
        await asyncio.sleep(0)
        yield i * 2

async def agen_fin(log):
    try:
        yield 1
        yield 2
    finally:
        log.append('agen-fin')

class Ctx:
    def __init__(self, log, name):
        self.log = log
        self.name = name

    async def __aenter__(self):
        await asyncio.sleep(0)
        self.log.append('enter-' + self.name)
        return self.name

    async def __aexit__(self, *exc):
        await asyncio.sleep(0)
        self.log.append('exit-' + self.name)
        return False

async def collect():
    out = []
    async for v in agen(3):
        out.append(v)
    else:
        out.append('for-else')
    return out

async def collect_break():
    out = []
    async for v in agen(5):
        if v == 4:
            out.append('break')
            break
        out.append(v)
    else:
        out.append('no-break')
    return out

async def nested_ctx():
    log = []
    async with Ctx(log, 'a') as x:
        async with Ctx(log, 'b') as y:
            log.append((x, y))
    return log

async def multi_ctx():
    log = []
    async with Ctx(log, 'p') as p, Ctx(log, 'q') as q:
        log.append(p + q)
    return log

async def acomp():
    out = [v async for v in agen(4) if v > 2]
    d = {v: v * v async for v in agen(3)}
    s = sorted({v % 3 async for v in agen(5)})
    return out, sorted(d.items()), s

async def throw_agen():
    log = []
    async def g():
        try:
            while True:
                v = yield 'r'
                log.append(('got', v))
        except RuntimeError as e:
            log.append(('rt', str(e)))
    it = g()
    await it.__anext__()
    await it.asend(1)
    try:
        await it.athrow(RuntimeError, 'boom')
    except StopAsyncIteration:
        log.append('stopped')
    await it.aclose()
    return log

async def finally_await():
    log = []
    async def work():
        try:
            await asyncio.sleep(0)
            return 'ok'
        finally:
            await asyncio.sleep(0)
            log.append('fin')
    r = await work()
    return log, r

async def main():
    print(await collect())
    print(await collect_break())
    print(await nested_ctx())
    print(await multi_ctx())
    print(await acomp())

    log = []
    it = agen_fin(log)
    print(await it.__anext__(), log)
    await it.aclose()
    print(log)

    print(await throw_agen())
    print(await finally_await())

    tasks = [agen(2).__anext__() for _ in range(2)]
    vals = []
    for t in tasks:
        try:
            vals.append(await t)
        except StopAsyncIteration:
            vals.append('stop')
    print(vals)

asyncio.run(main())

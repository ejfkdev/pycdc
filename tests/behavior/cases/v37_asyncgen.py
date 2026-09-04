# -*- coding: utf-8 -*-
# MIN_VERSION: 3.8
# 异步进阶：async generator、async for-else、嵌套 async with、
# finally 中 await
# 已知缺口：3.7 SETUP_EXCEPT 守卫式 async-for 的 break+else 组合、
# 内联 async 推导式、athrow/asend 协议（暂未支持，3.7 因此整体 gate 到 3.8）

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

# NOTE: 内联 async 推导式（[v async for ...] / {k: v async for ...}）
# 与 async 生成器 athrow/asend 协议暂不支持（已知缺口，后续补）

async def multi_ctx():
    log = []
    async with Ctx(log, 'p') as p, Ctx(log, 'q') as q:
        log.append(p + q)
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

    log = []
    it = agen_fin(log)
    print(await it.__anext__(), log)
    await it.aclose()
    print(log)

    print(await finally_await())

asyncio.run(main())

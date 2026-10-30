# MIN_VERSION: 3.12
import asyncio

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


async def exercise(function, failure, suppress):
    events = []

    async def work(label):
        events.append(label)
        await asyncio.sleep(0)
        if failure == label:
            raise ValueError(label)
        return 1 if label == "a" else 2

    def record(label):
        events.append(label)

    class Manager:
        async def __aenter__(self):
            events.append("enter")
            await asyncio.sleep(0)
            if failure == "enter":
                raise ValueError("enter")
            return self

        async def __aexit__(self, typ, value, traceback):
            events.append(("exit", typ.__name__ if typ else None))
            await asyncio.sleep(0)
            if failure == "exit":
                raise ValueError("exit")
            return suppress

    try:
        result = await function(Manager(), work, record, False)
        print("return", result)
    except BaseException as error:
        print(type(error).__name__, str(error))
    print(events)


for function in (sequential_contexts, awaited_then_context, outer_handler):
    for failure in ("", "a", "b", "cleanup", "enter", "exit"):
        for suppress in (False, True):
            print(function.__name__, failure, suppress)
            asyncio.run(exercise(function, failure, suppress))

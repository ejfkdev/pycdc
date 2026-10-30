# MIN_VERSION: 3.14
import asyncio

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


async def exercise(function, failure, suppress, flag):
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
        result = await function(Manager(), work, record, flag)
        print("return", result)
    except BaseException as error:
        print(type(error).__name__, str(error))
    print(events)


for function in (guarded_return, computed_return, none_guard):
    for failure in ("", "a", "cleanup", "enter", "exit"):
        for suppress in (False, True):
            for flag in (False, True, None):
                print(function.__name__, failure, suppress, flag)
                asyncio.run(exercise(function, failure, suppress, flag))

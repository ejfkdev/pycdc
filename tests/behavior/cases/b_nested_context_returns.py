# MIN_VERSION: 3.11
import asyncio

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


events = []
opened = set()

class Context:
    def __init__(self, index):
        self.index = index

    def __enter__(self):
        events.append(("enter", self.index))
        if failure == "enter-" + str(self.index):
            raise ValueError("entry")
        opened.add(self.index)
        return self

    def __exit__(self, kind, error, traceback):
        events.append(("exit", self.index, kind.__name__ if kind else None))
        opened.remove(self.index)
        if failure == "exit-" + str(self.index):
            raise ValueError("exit")
        return self.index == suppression and kind is ValueError

    async def __aenter__(self):
        await asyncio.sleep(0)
        return self.__enter__()

    async def __aexit__(self, kind, error, traceback):
        await asyncio.sleep(0)
        return self.__exit__(kind, error, traceback)


def value():
    events.append(("value", tuple(sorted(opened))))
    if failure == "body":
        raise ValueError("body")
    if failure == "cancelled":
        raise asyncio.CancelledError("cancelled")
    return 7


async def async_value():
    await asyncio.sleep(0)
    return value()


cases = [
    (sync_call, 2, False),
    (sync_mapping, 3, False),
    (async_call, 2, False),
    (async_await, 3, True),
    (async_tuple, 2, False),
    (async_single, 1, True),
    (sync_outer_return, 2, False),
    (async_outer_return, 2, True),
]
for function, depth, isawait in cases:
    for failure in ("", "body", "cancelled", "enter-0", "enter-1", "enter-2", "exit-0", "exit-1", "exit-2"):
        for suppression in (-1, 0, 1, 2):
            events.clear()
            opened.clear()
            print(function.__name__, failure, suppression)
            contexts = [Context(index) for index in range(depth)]
            try:
                result = function(contexts, async_value if isawait else value)
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                print("return", result)
            except (ValueError, asyncio.CancelledError, UnboundLocalError) as error:
                print(type(error).__name__, str(error))
            print(events, tuple(sorted(opened)))

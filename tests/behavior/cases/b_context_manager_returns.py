# MIN_VERSION: 3.9
# Controls for the modern exit protocol; Python 3.8 async returns have a separate gap.
import asyncio

def synchronous(manager):
    with manager as value:
        return value


def synchronous_attribute(manager):
    with manager as value:
        return value.result


async def asynchronous(manager):
    async with manager as value:
        return value


async def asynchronous_attribute(manager):
    async with manager as value:
        return value.result


events = []


class Manager:
    def __repr__(self):
        return "manager"

    def __enter__(self):
        events.append("enter")
        if failure == "enter":
            raise ValueError("enter")
        return self

    def __exit__(self, typ, value, traceback):
        events.append(("exit", typ.__name__ if typ else None))
        if failure == "exit":
            raise ValueError("exit")
        return suppress

    async def __aenter__(self):
        await asyncio.sleep(0)
        return self.__enter__()

    async def __aexit__(self, typ, value, traceback):
        await asyncio.sleep(0)
        return self.__exit__(typ, value, traceback)

    @property
    def result(self):
        events.append("read")
        if failure == "read":
            raise ValueError("read")
        return 7


for failure in ("", "enter", "exit", "read"):
    for suppress in (False, True):
        for function in (synchronous, synchronous_attribute, asynchronous, asynchronous_attribute):
            events.clear()
            print(function.__name__, failure, suppress)
            try:
                result = function(Manager())
                if asyncio.iscoroutine(result):
                    result = asyncio.run(result)
                print("return", result)
            except ValueError as error:
                print("error", str(error))
            print(events)

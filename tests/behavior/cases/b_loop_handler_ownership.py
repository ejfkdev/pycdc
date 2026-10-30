# MIN_VERSION: 3.12
import asyncio

def named(owner):
    try:
        for row in owner.rows:
            try:
                owner.record(row)
            except ValueError as error:
                owner.failed(row, str(error))
        owner.finish()
    except RuntimeError as error:
        owner.fallback(str(error))
    return None


def multiple(owner):
    try:
        for row in owner.rows:
            try:
                owner.record(row)
            except ValueError as error:
                owner.failed(row, str(error))
            except KeyError as error:
                owner.other(row, str(error))
        owner.finish()
    except RuntimeError as error:
        owner.fallback(str(error))
    return None


def siblings(owner):
    try:
        for row in owner.rows:
            try:
                owner.record(row)
            except ValueError:
                owner.failed(row)
            try:
                owner.second(row)
            except KeyError:
                owner.other(row)
        owner.finish()
    except RuntimeError as error:
        owner.fallback(str(error))
    return None


def same_type(owner):
    try:
        for row in owner.rows:
            try:
                owner.record(row)
            except Exception:
                owner.failed(row)
        owner.finish()
    except Exception as error:
        owner.fallback(str(error))
    return None


async def async_0(owner):
    try:
        for row in owner.rows:
            try:
                owner.record(row)
            except ValueError:
                owner.failed(row)
        owner.finish()
    except RuntimeError:
        owner.fallback()
    return None


async def async_1(owner):
    try:
        for row in owner.rows:
            try:
                await owner.arecord(row)
            except ValueError:
                owner.failed(row)
        owner.finish()
    except RuntimeError:
        owner.fallback()
    return None


async def async_2(owner):
    try:
        for row in owner.rows:
            try:
                await owner.arecord(row)
                await owner.asecond(row)
            except ValueError:
                owner.failed(row)
        owner.finish()
    except RuntimeError:
        owner.fallback()
    return None


def outer_finally(owner):
    try:
        for row in owner.rows:
            try:
                owner.record(row)
            except ValueError:
                owner.failed(row)
    finally:
        owner.finish()
    return None


def nonloop(owner):
    try:
        try:
            owner.record(owner.row)
        except ValueError:
            owner.failed(owner.row)
    except RuntimeError:
        owner.fallback()
    return None


class Owner:
    def __init__(self):
        self.rows = [] if case == "empty" else [1, 2, 3]
        self.events = []
        self.row = 2

    def record(self, row):
        self.events.append(("record", row))
        if case in ("row-error", "handler-error") and row == 2:
            raise ValueError("row")
        if case == "key-error" and row == 2:
            raise KeyError("key")
        if case == "runtime-error":
            raise RuntimeError("runtime")
        if case == "cancel":
            raise asyncio.CancelledError("cancelled")

    async def arecord(self, row):
        await asyncio.sleep(0)
        self.record(row)

    def second(self, row):
        self.events.append(("second", row))
        if case == "second-error" and row == 2:
            raise KeyError("second")

    async def asecond(self, row):
        await asyncio.sleep(0)
        self.second(row)

    def failed(self, row, *details):
        self.events.append(("failed", row, details))
        if case == "handler-error":
            raise RuntimeError("handler")

    def other(self, row, *details):
        self.events.append(("other", row, details))

    def finish(self):
        self.events.append("finish")
        if case == "finish-error":
            raise RuntimeError("finish")

    def fallback(self, *details):
        self.events.append(("fallback", details))


functions = (named, multiple, siblings, same_type, async_0, async_1, async_2, outer_finally, nonloop)
for function in functions:
    for case in ("normal", "empty", "row-error", "key-error", "second-error", "handler-error", "finish-error", "runtime-error", "cancel"):
        owner = Owner()
        print(function.__name__, case)
        try:
            result = function(owner)
            if asyncio.iscoroutine(result):
                result = asyncio.run(result)
            print("return", result)
        except BaseException as error:
            print("error", type(error).__name__, str(error))
        print(owner.events)

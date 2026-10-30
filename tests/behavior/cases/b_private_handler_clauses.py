# MIN_VERSION: 3.12
import asyncio


async def named(owner):
    accepted = False
    for candidate in owner.candidates:
        try:
            for value in (candidate, "keeper"):
                await owner.check(value)
            accepted = bool(await owner.reconsider(candidate)) or accepted
        except Incompatible as error:
            details = "reviewable"
            if owner.can_close:
                try:
                    changed = bool(await owner.close(candidate))
                    details = "closed" if changed else "terminal"
                except RuntimeError as inner:
                    await owner.log("close-failed", str(inner))
            await owner.log("incompatible", details)
        except ValueError as error:
            await owner.log("invalid", str(error))
            continue
        except (OSError, asyncio.TimeoutError) as error:
            await owner.log("transient", str(error))
            continue
        except Exception as error:
            await owner.log("unavailable", str(error))
            continue
    await owner.log("finished", accepted)
    return accepted


def synchronous(owner):
    accepted = False
    for candidate in owner.candidates:
        try:
            for value in (candidate, "keeper"):
                owner.check(value)
            accepted = bool(owner.reconsider(candidate)) or accepted
        except Incompatible as error:
            details = "reviewable"
            if owner.can_close:
                try:
                    changed = bool(owner.close(candidate))
                    details = "closed" if changed else "terminal"
                except RuntimeError as inner:
                    owner.log("close-failed", str(inner))
            owner.log("incompatible", details)
        except ValueError as error:
            owner.log("invalid", str(error))
            continue
        except (OSError, asyncio.TimeoutError) as error:
            owner.log("transient", str(error))
            continue
        except Exception as error:
            owner.log("unavailable", str(error))
            continue
    owner.log("finished", accepted)
    return accepted


async def attributes(owner):
    accepted = False
    for candidate in owner.candidates:
        try:
            for value in (candidate, "keeper"):
                await owner.check(value)
            accepted = bool(await owner.reconsider(candidate)) or accepted
        except faults.incompatible as error:
            details = "reviewable"
            if owner.can_close:
                try:
                    changed = bool(await owner.close(candidate))
                    details = "closed" if changed else "terminal"
                except RuntimeError as inner:
                    await owner.log("close-failed", str(inner))
            await owner.log("incompatible", details)
        except faults.invalid as error:
            await owner.log("invalid", str(error))
            continue
        except (faults.operating, faults.timeout) as error:
            await owner.log("transient", str(error))
            continue
        except faults.ordinary as error:
            await owner.log("unavailable", str(error))
            continue
    await owner.log("finished", accepted)
    return accepted


async def local_attributes(owner, faults):
    accepted = False
    for candidate in owner.candidates:
        try:
            for value in (candidate, "keeper"):
                await owner.check(value)
            accepted = bool(await owner.reconsider(candidate)) or accepted
        except faults.incompatible as error:
            details = "reviewable"
            if owner.can_close:
                try:
                    changed = bool(await owner.close(candidate))
                    details = "closed" if changed else "terminal"
                except RuntimeError as inner:
                    await owner.log("close-failed", str(inner))
            await owner.log("incompatible", details)
        except faults.invalid as error:
            await owner.log("invalid", str(error))
            continue
        except (faults.operating, faults.timeout) as error:
            await owner.log("transient", str(error))
            continue
        except faults.ordinary as error:
            await owner.log("unavailable", str(error))
            continue
    await owner.log("finished", accepted)
    return accepted


async def single_clause(owner):
    accepted = False
    for candidate in owner.candidates:
        try:
            for value in (candidate, "keeper"):
                await owner.check(value)
            accepted = bool(await owner.reconsider(candidate)) or accepted
        except Incompatible as error:
            details = "reviewable"
            if owner.can_close:
                try:
                    changed = bool(await owner.close(candidate))
                    details = "closed" if changed else "terminal"
                except RuntimeError as inner:
                    await owner.log("close-failed", str(inner))
            await owner.log("incompatible", details)
    await owner.log("finished", accepted)
    return accepted


async def no_private_try(owner):
    accepted = False
    for candidate in owner.candidates:
        try:
            for value in (candidate, "keeper"):
                await owner.check(value)
            accepted = bool(await owner.reconsider(candidate)) or accepted
        except Incompatible as error:
            details = "reviewable"
            if owner.can_close:
                changed = bool(await owner.close(candidate))
                details = "closed" if changed else "terminal"
            await owner.log("incompatible", details)
        except ValueError as error:
            await owner.log("invalid", str(error))
            continue
        except (OSError, asyncio.TimeoutError) as error:
            await owner.log("transient", str(error))
            continue
        except Exception as error:
            await owner.log("unavailable", str(error))
            continue
    await owner.log("finished", accepted)
    return accepted


class Incompatible(ValueError):
    pass

class Owner:

    def __init__(self):
        self.candidates = [] if case == 'empty' else ['first', 'second']
        self.can_close = case != 'no-close'
        self.events = []

    def check(self, value):
        self.events.append(('check', value))
        if value == 'first':
            failures = {'incompatible': Incompatible, 'no-close': Incompatible, 'close-failed': Incompatible, 'terminal': Incompatible, 'log-error': Incompatible, 'invalid': ValueError, 'io': OSError, 'timeout': asyncio.TimeoutError, 'unexpected': LookupError, 'cancel': asyncio.CancelledError}
            if case in failures:
                raise failures[case]('owned fault')

    def reconsider(self, candidate):
        self.events.append(('reconsider', candidate))
        return True

    def close(self, candidate):
        self.events.append(('close', candidate))
        if case == 'close-failed':
            raise RuntimeError('owned close')
        return case != 'terminal'

    def log(self, *values):
        self.events.append(('log', *values))
        if case == 'log-error' and values[0] == 'incompatible':
            raise KeyError('owned log')
        if case == 'finish-error' and values[0] == 'finished':
            raise RuntimeError('owned finish')

class AsyncOwner(Owner):
    async def check(self, value):
        await asyncio.sleep(0)
        return super().check(value)

    async def reconsider(self, candidate):
        await asyncio.sleep(0)
        return super().reconsider(candidate)

    async def close(self, candidate):
        await asyncio.sleep(0)
        return super().close(candidate)

    async def log(self, *values):
        await asyncio.sleep(0)
        return super().log(*values)


from types import SimpleNamespace
faults = SimpleNamespace(incompatible=Incompatible, invalid=ValueError,
    operating=OSError, timeout=asyncio.TimeoutError, ordinary=Exception)
functions = [
    (named, True, False),
    (synchronous, False, False),
    (attributes, True, False),
    (local_attributes, True, True),
    (single_clause, True, False),
    (no_private_try, True, False),
]
for function, asynchronous, local in functions:
    for case in ("normal", "empty", "incompatible", "no-close", "close-failed", "terminal", "invalid", "io", "timeout", "unexpected", "cancel", "log-error", "finish-error"):
        owner = AsyncOwner() if asynchronous else Owner()
        print(function.__name__, case)
        try:
            result = function(owner, faults) if local else function(owner)
            if asynchronous:
                result = asyncio.run(result)
            print("return", result)
        except BaseException as error:
            print("error", type(error).__name__, str(error))
        print(owner.events)

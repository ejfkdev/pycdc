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

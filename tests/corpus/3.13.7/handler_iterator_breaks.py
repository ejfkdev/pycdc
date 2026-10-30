import asyncio


async def named_break(owner):
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
            break
        except Exception as error:
            await owner.log("unavailable", str(error))
            break
    await owner.log("finished", accepted)
    return accepted


def sync_break(owner):
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
            break
        except Exception as error:
            owner.log("unavailable", str(error))
            break
    owner.log("finished", accepted)
    return accepted


async def direct_break(owner):
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
            break
        except Exception as error:
            await owner.log("unavailable", str(error))
            break
    await owner.log("finished", accepted)
    return accepted


async def unnamed_break(owner):
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
        except (OSError, asyncio.TimeoutError):
            await owner.log("transient", "owned fault")
            break
        except Exception:
            await owner.log("unavailable", "owned fault")
            break
    await owner.log("finished", accepted)
    return accepted


async def direct_unnamed_break(owner):
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
        except (OSError, asyncio.TimeoutError):
            await owner.log("transient", "owned fault")
            break
        except Exception:
            await owner.log("unavailable", "owned fault")
            break
    await owner.log("finished", accepted)
    return accepted

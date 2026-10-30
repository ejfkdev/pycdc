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

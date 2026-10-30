# MIN_VERSION: 3.11

# Regenerate with: python tools/compile_bounded_try_returns.py
# The compiled inputs add NOPs before returns and relocate exception ranges.
from datetime import datetime, timezone


def parse_timestamp(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def unprotected_return(read):
    try:
        read("inside")
    except ValueError:
        return
    return read("outside")


def else_return(read):
    try:
        read("inside")
    except ValueError:
        return
    else:
        return read("outside")


for value in (
    None, True, False, 0, 123456789, float("inf"), float("nan"), "invalid",
    "2026-10-12T12:00:00", "2026-10-12T12:00:00Z",
    datetime(2026, 10, 12), datetime(2026, 10, 12, tzinfo=timezone.utc),
):
    print(parse_timestamp(value))


def read(where):
    print("read", where)
    if where == "outside":
        raise ValueError("outside the protected body")


for function in (unprotected_return, else_return):
    try:
        function(read)
    except ValueError as error:
        print(function.__name__, str(error))

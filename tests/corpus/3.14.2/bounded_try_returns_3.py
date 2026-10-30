# Regenerate with: python tools/compile_padded_none_returns.py
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

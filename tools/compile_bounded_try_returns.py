"""Generate Bounded try-return fixtures with CPython 3.11–3.15.

The zero-padding inputs and RETURN_CONST versions are compatibility controls.
This reuses the existing relocation helper rather than changing return values.
"""
import importlib.util
import marshal
from pathlib import Path
import sys
import types

from compile_padded_value_returns import pad_return_values


if __name__ == "__main__":
    if not (3, 11) <= sys.version_info[:2] <= (3, 15):
        raise SystemExit("Use CPython 3.11 through 3.15")
    root = Path(__file__).resolve().parents[1]
    source_path = Path("tests/data/bounded_try_returns.py")
    source = (root / source_path).read_bytes()
    module = compile(source, source_path.as_posix(), "exec", dont_inherit=True)
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    header = (importlib.util.MAGIC_NUMBER + (3).to_bytes(4, "little")
              + importlib.util.source_hash(source))
    for count in (0, 1, 3):
        padded = module.replace(co_consts=tuple(
            pad_return_values(value, count) if isinstance(value, types.CodeType) else value
            for value in module.co_consts))
        payload = header + marshal.dumps(padded)
        (root / f"tests/pyc/bounded_try_returns_{count}.{version}.pyc").write_bytes(payload)
        if count == 3:
            corpus = root / "tests/corpus" / ".".join(map(str, sys.version_info[:3]))
            corpus.mkdir(parents=True, exist_ok=True)
            (corpus / "bounded_try_returns_3.py").write_bytes(source)
            (corpus / "bounded_try_returns_3.pyc").write_bytes(payload)

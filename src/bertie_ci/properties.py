from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

_ESCAPES = {
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\f": "\\f",
}


def _escape(text: str, *, key: bool) -> str:
    """Escape one key or value for ``java.util.Properties.load``.

    Windows paths are the reason this exists. ``C:\\Users\\berlord`` is read back
    as ``C:Usersberlord``, and a segment beginning with a lowercase ``u`` makes
    the loader throw ``Malformed \\uxxxx encoding`` outright.
    """
    out: list[str] = []
    for index, char in enumerate(text):
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif char == " " and (key or index == 0):
            out.append("\\ ")
        elif key and char in "=:":
            out.append("\\" + char)
        elif index == 0 and char in "#!":
            out.append("\\" + char)
        elif "\x20" <= char <= "\x7e":
            out.append(char)
        else:
            # HeadlessMC loads the file as an InputStream, so it is decoded as
            # ISO-8859-1. Escaping everything outside printable ASCII keeps the
            # file identical under either decoding.
            encoded = char.encode("utf-16-be")
            for offset in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[offset : offset + 2], "big")
                out.append(f"\\u{unit:04x}")
    return "".join(out)


def render_properties(entries: Mapping[str, str | Path]) -> str:
    lines = [
        f"{_escape(key, key=True)}={_escape(os.fspath(value), key=False)}"
        for key, value in entries.items()
    ]
    return "\n".join(lines) + "\n"


def write_properties(path: Path, entries: Mapping[str, str | Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # `_escape` leaves only printable ASCII behind; encoding as ASCII asserts it.
    path.write_text(render_properties(entries), encoding="ascii")

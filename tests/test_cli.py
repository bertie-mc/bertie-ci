import io
import sys

import pytest

from bertie_ci.cli import tolerate_unencodable_output


def test_streams_survive_characters_outside_the_ansi_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirected stdout on Windows encodes as cp1252, and Minecraft logs do not."""
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)

    with pytest.raises(UnicodeEncodeError):
        stream.write("█ progress\n")
        stream.flush()

    tolerate_unencodable_output()
    stream.write("█ progress\n")
    stream.flush()

    assert b"? progress" in buffer.getvalue()

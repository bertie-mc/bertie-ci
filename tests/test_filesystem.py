import os
import stat
from pathlib import Path

from bertie_ci.filesystem import replace_file


def test_replace_file_replaces_read_only_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.jar"
    destination = tmp_path / "destination.jar"
    source.write_bytes(b"new")
    destination.write_bytes(b"old")
    os.chmod(destination, stat.S_IREAD)

    try:
        replace_file(source, destination)
    finally:
        if destination.exists():
            os.chmod(destination, stat.S_IREAD | stat.S_IWRITE)

    assert destination.read_bytes() == b"new"

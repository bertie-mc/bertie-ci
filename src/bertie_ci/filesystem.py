from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any, Callable


def _clear_readonly(func: Callable[[str], Any], target: str, _error: Any) -> None:
    os.chmod(target, stat.S_IWRITE)
    func(target)


def remove_tree(path: Path) -> None:
    """Delete a tree while tolerating read-only files on Windows."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_readonly)
    else:
        shutil.rmtree(path, onerror=_clear_readonly)


def remove_file(path: Path) -> None:
    """Delete a file while tolerating a read-only Windows attribute."""
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        path.unlink()


def replace_file(source: Path, destination: Path) -> None:
    """Copy a file over an optional read-only destination."""
    remove_file(destination)
    shutil.copy2(source, destination)

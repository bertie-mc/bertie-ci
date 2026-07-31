import os
import stat
from pathlib import Path

import pytest

from bertie_ci.artifact import find_artifact
from bertie_ci.runtime import _reset_runtime


def test_find_artifact_ignores_documentation_jars(tmp_path: Path) -> None:
    libraries = tmp_path / "build" / "libs"
    libraries.mkdir(parents=True)
    runtime = libraries / "example-1.0.jar"
    runtime.touch()
    (libraries / "example-1.0-sources.jar").touch()
    (libraries / "example-1.0-javadoc.jar").touch()

    assert find_artifact(tmp_path, None) == runtime.resolve()


def test_find_artifact_rejects_ambiguous_output(tmp_path: Path) -> None:
    libraries = tmp_path / "build" / "libs"
    libraries.mkdir(parents=True)
    (libraries / "one.jar").touch()
    (libraries / "two.jar").touch()

    with pytest.raises(RuntimeError, match="Expected one runtime JAR"):
        find_artifact(tmp_path, None)


def test_find_artifact_accepts_download_directory(tmp_path: Path) -> None:
    downloads = tmp_path / "download"
    downloads.mkdir()
    runtime = downloads / "example.jar"
    runtime.touch()

    assert find_artifact(tmp_path, downloads) == runtime.resolve()


def test_reset_runtime_only_replaces_selected_runtime(tmp_path: Path) -> None:
    work = tmp_path / "work"
    old_run = work / "client" / "run"
    old_run.mkdir(parents=True)
    (old_run / "old.log").touch()
    sibling = work / "keep.txt"
    sibling.write_text("keep", encoding="utf-8")

    runtime = _reset_runtime(work, "client")

    assert runtime == (work / "client").resolve()
    assert not (runtime / "run" / "old.log").exists()
    assert (runtime / "run" / "mods").is_dir()
    assert (runtime / "HeadlessMC").is_dir()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_reset_runtime_replaces_read_only_files(tmp_path: Path) -> None:
    """Windows refuses to unlink a read-only file; a stale run must still clear."""
    work = tmp_path / "work"
    old_run = work / "client" / "run"
    old_run.mkdir(parents=True)
    stale = old_run / "options.txt"
    stale.write_text("stale", encoding="utf-8")
    os.chmod(stale, stat.S_IREAD)

    try:
        runtime = _reset_runtime(work, "client")
    finally:
        if stale.exists():
            os.chmod(stale, stat.S_IWRITE)

    assert not stale.exists()
    assert (runtime / "run" / "mods").is_dir()

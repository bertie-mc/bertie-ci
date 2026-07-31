import json
import os
import stat
from pathlib import Path

import pytest

from bertie_ci.artifact import find_artifact
from bertie_ci.runtime import (
    _accept_minecraft_eula,
    _reset_probe,
    _server_readiness_was_recorded,
    _set_options,
    _write_server_readiness_test,
)


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


def test_reset_probe_preserves_prepared_instance(tmp_path: Path) -> None:
    work = tmp_path / "work"
    instance = work / "instance"
    instance.mkdir(parents=True)
    sibling = instance / "keep.txt"
    sibling.write_text("keep", encoding="utf-8")
    control = work / "HeadlessMC"
    control.mkdir()
    (control / "old.log").touch()
    (work / "runtime.log").touch()

    result = _reset_probe(work)

    assert result == work.resolve()
    assert not (control / "old.log").exists()
    assert control.is_dir()
    assert not (work / "runtime.log").exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_reset_probe_replaces_read_only_control_files(tmp_path: Path) -> None:
    """Windows refuses to unlink a read-only file; a stale run must still clear."""
    work = tmp_path / "work"
    control = work / "HeadlessMC"
    control.mkdir(parents=True)
    stale = control / "config.properties"
    stale.write_text("stale", encoding="utf-8")
    os.chmod(stale, stat.S_IREAD)

    try:
        runtime = _reset_probe(work)
    finally:
        if stale.exists():
            os.chmod(stale, stat.S_IWRITE)

    assert not stale.exists()
    assert (runtime / "HeadlessMC").is_dir()


def test_set_options_replaces_probe_values_and_preserves_pack_values(
    tmp_path: Path,
) -> None:
    options = tmp_path / "options.txt"
    options.write_text(
        "onboardAccessibility:true\nrenderDistance:12\n", encoding="utf-8"
    )

    _set_options(
        options, {"onboardAccessibility": "false", "pauseOnLostFocus": "false"}
    )

    assert options.read_text(encoding="utf-8").splitlines() == [
        "renderDistance:12",
        "onboardAccessibility:false",
        "pauseOnLostFocus:false",
    ]


def test_accept_minecraft_eula_avoids_preliminary_server_launch(
    tmp_path: Path,
) -> None:
    _accept_minecraft_eula(tmp_path)

    assert (tmp_path / "eula.txt").read_text(encoding="utf-8").splitlines()[-1] == (
        "eula=true"
    )


def test_server_readiness_test_does_not_require_clean_shutdown(
    tmp_path: Path,
) -> None:
    test = json.loads(
        _write_server_readiness_test(tmp_path, 4500).read_text(encoding="utf-8")
    )

    assert test["timeout"] == 4350
    assert test["implicitWaitForEnd"] is False
    assert [step["type"] for step in test["steps"]] == [
        "ENDS_WITH",
        "SEND",
        "SUCCESS",
    ]


def test_server_readiness_timeout_keeps_cleanup_margin(tmp_path: Path) -> None:
    test = json.loads(
        _write_server_readiness_test(tmp_path, 120).read_text(encoding="utf-8")
    )

    assert test["timeout"] == 1


def test_server_readiness_requires_headlessmc_success_marker(tmp_path: Path) -> None:
    runtime_log = tmp_path / "runtime.log"
    runtime_log.write_text(
        "[main/INFO] CommandTest was successful.\nMinecraft exited with code: 143\n",
        encoding="utf-8",
    )

    assert _server_readiness_was_recorded(runtime_log)


def test_server_readiness_rejects_missing_success_marker(tmp_path: Path) -> None:
    runtime_log = tmp_path / "runtime.log"
    runtime_log.write_text("CommandTest failed!\n", encoding="utf-8")

    assert not _server_readiness_was_recorded(runtime_log)

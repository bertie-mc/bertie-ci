from pathlib import Path

import pytest

from bertie_ci.artifact import find_artifact, stage_artifact
from bertie_ci.gradle import verify_gametest_log


def _log(tmp_path: Path, text: str) -> Path:
    log = tmp_path / "gametest.log"
    log.write_text(text, encoding="utf-8")
    return log


def test_verify_gametest_log_requires_a_completed_run(tmp_path: Path) -> None:
    log = _log(
        tmp_path,
        """
14 tests are now running at position 1, 2, 3!
========= 14 GAME TESTS COMPLETE IN 10 ms =========
All 14 required tests passed :)
Game test server shutting down
BUILD SUCCESSFUL
""",
    )

    assert verify_gametest_log(log) == 14


@pytest.mark.parametrize(
    "text, message",
    [
        (
            "Failed to start the minecraft server\nBUILD SUCCESSFUL",
            "failed before completion",
        ),
        ("BUILD SUCCESSFUL", "did not discover any tests"),
        ("0 tests are now running\nBUILD SUCCESSFUL", "did not discover any tests"),
        ("2 tests are now running\nBUILD SUCCESSFUL", "did not complete successfully"),
    ],
)
def test_verify_gametest_log_fails_closed(
    tmp_path: Path, text: str, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        verify_gametest_log(_log(tmp_path, text))


def test_find_artifact_ignores_documentation_jars(tmp_path: Path) -> None:
    libraries = tmp_path / "build" / "libs"
    libraries.mkdir(parents=True)
    runtime = libraries / "example-1.0.0.jar"
    runtime.touch()
    (libraries / "example-1.0.0-sources.jar").touch()
    (libraries / "example-1.0.0-javadoc.jar").touch()

    assert find_artifact(tmp_path, None) == runtime


def test_stage_artifact_preserves_release_filename(tmp_path: Path) -> None:
    runtime = tmp_path / "build" / "libs" / "example-1.0.0.jar"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"jar")

    staged = stage_artifact(runtime, tmp_path / ".bertie-ci" / "artifact")

    assert staged.name == runtime.name
    assert staged.read_bytes() == b"jar"


def test_stage_artifact_rejects_ambiguous_output(tmp_path: Path) -> None:
    runtime = tmp_path / "build" / "libs" / "example-1.0.0.jar"
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    output = tmp_path / ".bertie-ci" / "artifact"
    output.mkdir(parents=True)
    (output / "old-version.jar").touch()

    with pytest.raises(RuntimeError, match="contains other JARs"):
        stage_artifact(runtime, output)

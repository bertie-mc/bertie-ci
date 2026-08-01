from pathlib import Path

import pytest

from bertie_ci.artifact import find_artifact, stage_artifact
from bertie_ci.gradle import assemble_client_test_mod, run_gradle, verify_gametest_log


def test_run_gradle_uses_the_managed_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invocation = {}

    def fake_run(command, **kwargs) -> None:
        invocation["command"] = command
        invocation.update(kwargs)

    gradle = tmp_path / "nix-store" / "bin" / "gradle"
    java_home = tmp_path / "jdk"
    monkeypatch.setenv("BERTIE_CI_GRADLE", str(gradle))
    monkeypatch.setattr("bertie_ci.gradle.run", fake_run)

    run_gradle(tmp_path, java_home, ["assemble"])

    assert invocation["command"] == [
        str(gradle),
        "assemble",
        "--no-daemon",
        "--stacktrace",
    ]
    assert invocation["cwd"] == tmp_path
    assert invocation["env"]["JAVA_HOME"] == str(java_home)


def test_client_test_mod_build_has_a_stable_staged_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_libs = tmp_path / "build" / "test-libs"
    test_libs.mkdir(parents=True)
    source = test_libs / "example-client-tests.jar"
    source.write_bytes(b"test mod")
    tasks = []
    monkeypatch.setattr(
        "bertie_ci.gradle.run_gradle",
        lambda _project, _java, requested: tasks.extend(requested),
    )

    staged = assemble_client_test_mod(
        tmp_path, tmp_path / "jdk", tmp_path / ".bertie-ci" / "client-test-mod"
    )

    assert tasks == ["clientTestJar"]
    assert staged.name == "client-test-mod.jar"
    assert staged.read_bytes() == b"test mod"


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

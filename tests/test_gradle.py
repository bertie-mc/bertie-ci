from pathlib import Path

import pytest

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

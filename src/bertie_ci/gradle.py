from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Sequence

from .artifact import find_artifact, stage_artifact
from .process import run


def run_gradle(
    project: Path,
    java_home: Path,
    tasks: Sequence[str],
    *,
    log: Path | None = None,
    timeout_seconds: int | None = None,
) -> None:
    command: list[str | Path] = [
        os.environ.get("BERTIE_CI_GRADLE", "gradle"),
        *tasks,
        "--no-daemon",
        "--stacktrace",
    ]
    run(
        command,
        cwd=project,
        env={**os.environ, "JAVA_HOME": os.fspath(java_home)},
        log=log,
        timeout_seconds=timeout_seconds,
    )


def assemble_mod(project: Path, java_home: Path) -> None:
    run_gradle(project, java_home, ["assemble"])


def assemble_client_test_mod(project: Path, java_home: Path, output_dir: Path) -> Path:
    """Build and stage the conventional clientTest test-only mod."""
    run_gradle(project, java_home, ["clientTestJar"])
    artifact = find_artifact(project, Path("build/test-libs"))
    return stage_artifact(artifact, output_dir, "client-test-mod.jar")


def run_unit_tests(project: Path, java_home: Path) -> None:
    run_gradle(project, java_home, ["test"])


def run_gametests(
    project: Path, java_home: Path, work: Path, timeout_seconds: int
) -> int:
    work.mkdir(parents=True, exist_ok=True)
    log = work / "gametest.log"
    run_gradle(
        project,
        java_home,
        ["runGameTestServer"],
        log=log,
        timeout_seconds=timeout_seconds,
    )
    return verify_gametest_log(log)


def verify_gametest_log(log: Path) -> int:
    text = log.read_text(encoding="utf-8", errors="replace")
    fatal_signatures = (
        "Failed to start the minecraft server",
        "Mod loading failures have occurred",
        "Crash report saved to:",
    )
    for signature in fatal_signatures:
        if signature in text:
            raise RuntimeError(
                f"GameTest runtime failed before completion ({signature!r}); see {log}"
            )

    discovered = re.search(r"\b(\d+) tests are now running\b", text)
    if discovered is None or int(discovered.group(1)) == 0:
        raise RuntimeError(f"GameTest runtime did not discover any tests; see {log}")
    count = int(discovered.group(1))

    passed = re.search(r"\bAll (\d+) required tests passed\b", text)
    if passed is None or "Game test server shutting down" not in text:
        raise RuntimeError(f"GameTests did not complete successfully; see {log}")
    return count

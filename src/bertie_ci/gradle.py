from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from .process import run


def run_gradle(
    project: Path,
    java_home: Path,
    tasks: Sequence[str],
    *,
    log: Path | None = None,
    timeout_seconds: int | None = None,
) -> None:
    wrapper = project / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if not wrapper.is_file():
        raise RuntimeError(f"Gradle wrapper not found in {project}")

    command: list[str | Path] = [
        wrapper,
        *tasks,
        "--no-daemon",
        "--stacktrace",
    ]
    if os.name != "nt":
        command.insert(0, os.environ.get("BERTIE_CI_SHELL", "sh"))
    run(
        command,
        cwd=project,
        env={**os.environ, "JAVA_HOME": os.fspath(java_home)},
        log=log,
        timeout_seconds=timeout_seconds,
    )


def build_mod(project: Path, java_home: Path) -> None:
    run_gradle(project, java_home, ["build"])


def run_gametests(
    project: Path, java_home: Path, work: Path, timeout_seconds: int
) -> None:
    work.mkdir(parents=True, exist_ok=True)
    run_gradle(
        project,
        java_home,
        ["runGameTestServer"],
        log=work / "gametest.log",
        timeout_seconds=timeout_seconds,
    )

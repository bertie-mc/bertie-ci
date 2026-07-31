from __future__ import annotations

import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Tools


def _reserve_display() -> tuple[int, Path]:
    temporary = Path(tempfile.gettempdir())
    for number in range(90, 200):
        lock = temporary / f"bertie-ci-xvfb-{number}.lock"
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(descriptor)
        return number, lock
    raise RuntimeError("No free Xvfb display number is available")


def _check_glx(tools: Tools, environment: dict[str, str]) -> None:
    if tools.glxinfo is None:
        return
    result = subprocess.run(
        [tools.glxinfo, "-B"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Virtual OpenGL preflight failed: {detail}")
    summary = next(
        (
            line.strip()
            for line in result.stdout.splitlines()
            if "OpenGL renderer string" in line
        ),
        "OpenGL available",
    )
    print(f"Virtual display ready: {summary}", flush=True)


@contextmanager
def virtual_display(tools: Tools, log: Path) -> Iterator[dict[str, str]]:
    environment = {**os.environ, "LIBGL_ALWAYS_SOFTWARE": "true"}
    if tools.xvfb is None:
        if os.name != "nt" and not environment.get("DISPLAY"):
            raise RuntimeError(
                "No display is available; supply BERTIE_CI_XVFB or DISPLAY"
            )
        yield environment
        return

    number, lock = _reserve_display()
    display = f":{number}"
    environment["DISPLAY"] = display
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8", errors="replace") as output:
        process = subprocess.Popen(
            [
                tools.xvfb,
                display,
                "-screen",
                "0",
                "1280x720x24",
                "+extension",
                "GLX",
                "+render",
                "-noreset",
                "-ac",
            ],
            stdout=output,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError(f"Xvfb exited early; see {log}")
                socket = Path("/tmp/.X11-unix") / f"X{number}"
                if socket.exists():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(f"Xvfb did not become ready; see {log}")
            _check_glx(tools, environment)
            yield environment
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
            lock.unlink(missing_ok=True)

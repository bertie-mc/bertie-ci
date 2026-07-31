from __future__ import annotations

import os
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import Tools, Versions
from .display import virtual_display
from .fixture import install_fixtures
from .process import run
from .properties import write_properties


def _clear_readonly(func: Callable[[str], Any], target: str, _error: Any) -> None:
    os.chmod(target, stat.S_IWRITE)
    func(target)


def _remove_tree(path: Path) -> None:
    """Delete a runtime tree, tolerating read-only files.

    Windows refuses to unlink a read-only file; POSIX only consults the parent
    directory, so this only ever matters there.
    """
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_clear_readonly)
    else:
        shutil.rmtree(path, onerror=_clear_readonly)


@dataclass(frozen=True)
class Context:
    work: Path
    cache: Path
    artifact: Path
    versions: Versions
    tools: Tools


def _reset_runtime(work: Path, name: str) -> Path:
    runtime = (work / name).resolve()
    if runtime.parent != work.resolve():
        raise RuntimeError(f"Unsafe runtime directory: {runtime}")
    for child in (runtime / "run", runtime / "HeadlessMC"):
        if child.exists():
            _remove_tree(child)
    log = runtime / "runtime.log"
    if log.exists():
        log.unlink()
    (runtime / "run" / "mods").mkdir(parents=True, exist_ok=True)
    (runtime / "HeadlessMC").mkdir(parents=True, exist_ok=True)
    return runtime


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _java(context: Context) -> list[Path | str]:
    return [context.tools.java, "-jar", context.tools.headlessmc]


def _install_client(context: Context, runtime: Path, minecraft: Path) -> None:
    vanilla_json = (
        minecraft
        / "versions"
        / context.versions.minecraft
        / f"{context.versions.minecraft}.json"
    )
    if not vanilla_json.is_file():
        run(
            [*_java(context), "--command", "download", context.versions.minecraft],
            cwd=runtime,
            log=runtime / "minecraft-download.log",
            stream_output=False,
        )

    loader = f"neoforge-{context.versions.neoforge}"
    loader_json = minecraft / "versions" / loader / f"{loader}.json"
    if not loader_json.is_file():
        run(
            [
                *_java(context),
                "--command",
                "neoforge",
                context.versions.minecraft,
                "--uid",
                context.versions.neoforge,
            ],
            cwd=runtime,
            log=runtime / "neoforge-client-install.log",
            stream_output=False,
        )


def run_client(
    context: Context, fixture_profiles: list[str], timeout_seconds: int
) -> None:
    runtime = _reset_runtime(context.work, "client")
    minecraft = (context.cache / "minecraft").resolve()
    minecraft.mkdir(parents=True, exist_ok=True)
    install_fixtures(
        context.tools, context.versions, runtime, fixture_profiles, "client"
    )
    shutil.copy2(context.artifact, runtime / "run" / "mods" / "mod-under-test.jar")
    shutil.copy2(
        context.tools.mc_runtime_test, runtime / "run" / "mods" / "mc-runtime-test.jar"
    )

    write_properties(
        runtime / "HeadlessMC" / "config.properties",
        {
            "hmc.java.versions": context.tools.java,
            "hmc.jvmargs": "-Xms512M -Xmx4G -DMcRuntimeGameTestMinExpectedGameTests=0",
            "hmc.gamedir": runtime / "run",
            "hmc.mcdir": minecraft,
            "hmc.offline": "true",
            "hmc.assets.dummy": "true",
            "hmc.check.xvfb": str(context.tools.xvfb is not None).lower(),
            "hmc.jline.enabled": "false",
            "hmc.rethrow.launch.exceptions": "true",
            "hmc.exit.on.failed.command": "true",
            "hmc.crash.report.watcher": "true",
            "hmc.loglevel": "INFO",
        },
    )
    _write(
        runtime / "run" / "options.txt",
        ["onboardAccessibility:false", "pauseOnLostFocus:false"],
    )
    # NeoForge's early-loading splash is a second GL surface the world-join probe
    # never needs. FML corrects this file with its remaining defaults on startup.
    _write(runtime / "run" / "config" / "fml.toml", ["earlyWindowControl = false"])
    _install_client(context, runtime, minecraft)

    loader = f"^neoforge-{context.versions.neoforge}$"
    command: list[str | Path] = [
        *_java(context),
        "--command",
        "launch",
        loader,
        "-regex",
    ]
    print("Launching client world-join probe", flush=True)
    with virtual_display(context.tools, runtime / "xvfb.log") as environment:
        run(
            command,
            cwd=runtime,
            env=environment,
            log=runtime / "runtime.log",
            timeout_seconds=timeout_seconds,
        )
    print(f"Client world-join probe passed. Logs: {runtime}", flush=True)


def run_server(
    context: Context, fixture_profiles: list[str], timeout_seconds: int
) -> None:
    runtime = _reset_runtime(context.work, "server")
    minecraft = (context.cache / "minecraft").resolve()
    minecraft.mkdir(parents=True, exist_ok=True)
    install_fixtures(
        context.tools, context.versions, runtime, fixture_profiles, "server"
    )
    shutil.copy2(context.artifact, runtime / "run" / "mods" / "mod-under-test.jar")

    write_properties(
        runtime / "HeadlessMC" / "config.properties",
        {
            "hmc.java.versions": context.tools.java,
            "hmc.jvmargs": "-Xms512M -Xmx3G",
            "hmc.mcdir": minecraft,
            "hmc.server.test.dir": runtime / "run",
            "hmc.server.test.type": "neoforge",
            "hmc.server.test.version": context.versions.minecraft,
            "hmc.offline": "true",
            "hmc.jline.enabled": "false",
            "hmc.rethrow.launch.exceptions": "true",
            "hmc.exit.on.failed.command": "true",
            "hmc.server.launch.for.eula": "true",
            "hmc.server.accept.eula": "true",
            "hmc.server.test": "true",
            "hmc.server.test.cache": "true",
            "hmc.server.test.cache.use.mc.dir": "true",
            "hmc.crash.report.watcher": "true",
            "hmc.loglevel": "INFO",
        },
    )

    print(f"Installing exact NeoForge server {context.versions.neoforge}", flush=True)
    run(
        [
            *_java(context),
            "--command",
            "server",
            "add",
            "neoforge",
            context.versions.minecraft,
            "bertie-ci",
            context.versions.neoforge,
        ],
        cwd=runtime,
        log=runtime / "neoforge-server-install.log",
        stream_output=False,
    )
    print("Launching dedicated-server readiness probe", flush=True)
    run(
        [*_java(context), "--command", "server", "launch", "0", "-id"],
        cwd=runtime,
        log=runtime / "runtime.log",
        timeout_seconds=timeout_seconds,
    )
    print(f"Dedicated-server probe passed. Logs: {runtime}", flush=True)

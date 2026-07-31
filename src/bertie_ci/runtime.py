from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import Tools, Versions
from .display import virtual_display
from .fixture import install_fixtures
from .process import run


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
            shutil.rmtree(child)
    log = runtime / "runtime.log"
    if log.exists():
        log.unlink()
    (runtime / "run" / "mods").mkdir(parents=True, exist_ok=True)
    (runtime / "HeadlessMC").mkdir(parents=True, exist_ok=True)
    return runtime


def _write(path: Path, lines: list[str]) -> None:
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

    _write(
        runtime / "HeadlessMC" / "config.properties",
        [
            f"hmc.java.versions={context.tools.java}",
            "hmc.jvmargs=-Xms512M -Xmx4G -DMcRuntimeGameTestMinExpectedGameTests=0",
            f"hmc.gamedir={runtime / 'run'}",
            f"hmc.mcdir={minecraft}",
            "hmc.offline=true",
            "hmc.assets.dummy=true",
            f"hmc.check.xvfb={str(context.tools.xvfb is not None).lower()}",
            "hmc.jline.enabled=false",
            "hmc.rethrow.launch.exceptions=true",
            "hmc.exit.on.failed.command=true",
            "hmc.crash.report.watcher=true",
            "hmc.loglevel=INFO",
        ],
    )
    _write(
        runtime / "run" / "options.txt",
        ["onboardAccessibility:false", "pauseOnLostFocus:false"],
    )
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

    _write(
        runtime / "HeadlessMC" / "config.properties",
        [
            f"hmc.java.versions={context.tools.java}",
            "hmc.jvmargs=-Xms512M -Xmx3G",
            f"hmc.mcdir={minecraft}",
            f"hmc.server.test.dir={runtime / 'run'}",
            "hmc.server.test.type=neoforge",
            f"hmc.server.test.version={context.versions.minecraft}",
            "hmc.offline=true",
            "hmc.jline.enabled=false",
            "hmc.rethrow.launch.exceptions=true",
            "hmc.exit.on.failed.command=true",
            "hmc.server.launch.for.eula=true",
            "hmc.server.accept.eula=true",
            "hmc.server.test=true",
            "hmc.server.test.cache=true",
            "hmc.server.test.cache.use.mc.dir=true",
            "hmc.crash.report.watcher=true",
            "hmc.loglevel=INFO",
        ],
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

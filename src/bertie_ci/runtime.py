from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Tools, Versions
from .display import virtual_display
from .filesystem import remove_file, remove_tree, replace_file
from .instance import Instance
from .process import run
from .properties import write_properties


_SERVER_TEST_SUCCESS = "CommandTest was successful."


@dataclass(frozen=True)
class ProbeContext:
    work: Path
    cache: Path
    instance: Instance
    supported: Versions
    tools: Tools


def _reset_probe(work: Path) -> Path:
    work = work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    control = work / "HeadlessMC"
    if control.exists():
        remove_tree(control)
    control.mkdir()
    for name in (
        "runtime.log",
        "minecraft-download.log",
        "neoforge-client-install.log",
        "neoforge-server-install.log",
        "xvfb.log",
    ):
        remove_file(work / name)
    return work


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _java(context: ProbeContext) -> list[Path | str]:
    return [context.tools.java, "-jar", context.tools.headlessmc]


def _assert_compatible(context: ProbeContext, side: str) -> None:
    instance = context.instance
    if instance.side != side:
        raise RuntimeError(
            f"{side} probe cannot consume a {instance.side} prepared instance"
        )
    if instance.loader != "neoforge":
        raise RuntimeError(f"Unsupported loader: {instance.loader}")
    expected = (context.supported.minecraft, context.supported.neoforge)
    actual = (instance.minecraft, instance.loader_version)
    if actual != expected:
        raise RuntimeError(
            "Prepared instance uses Minecraft/NeoForge "
            f"{actual[0]}/{actual[1]}, but this bertie-ci release supports "
            f"{expected[0]}/{expected[1]}"
        )


def _install_client(context: ProbeContext, minecraft: Path) -> None:
    instance = context.instance
    vanilla_json = (
        minecraft / "versions" / instance.minecraft / f"{instance.minecraft}.json"
    )
    if not vanilla_json.is_file():
        run(
            [*_java(context), "--command", "download", instance.minecraft],
            cwd=context.work,
            log=context.work / "minecraft-download.log",
            stream_output=False,
        )

    loader = f"neoforge-{instance.loader_version}"
    loader_json = minecraft / "versions" / loader / f"{loader}.json"
    if not loader_json.is_file():
        run(
            [
                *_java(context),
                "--command",
                "neoforge",
                instance.minecraft,
                "--uid",
                instance.loader_version,
            ],
            cwd=context.work,
            log=context.work / "neoforge-client-install.log",
            stream_output=False,
        )


def _set_options(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    retained = [line for line in lines if line.partition(":")[0] not in values]
    retained.extend(f"{key}:{value}" for key, value in values.items())
    _write(path, retained)


def _accept_minecraft_eula(game_dir: Path) -> None:
    """Accept the EULA without launching a disposable server first."""
    _write(
        game_dir / "eula.txt",
        [
            "# Accepted by the explicitly requested bertie-ci server probe.",
            "# https://aka.ms/MinecraftEULA",
            "eula=true",
        ],
    )


def _write_server_readiness_test(work: Path, timeout_seconds: int) -> Path:
    """Create a HeadlessMC test whose success boundary is server readiness."""
    # HeadlessMC otherwise applies an independent 120-second default to the
    # readiness marker. Keep enough of the command deadline for its process
    # cleanup after the test sends ``stop``.
    readiness_timeout = max(1, timeout_seconds - 150)
    target = work / "server-readiness-test.json"
    target.write_text(
        json.dumps(
            {
                "name": "Bertie server readiness",
                "timeout": readiness_timeout,
                "implicitWaitForEnd": False,
                "steps": [
                    {
                        "type": "ENDS_WITH",
                        "message": 'For help, type "help"',
                    },
                    {"type": "SEND", "message": "stop"},
                    {"type": "SUCCESS"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def _server_readiness_was_recorded(runtime_log: Path) -> bool:
    return runtime_log.is_file() and _SERVER_TEST_SUCCESS in runtime_log.read_text(
        encoding="utf-8", errors="replace"
    )


def run_client_probe(
    context: ProbeContext, timeout_seconds: int, max_memory: str
) -> None:
    _assert_compatible(context, "client")
    work = _reset_probe(context.work)
    game_dir = context.instance.game_dir
    mods = game_dir / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    replace_file(context.tools.mc_runtime_test, mods / "bertie-ci-mc-runtime-test.jar")
    minecraft = (context.cache / "minecraft").resolve()
    minecraft.mkdir(parents=True, exist_ok=True)

    write_properties(
        work / "HeadlessMC" / "config.properties",
        {
            "hmc.java.versions": context.tools.java,
            "hmc.jvmargs": f"-Xms512M -Xmx{max_memory} -DMcRuntimeGameTestMinExpectedGameTests=0",
            "hmc.gamedir": game_dir,
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
    _set_options(
        game_dir / "options.txt",
        {"onboardAccessibility": "false", "pauseOnLostFocus": "false"},
    )
    # NeoForge's early-loading splash is a second GL surface the world-join probe
    # never needs. Do not replace a pack's existing FML configuration.
    fml_config = game_dir / "config" / "fml.toml"
    if not fml_config.is_file():
        _write(fml_config, ["earlyWindowControl = false"])
    _install_client(context, minecraft)

    loader = f"^neoforge-{context.instance.loader_version}$"
    print("Launching client world-join probe", flush=True)
    with virtual_display(context.tools, work / "xvfb.log") as environment:
        run(
            [*_java(context), "--command", "launch", loader, "-regex"],
            cwd=work,
            env=environment,
            log=work / "runtime.log",
            timeout_seconds=timeout_seconds,
        )
    print(f"Client world-join probe passed. Logs: {work}", flush=True)


def run_server_probe(
    context: ProbeContext, timeout_seconds: int, max_memory: str
) -> None:
    _assert_compatible(context, "server")
    work = _reset_probe(context.work)
    game_dir = context.instance.game_dir
    minecraft = (context.cache / "minecraft").resolve()
    minecraft.mkdir(parents=True, exist_ok=True)
    readiness_test = _write_server_readiness_test(work, timeout_seconds)

    write_properties(
        work / "HeadlessMC" / "config.properties",
        {
            "hmc.java.versions": context.tools.java,
            "hmc.jvmargs": f"-Xms512M -Xmx{max_memory}",
            "hmc.mcdir": minecraft,
            "hmc.server.test.dir": game_dir,
            "hmc.server.test.type": context.instance.loader,
            "hmc.server.test.version": context.instance.minecraft,
            "hmc.offline": "true",
            "hmc.jline.enabled": "false",
            "hmc.rethrow.launch.exceptions": "true",
            "hmc.exit.on.failed.command": "true",
            "hmc.server.launch.for.eula": "true",
            "hmc.server.accept.eula": "true",
            # The built-in server test waits for a clean shutdown. Our assertion
            # boundary is readiness; a large pack may spend minutes in work
            # scheduled immediately after printing Done. The custom test sends
            # stop but treats the readiness marker itself as success.
            "hmc.server.test": "false",
            "hmc.server.test.cache": "true",
            "hmc.server.test.cache.use.mc.dir": "true",
            "hmc.test.filename": readiness_test,
            "hmc.test.leave.after": "false",
            "hmc.crash.report.watcher": "true",
            "hmc.loglevel": "INFO",
        },
    )

    print(
        f"Installing exact NeoForge server {context.instance.loader_version}",
        flush=True,
    )
    run(
        [
            *_java(context),
            "--command",
            "server",
            "add",
            context.instance.loader,
            context.instance.minecraft,
            "bertie-ci",
            context.instance.loader_version,
        ],
        cwd=work,
        log=work / "neoforge-server-install.log",
        stream_output=False,
    )
    # HeadlessMC can create this by launching the server once before the real
    # readiness run. A large modpack can fill that preliminary process's output
    # pipe during mod discovery, so provision the same accepted state directly.
    _accept_minecraft_eula(game_dir)
    print("Launching dedicated-server readiness probe", flush=True)
    runtime_log = work / "runtime.log"
    try:
        run(
            [*_java(context), "--command", "server", "launch", "0", "-id"],
            cwd=work,
            log=runtime_log,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.CalledProcessError:
        # HeadlessMC waits for the child after the readiness test succeeds. A
        # large pack can exceed its two-minute shutdown grace period and be
        # force-terminated, producing a non-zero child status. Readiness is the
        # probe contract, so only accept that status when HeadlessMC itself
        # recorded the successful test first.
        if not _server_readiness_was_recorded(runtime_log):
            raise
        print(
            "Readiness passed; ignoring the server's post-readiness exit status.",
            flush=True,
        )
    print(f"Dedicated-server probe passed. Logs: {work}", flush=True)

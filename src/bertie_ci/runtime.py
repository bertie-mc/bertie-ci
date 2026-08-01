from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import ClientRuntimeTools, ServerRuntimeTools, Versions
from .display import virtual_display
from .filesystem import remove_file, remove_tree, replace_file
from .instance import Instance
from .process import run
from .properties import write_properties

_COMMAND_TEST_SUCCESS = "CommandTest was successful."


@dataclass(frozen=True)
class RuntimeContext:
    work: Path
    cache: Path
    instance: Instance
    supported: Versions
    tools: ServerRuntimeTools


def _reset_runtime(work: Path) -> Path:
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


def _java(context: RuntimeContext) -> list[Path | str]:
    return [context.tools.java, "-jar", context.tools.headlessmc]


def _assert_compatible(context: RuntimeContext, side: str) -> None:
    instance = context.instance
    if instance.side != side:
        raise RuntimeError(
            f"{side} test cannot consume a {instance.side} prepared instance"
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


def _install_client(context: RuntimeContext, minecraft: Path) -> None:
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
            "# Accepted by the explicitly requested bertie-ci server test.",
            "# https://aka.ms/MinecraftEULA",
            "eula=true",
        ],
    )


def _write_server_readiness_test(work: Path, timeout_seconds: int) -> Path:
    """Create a HeadlessMC test whose success boundary is server readiness."""
    # HeadlessMC otherwise applies an independent 120-second default to the
    # readiness marker. Keep enough of the command deadline for its process
    # cleanup after the test sends ``stop``.
    cleanup_margin = min(150, max(1, timeout_seconds // 10))
    readiness_timeout = max(1, timeout_seconds - cleanup_margin)
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


def _command_test_was_recorded(runtime_log: Path) -> bool:
    return runtime_log.is_file() and _COMMAND_TEST_SUCCESS in runtime_log.read_text(
        encoding="utf-8", errors="replace"
    )


def _resolve_test_mod(test_mod: Path) -> Path:
    source = test_mod.resolve(strict=True)
    if source.is_dir():
        candidates = sorted(
            path.resolve(strict=True)
            for path in source.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".jar"
            and not path.name.lower().endswith(("-sources.jar", "-javadoc.jar"))
        )
        if len(candidates) != 1:
            raise RuntimeError(
                f"Expected one test mod JAR in {source}, found {len(candidates)}"
            )
        source = candidates[0]
    if not source.is_file() or source.suffix.lower() != ".jar":
        raise RuntimeError(f"Test mod is not a JAR: {source}")
    return source


def _install_test_mods(mods: Path, test_mods: tuple[Path, ...]) -> None:
    sources = tuple(_resolve_test_mod(test_mod) for test_mod in test_mods)
    mods.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".bertie-ci-test-", dir=mods) as temporary:
        staged = []
        for index, source in enumerate(sources, start=1):
            target = Path(temporary) / f"bertie-ci-test-{index}.jar"
            shutil.copy2(source, target)
            staged.append(target)

        for pattern in ("bertie-ci-test-*.jar", "bertie-ci-client-test-*.jar"):
            for stale in mods.glob(pattern):
                remove_file(stale)
        for source in staged:
            replace_file(source, mods / source.name)


def _assert_required_log_markers(
    runtime_log: Path, required_log_markers: tuple[str, ...]
) -> None:
    if not required_log_markers:
        return
    text = runtime_log.read_text(encoding="utf-8", errors="replace")
    missing = [marker for marker in required_log_markers if marker not in text]
    if missing:
        formatted = ", ".join(repr(marker) for marker in missing)
        raise RuntimeError(f"Runtime log is missing required marker(s): {formatted}")


def run_client_test(
    context: RuntimeContext,
    timeout_seconds: int,
    max_memory: str,
    *,
    minimum_game_tests: int = 0,
    test_mods: tuple[Path, ...] = (),
    required_log_markers: tuple[str, ...] = (),
) -> None:
    if minimum_game_tests < 0:
        raise RuntimeError("minimum_game_tests cannot be negative")
    _assert_compatible(context, "client")
    if not isinstance(context.tools, ClientRuntimeTools):
        raise RuntimeError("Client runtime tools are required for a client test")
    work = _reset_runtime(context.work)
    game_dir = context.instance.game_dir
    mods = game_dir / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    replace_file(context.tools.mc_runtime_test, mods / "bertie-ci-mc-runtime-test.jar")
    _install_test_mods(mods, test_mods)
    minecraft = (context.cache / "minecraft").resolve()
    minecraft.mkdir(parents=True, exist_ok=True)

    write_properties(
        work / "HeadlessMC" / "config.properties",
        {
            "hmc.java.versions": context.tools.java,
            "hmc.jvmargs": (
                f"-Xms512M -Xmx{max_memory} "
                f"-DMcRuntimeGameTestMinExpectedGameTests={minimum_game_tests}"
            ),
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
    # NeoForge's early-loading splash is a second GL surface the world-join test
    # never needs. Do not replace a pack's existing FML configuration.
    fml_config = game_dir / "config" / "fml.toml"
    if not fml_config.is_file():
        _write(fml_config, ["earlyWindowControl = false"])
    _install_client(context, minecraft)

    loader = f"^neoforge-{context.instance.loader_version}$"
    if minimum_game_tests > 0:
        assertions = f"{minimum_game_tests}+ GameTests"
    elif required_log_markers:
        assertions = f"{len(required_log_markers)} project assertion marker(s)"
    else:
        assertions = "world join"
    purpose = f"client runtime ({assertions})"
    runtime_log = work / "runtime.log"
    print(f"Launching client {purpose}", flush=True)
    with virtual_display(context.tools, work / "xvfb.log") as environment:
        run(
            [*_java(context), "--command", "launch", loader, "-regex"],
            cwd=work,
            env=environment,
            log=runtime_log,
            timeout_seconds=timeout_seconds,
        )
    _assert_required_log_markers(runtime_log, required_log_markers)
    print(f"Client {purpose} passed. Logs: {work}", flush=True)


def run_server_test(
    context: RuntimeContext,
    timeout_seconds: int,
    max_memory: str,
    *,
    command_test: Path | None = None,
    test_mods: tuple[Path, ...] = (),
    required_log_markers: tuple[str, ...] = (),
) -> None:
    _assert_compatible(context, "server")
    work = _reset_runtime(context.work)
    game_dir = context.instance.game_dir
    _install_test_mods(game_dir / "mods", test_mods)
    minecraft = (context.cache / "minecraft").resolve()
    minecraft.mkdir(parents=True, exist_ok=True)
    test = (
        command_test.resolve(strict=True)
        if command_test is not None
        else _write_server_readiness_test(work, timeout_seconds)
    )

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
            "hmc.test.filename": test,
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
    purpose = "readiness" if command_test is None else "project command suite"
    print(f"Launching dedicated-server {purpose}", flush=True)
    runtime_log = work / "runtime.log"
    try:
        run(
            [*_java(context), "--command", "server", "launch", "0", "-id"],
            cwd=work,
            log=runtime_log,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.CalledProcessError:
        # HeadlessMC waits for the child after its command test succeeds. A large
        # pack can exceed the two-minute shutdown grace period and be force-
        # terminated after the selected scenario has already passed. The command
        # test is the success boundary for default and project-owned scenarios.
        if not _command_test_was_recorded(runtime_log):
            raise
        print(
            "Server scenario passed; ignoring its post-success exit status.",
            flush=True,
        )
    if not _command_test_was_recorded(runtime_log):
        raise RuntimeError(
            f"Dedicated-server {purpose} did not report scenario success; see {runtime_log}"
        )
    _assert_required_log_markers(runtime_log, required_log_markers)
    print(f"Dedicated-server {purpose} passed. Logs: {work}", flush=True)

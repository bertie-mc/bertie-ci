import json
import os
import stat
import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest

import bertie_ci.runtime as runtime_module
from bertie_ci.config import ClientRuntimeTools, ServerRuntimeTools, Versions
from bertie_ci.instance import Instance
from bertie_ci.runtime import (
    RuntimeContext,
    _accept_minecraft_eula,
    _assert_compatible,
    _install_test_mods,
    _reset_runtime,
    _set_options,
    _write_server_readiness_test,
    run_client_test,
    run_server_test,
)

VERSIONS = Versions("1.21.1", "21.1.233", "21", "2.10.0", "4.5.1", "0.5.14")


def _tool_file(root: Path, name: str, content: bytes = b"tool") -> Path:
    path = root / "tools" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _context(tmp_path: Path, side: str) -> RuntimeContext:
    work = tmp_path / "work"
    game_dir = work / "instance"
    game_dir.mkdir(parents=True)
    java = _tool_file(tmp_path, "java")
    headlessmc = _tool_file(tmp_path, "headlessmc.jar")
    if side == "client":
        tools = ClientRuntimeTools(
            java,
            headlessmc,
            _tool_file(tmp_path, "mc-runtime-test.jar", b"runtime test"),
            None,
            None,
        )
    else:
        tools = ServerRuntimeTools(java, headlessmc)
    return RuntimeContext(
        work,
        tmp_path / "cache",
        Instance(side, game_dir, "1.21.1", "neoforge", "21.1.233"),
        VERSIONS,
        tools,
    )


def _cache_client_install(context: RuntimeContext) -> None:
    versions = context.cache / "minecraft" / "versions"
    vanilla = versions / "1.21.1" / "1.21.1.json"
    neoforge = versions / "neoforge-21.1.233" / "neoforge-21.1.233.json"
    vanilla.parent.mkdir(parents=True)
    neoforge.parent.mkdir(parents=True)
    vanilla.write_text("{}", encoding="utf-8")
    neoforge.write_text("{}", encoding="utf-8")


def test_reset_runtime_preserves_prepared_instance(tmp_path: Path) -> None:
    work = tmp_path / "work"
    instance = work / "instance"
    instance.mkdir(parents=True)
    sibling = instance / "keep.txt"
    sibling.write_text("keep", encoding="utf-8")
    control = work / "HeadlessMC"
    control.mkdir()
    (control / "old.log").touch()
    (work / "runtime.log").touch()

    result = _reset_runtime(work)

    assert result == work.resolve()
    assert not (control / "old.log").exists()
    assert control.is_dir()
    assert not (work / "runtime.log").exists()
    assert sibling.read_text(encoding="utf-8") == "keep"


def test_reset_runtime_replaces_read_only_control_files(tmp_path: Path) -> None:
    """Windows refuses to unlink a read-only file; a stale run must still clear."""
    work = tmp_path / "work"
    control = work / "HeadlessMC"
    control.mkdir(parents=True)
    stale = control / "config.properties"
    stale.write_text("stale", encoding="utf-8")
    os.chmod(stale, stat.S_IREAD)

    try:
        runtime = _reset_runtime(work)
    finally:
        if stale.exists():
            os.chmod(stale, stat.S_IWRITE)

    assert not stale.exists()
    assert (runtime / "HeadlessMC").is_dir()


def test_set_options_replaces_runner_values_and_preserves_pack_values(
    tmp_path: Path,
) -> None:
    options = tmp_path / "options.txt"
    options.write_text(
        "onboardAccessibility:true\nrenderDistance:12\n", encoding="utf-8"
    )

    _set_options(
        options, {"onboardAccessibility": "false", "pauseOnLostFocus": "false"}
    )

    assert options.read_text(encoding="utf-8").splitlines() == [
        "renderDistance:12",
        "onboardAccessibility:false",
        "pauseOnLostFocus:false",
    ]


def test_accept_minecraft_eula_avoids_preliminary_server_launch(
    tmp_path: Path,
) -> None:
    _accept_minecraft_eula(tmp_path)

    assert (tmp_path / "eula.txt").read_text(encoding="utf-8").splitlines()[-1] == (
        "eula=true"
    )


def test_server_readiness_test_does_not_require_clean_shutdown(
    tmp_path: Path,
) -> None:
    test = json.loads(
        _write_server_readiness_test(tmp_path, 4500).read_text(encoding="utf-8")
    )

    assert test["timeout"] == 4350
    assert test["implicitWaitForEnd"] is False
    assert [step["type"] for step in test["steps"]] == [
        "ENDS_WITH",
        "SEND",
        "SUCCESS",
    ]


def test_server_readiness_timeout_keeps_cleanup_margin(tmp_path: Path) -> None:
    test = json.loads(
        _write_server_readiness_test(tmp_path, 120).read_text(encoding="utf-8")
    )

    assert test["timeout"] == 108


def test_test_mod_injection_replaces_previous_extensions(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / "provider-owned.jar").write_bytes(b"provider")
    (mods / "bertie-ci-test-2.jar").write_bytes(b"stale")
    (mods / "bertie-ci-client-test-1.jar").write_bytes(b"legacy")
    first = tmp_path / "first.jar"
    second = tmp_path / "second.JAR"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    _install_test_mods(mods, (first, second))

    assert (mods / "provider-owned.jar").read_bytes() == b"provider"
    assert not (mods / "bertie-ci-client-test-1.jar").exists()
    assert (mods / "bertie-ci-test-1.jar").read_bytes() == b"first"
    assert (mods / "bertie-ci-test-2.jar").read_bytes() == b"second"

    _install_test_mods(mods, ())

    assert not list(mods.glob("bertie-ci-test-*.jar"))
    assert (mods / "provider-owned.jar").is_file()


def test_test_mod_rejects_non_jar(tmp_path: Path) -> None:
    test_mod = tmp_path / "test-mod.zip"
    test_mod.touch()

    with pytest.raises(RuntimeError, match="not a JAR"):
        _install_test_mods(tmp_path / "mods", (test_mod,))


def test_test_mod_directory_resolves_one_jar_and_ignores_sources(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "assertions.jar").write_bytes(b"assertions")
    (artifact / "assertions-sources.jar").write_bytes(b"sources")

    _install_test_mods(tmp_path / "mods", (artifact,))

    assert (tmp_path / "mods" / "bertie-ci-test-1.jar").read_bytes() == b"assertions"


def test_invalid_test_mod_does_not_remove_previous_extensions(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    previous = mods / "bertie-ci-test-1.jar"
    previous.write_bytes(b"previous")
    valid = tmp_path / "valid.jar"
    invalid = tmp_path / "invalid.zip"
    valid.write_bytes(b"valid")
    invalid.write_bytes(b"invalid")

    with pytest.raises(RuntimeError, match="not a JAR"):
        _install_test_mods(mods, (valid, invalid))

    assert previous.read_bytes() == b"previous"


def test_test_mod_can_be_reinstalled_from_runner_owned_path(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    staged = mods / "bertie-ci-test-1.jar"
    staged.write_bytes(b"assertions")

    _install_test_mods(mods, (staged,))

    assert staged.read_bytes() == b"assertions"


def test_client_test_defaults_to_world_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, "client")
    _cache_client_install(context)
    invocations: list[list[str | Path]] = []

    def fake_run(command: list[str | Path], **kwargs: object) -> None:
        invocations.append(command)
        log = kwargs.get("log")
        if isinstance(log, Path):
            log.write_text("client joined world\n", encoding="utf-8")

    monkeypatch.setattr(runtime_module, "run", fake_run)
    monkeypatch.setattr(runtime_module, "virtual_display", lambda *_: nullcontext({}))

    run_client_test(context, 120, "4G")

    assert len(invocations) == 1
    assert "launch" in invocations[0]
    assert (
        context.instance.game_dir / "mods" / "bertie-ci-mc-runtime-test.jar"
    ).is_file()
    properties = (context.work / "HeadlessMC" / "config.properties").read_text(
        encoding="ascii"
    )
    assert "McRuntimeGameTestMinExpectedGameTests=0" in properties


def test_client_test_composes_project_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, "client")
    _cache_client_install(context)
    test_mod = tmp_path / "client-tests.jar"
    test_mod.write_bytes(b"client assertions")

    def fake_run(_command: list[str | Path], **kwargs: object) -> None:
        log = kwargs.get("log")
        assert isinstance(log, Path)
        log.write_text("CLIENT_ASSERTIONS_OK\n", encoding="utf-8")

    monkeypatch.setattr(runtime_module, "run", fake_run)
    monkeypatch.setattr(runtime_module, "virtual_display", lambda *_: nullcontext({}))

    run_client_test(
        context,
        120,
        "4G",
        minimum_game_tests=2,
        test_mods=(test_mod,),
        required_log_markers=("CLIENT_ASSERTIONS_OK",),
    )

    staged = context.instance.game_dir / "mods" / "bertie-ci-test-1.jar"
    assert staged.read_bytes() == b"client assertions"
    properties = (context.work / "HeadlessMC" / "config.properties").read_text(
        encoding="ascii"
    )
    assert "McRuntimeGameTestMinExpectedGameTests=2" in properties

    with pytest.raises(RuntimeError, match="MISSING_CLIENT_ASSERTION"):
        run_client_test(
            context,
            120,
            "4G",
            required_log_markers=("MISSING_CLIENT_ASSERTION",),
        )


def test_server_test_defaults_to_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, "server")
    invocations: list[list[str | Path]] = []

    def fake_run(command: list[str | Path], **kwargs: object) -> None:
        invocations.append(command)
        log = kwargs.get("log")
        if isinstance(log, Path):
            log.write_text("CommandTest was successful.\n", encoding="utf-8")

    monkeypatch.setattr(runtime_module, "run", fake_run)

    run_server_test(context, 300, "3G")

    scenario = json.loads(
        (context.work / "server-readiness-test.json").read_text(encoding="utf-8")
    )
    assert [step["type"] for step in scenario["steps"]] == [
        "ENDS_WITH",
        "SEND",
        "SUCCESS",
    ]
    assert any("launch" in command for command in invocations)


def test_server_test_requires_explicit_success_record_on_zero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, "server")

    def fake_run(_command: list[str | Path], **kwargs: object) -> None:
        log = kwargs.get("log")
        if isinstance(log, Path):
            log.write_text("server exited normally\n", encoding="utf-8")

    monkeypatch.setattr(runtime_module, "run", fake_run)

    with pytest.raises(RuntimeError, match="did not report scenario success"):
        run_server_test(context, 300, "3G")


def test_server_test_composes_project_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _context(tmp_path, "server")
    command_test = tmp_path / "server.json"
    command_test.write_text('{"name":"project","steps":[]}', encoding="utf-8")
    test_mod = tmp_path / "server-tests.jar"
    test_mod.write_bytes(b"server assertions")

    def fake_run(_command: list[str | Path], **kwargs: object) -> None:
        log = kwargs.get("log")
        if isinstance(log, Path):
            log.write_text(
                "CommandTest was successful.\nSERVER_ASSERTIONS_OK\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(runtime_module, "run", fake_run)

    run_server_test(
        context,
        300,
        "3G",
        command_test=command_test,
        test_mods=(test_mod,),
        required_log_markers=("SERVER_ASSERTIONS_OK",),
    )

    assert command_test.read_text(encoding="utf-8") == '{"name":"project","steps":[]}'
    assert (
        context.instance.game_dir / "mods" / "bertie-ci-test-1.jar"
    ).read_bytes() == b"server assertions"
    properties = (context.work / "HeadlessMC" / "config.properties").read_text(
        encoding="ascii"
    )
    assert str(command_test) in properties


@pytest.mark.parametrize(
    "side,loader,loader_version,message",
    [
        ("server", "neoforge", "21.1.233", "client test cannot consume"),
        ("client", "fabric", "21.1.233", "Unsupported loader"),
        ("client", "neoforge", "21.1.217", "but this bertie-ci release supports"),
    ],
)
def test_runtime_rejects_incompatible_instance(
    tmp_path: Path,
    side: str,
    loader: str,
    loader_version: str,
    message: str,
) -> None:
    context = _context(tmp_path, side)
    context = RuntimeContext(
        context.work,
        context.cache,
        Instance(side, context.instance.game_dir, "1.21.1", loader, loader_version),
        context.supported,
        context.tools,
    )

    with pytest.raises(RuntimeError, match=message):
        _assert_compatible(context, "client")


@pytest.mark.parametrize("recorded", [True, False])
def test_server_accepts_only_recorded_post_success_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, recorded: bool
) -> None:
    context = _context(tmp_path, "server")

    def fake_run(command: list[str | Path], **kwargs: object) -> None:
        if "launch" not in command:
            return
        log = kwargs.get("log")
        assert isinstance(log, Path)
        log.write_text(
            "CommandTest was successful.\n" if recorded else "CommandTest failed.\n",
            encoding="utf-8",
        )
        raise subprocess.CalledProcessError(143, command)

    monkeypatch.setattr(runtime_module, "run", fake_run)

    if recorded:
        run_server_test(context, 300, "3G")
    else:
        with pytest.raises(subprocess.CalledProcessError):
            run_server_test(context, 300, "3G")

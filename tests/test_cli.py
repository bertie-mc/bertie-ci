import io
import sys
from pathlib import Path

import pytest

import bertie_ci.cli as cli
from bertie_ci.instance import Instance


def test_empty_adapter_path_means_omitted_optional_input() -> None:
    assert cli._optional_path("") is None
    assert cli._optional_path("build/client-tests.jar") == Path(
        "build/client-tests.jar"
    )


@pytest.mark.parametrize("value", ["0", "-1"])
def test_runtime_timeout_must_be_positive(value: str) -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            ["client-test", "--instance", "instance.json", "--timeout", value]
        )


def test_client_test_defaults_to_world_join(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = cli._parser().parse_args(
        [
            "client-test",
            "--instance",
            "instance.json",
            "--test-mod",
            "",
            "--require-log",
            "",
        ]
    )
    context = object()
    observed: dict[str, object] = {}
    monkeypatch.setattr(cli, "_runtime_context", lambda *_: context)

    def capture_test(*test_args: object, **test_kwargs: object) -> None:
        observed["args"] = test_args
        observed["kwargs"] = test_kwargs

    monkeypatch.setattr(cli, "run_client_test", capture_test)

    cli._run_test(args, "client")

    assert observed["args"] == (context, 1500, "4G")
    assert observed["kwargs"] == {
        "minimum_game_tests": 0,
        "test_mods": (),
        "required_log_markers": (),
    }


def test_server_test_composes_optional_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command_test = tmp_path / "server.json"
    test_mod = tmp_path / "server-tests.jar"
    args = cli._parser().parse_args(
        [
            "server-test",
            "--instance",
            "instance.json",
            "--command-test",
            str(command_test),
            "--test-mod",
            str(test_mod),
            "--require-log",
            "SERVER_ASSERTIONS_OK",
        ]
    )
    context = object()
    observed: dict[str, object] = {}
    monkeypatch.setattr(cli, "_runtime_context", lambda *_: context)

    def capture_test(*test_args: object, **test_kwargs: object) -> None:
        observed["args"] = test_args
        observed["kwargs"] = test_kwargs

    monkeypatch.setattr(cli, "run_server_test", capture_test)

    cli._run_test(args, "server")

    assert observed["args"] == (context, 900, "3G")
    assert observed["kwargs"] == {
        "command_test": command_test,
        "test_mods": (test_mod,),
        "required_log_markers": ("SERVER_ASSERTIONS_OK",),
    }


def test_runtime_context_rejects_wrong_side_before_loading_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = tmp_path / "instance.json"
    descriptor.touch()
    game_dir = tmp_path / "instance"
    game_dir.mkdir()
    instance = Instance("server", game_dir, "1.21.1", "neoforge", "21.1.233")
    loaded: list[str] = []
    monkeypatch.setattr(cli, "load_instance", lambda _path: instance)
    monkeypatch.setattr(
        cli, "load_client_runtime_tools", lambda: loaded.append("client")
    )
    monkeypatch.setattr(
        cli, "load_server_runtime_tools", lambda: loaded.append("server")
    )

    with pytest.raises(RuntimeError, match="client test cannot consume a server"):
        cli._runtime_context(descriptor, None, None, "client")

    assert loaded == []


def test_streams_survive_characters_outside_the_ansi_code_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirected stdout on Windows encodes as cp1252, and Minecraft logs do not."""
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)

    with pytest.raises(UnicodeEncodeError):
        stream.write("█ progress\n")
        stream.flush()

    cli.tolerate_unencodable_output()
    stream.write("█ progress\n")
    stream.flush()

    assert b"? progress" in buffer.getvalue()

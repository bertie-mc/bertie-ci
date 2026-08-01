import io
import sys
from pathlib import Path

import pytest

import bertie_ci.cli as cli


def test_empty_adapter_path_means_omitted_optional_input() -> None:
    assert cli._optional_path("") is None
    assert cli._optional_path("build/client-tests.jar") == Path(
        "build/client-tests.jar"
    )


def test_empty_client_action_inputs_are_omitted(
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
            "--minimum-game-tests",
            "1",
        ]
    )
    context = object()
    observed: dict[str, object] = {}
    monkeypatch.setattr(cli, "_probe_context", lambda *_: context)

    def capture_probe(*probe_args: object, **probe_kwargs: object) -> None:
        observed["args"] = probe_args
        observed["kwargs"] = probe_kwargs

    monkeypatch.setattr(cli, "run_client_probe", capture_probe)

    cli._run_probe(args, "client", project_owned=True)

    assert observed["args"] == (context, 1500, "4G")
    assert observed["kwargs"] == {
        "minimum_game_tests": 1,
        "test_mods": (),
        "required_log_markers": (),
    }


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

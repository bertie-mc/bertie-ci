from pathlib import Path

import pytest

from bertie_ci.config import (
    ClientRuntimeTools,
    PackTools,
    ServerRuntimeTools,
    load_client_runtime_tools,
    load_pack_tools,
    load_server_runtime_tools,
)


def _java_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "jdk"
    java = home / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.touch()
    monkeypatch.setenv("BERTIE_CI_JAVA_HOME", str(home))
    return java


def _tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, variable: str) -> Path:
    path = tmp_path / f"{variable.lower()}.jar"
    path.touch()
    monkeypatch.setenv(variable, str(path))
    return path


def test_server_runtime_tools_require_no_client_or_preparation_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    java = _java_home(tmp_path, monkeypatch)
    headlessmc = _tool(tmp_path, monkeypatch, "BERTIE_CI_HEADLESSMC_JAR")
    monkeypatch.delenv("BERTIE_CI_MCRT_JAR", raising=False)
    monkeypatch.delenv("BERTIE_CI_PACKWIZ_INSTALLER_JAR", raising=False)
    monkeypatch.delenv("BERTIE_CI_FIXTURES", raising=False)
    monkeypatch.delenv("BERTIE_CI_FIXTURE_PACK", raising=False)

    assert load_server_runtime_tools() == ServerRuntimeTools(java, headlessmc)


def test_client_runtime_tools_require_no_preparation_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    java = _java_home(tmp_path, monkeypatch)
    headlessmc = _tool(tmp_path, monkeypatch, "BERTIE_CI_HEADLESSMC_JAR")
    runtime_test = _tool(tmp_path, monkeypatch, "BERTIE_CI_MCRT_JAR")
    monkeypatch.delenv("BERTIE_CI_PACKWIZ_INSTALLER_JAR", raising=False)
    monkeypatch.delenv("BERTIE_CI_FIXTURES", raising=False)
    monkeypatch.delenv("BERTIE_CI_FIXTURE_PACK", raising=False)
    monkeypatch.delenv("BERTIE_CI_XVFB", raising=False)
    monkeypatch.delenv("BERTIE_CI_GLXINFO", raising=False)

    assert load_client_runtime_tools() == ClientRuntimeTools(
        java, headlessmc, runtime_test, None, None
    )


def test_pack_tools_require_no_runtime_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    java = _java_home(tmp_path, monkeypatch)
    installer = _tool(tmp_path, monkeypatch, "BERTIE_CI_PACKWIZ_INSTALLER_JAR")
    monkeypatch.delenv("BERTIE_CI_HEADLESSMC_JAR", raising=False)
    monkeypatch.delenv("BERTIE_CI_MCRT_JAR", raising=False)

    assert load_pack_tools() == PackTools(java, installer)

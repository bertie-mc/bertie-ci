from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Versions:
    minecraft: str
    neoforge: str
    java: str
    headlessmc: str
    mc_runtime_test: str
    packwiz_installer: str


@dataclass(frozen=True)
class PackTools:
    java: Path
    packwiz_installer: Path


@dataclass(frozen=True)
class FixtureTools(PackTools):
    fixtures: Path
    fixture_pack: Path | None


@dataclass(frozen=True)
class ServerRuntimeTools:
    java: Path
    headlessmc: Path


@dataclass(frozen=True)
class ClientRuntimeTools(ServerRuntimeTools):
    mc_runtime_test: Path
    xvfb: Path | None
    glxinfo: Path | None


def load_packwiz() -> Path:
    configured = os.environ.get("BERTIE_CI_PACKWIZ")
    executable = Path(configured) if configured else None
    if executable is None:
        discovered = shutil.which("packwiz")
        executable = Path(discovered) if discovered else None
    if executable is None or not executable.is_file():
        raise RuntimeError(
            "packwiz is unavailable; set BERTIE_CI_PACKWIZ or run through the Nix flake"
        )
    return executable


def load_packwiz_installer() -> Path:
    configured = os.environ.get("BERTIE_CI_PACKWIZ_INSTALLER_JAR")
    if not configured:
        raise RuntimeError(
            "packwiz-installer is unavailable; set BERTIE_CI_PACKWIZ_INSTALLER_JAR "
            "or run through the Nix flake"
        )
    installer = Path(configured)
    if not installer.is_file():
        raise RuntimeError(f"packwiz-installer not found at {installer}")
    return installer


def _versions_path() -> Path:
    configured = os.environ.get("BERTIE_CI_VERSIONS")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "versions.json"


def load_versions() -> Versions:
    data: dict[str, Any] = json.loads(_versions_path().read_text(encoding="utf-8"))
    return Versions(
        minecraft=data["minecraft"],
        neoforge=data["neoforge"],
        java=data["java"],
        headlessmc=data["headlessmc"]["version"],
        mc_runtime_test=data["mc_runtime_test"]["version"],
        packwiz_installer=data["packwiz_installer"]["version"],
    )


def load_java() -> Path:
    java_home = os.environ.get("BERTIE_CI_JAVA_HOME") or os.environ.get("JAVA_HOME")
    java_name = "java.exe" if os.name == "nt" else "java"
    if not java_home:
        raise RuntimeError(
            "Java 21 is unavailable; set JAVA_HOME or run through the Nix flake"
        )
    java = Path(java_home) / "bin" / java_name
    if not java.is_file():
        raise RuntimeError(f"Java not found at {java}")
    return java


def _configured_file(variable: str, label: str) -> Path:
    configured = os.environ.get(variable)
    if not configured:
        raise RuntimeError(
            f"{label} is unavailable; set {variable} or run through the Nix flake"
        )
    path = Path(configured)
    if not path.is_file():
        raise RuntimeError(f"{label} not found at {path}")
    return path


def load_pack_tools() -> PackTools:
    return PackTools(load_java(), load_packwiz_installer())


def load_fixture_tools() -> FixtureTools:
    fixture_root = os.environ.get("BERTIE_CI_FIXTURES")
    fixtures = (
        Path(fixture_root)
        if fixture_root
        else Path(__file__).resolve().parents[2] / "fixtures"
    )
    fixture_pack_root = os.environ.get("BERTIE_CI_FIXTURE_PACK")
    tools = FixtureTools(
        java=load_java(),
        packwiz_installer=load_packwiz_installer(),
        fixtures=fixtures,
        fixture_pack=Path(fixture_pack_root) if fixture_pack_root else None,
    )
    if not tools.fixtures.is_dir():
        raise RuntimeError(f"Fixture profiles not found at {tools.fixtures}")
    if tools.fixture_pack is not None and not (
        (tools.fixture_pack / "pack.toml").is_file()
        and (tools.fixture_pack / "mods").is_dir()
    ):
        raise RuntimeError(f"Canonical fixture pack not found at {tools.fixture_pack}")
    return tools


def load_server_runtime_tools() -> ServerRuntimeTools:
    return ServerRuntimeTools(
        java=load_java(),
        headlessmc=_configured_file("BERTIE_CI_HEADLESSMC_JAR", "HeadlessMC"),
    )


def load_client_runtime_tools() -> ClientRuntimeTools:
    xvfb = os.environ.get("BERTIE_CI_XVFB")
    glxinfo = os.environ.get("BERTIE_CI_GLXINFO")
    tools = ClientRuntimeTools(
        java=load_java(),
        headlessmc=_configured_file("BERTIE_CI_HEADLESSMC_JAR", "HeadlessMC"),
        mc_runtime_test=_configured_file("BERTIE_CI_MCRT_JAR", "mc-runtime-test"),
        xvfb=Path(xvfb) if xvfb else None,
        glxinfo=Path(glxinfo) if glxinfo else None,
    )
    for name, path in (
        ("Xvfb", tools.xvfb),
        ("glxinfo", tools.glxinfo),
    ):
        if path is not None and not path.is_file():
            raise RuntimeError(f"{name} not found at {path}")
    return tools

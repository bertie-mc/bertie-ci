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
class Tools:
    java: Path
    headlessmc: Path
    mc_runtime_test: Path
    packwiz_installer: Path
    fixtures: Path
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


def load_tools() -> Tools:
    headlessmc = os.environ.get("BERTIE_CI_HEADLESSMC_JAR")
    runtime_test = os.environ.get("BERTIE_CI_MCRT_JAR")
    if not headlessmc or not runtime_test:
        raise RuntimeError(
            "Runtime artifacts are unavailable; set BERTIE_CI_HEADLESSMC_JAR, "
            "BERTIE_CI_MCRT_JAR, and BERTIE_CI_PACKWIZ_INSTALLER_JAR or run through "
            "the Nix flake"
        )

    fixture_root = os.environ.get("BERTIE_CI_FIXTURES")
    fixtures = (
        Path(fixture_root)
        if fixture_root
        else Path(__file__).resolve().parents[2] / "fixtures"
    )
    xvfb = os.environ.get("BERTIE_CI_XVFB")
    glxinfo = os.environ.get("BERTIE_CI_GLXINFO")
    tools = Tools(
        java=load_java(),
        headlessmc=Path(headlessmc),
        mc_runtime_test=Path(runtime_test),
        packwiz_installer=load_packwiz_installer(),
        fixtures=fixtures,
        xvfb=Path(xvfb) if xvfb else None,
        glxinfo=Path(glxinfo) if glxinfo else None,
    )
    for name, path in (
        ("Java", tools.java),
        ("HeadlessMC", tools.headlessmc),
        ("mc-runtime-test", tools.mc_runtime_test),
        ("packwiz-installer", tools.packwiz_installer),
        ("Xvfb", tools.xvfb),
        ("glxinfo", tools.glxinfo),
    ):
        if path is not None and not path.is_file():
            raise RuntimeError(f"{name} not found at {path}")
    if not tools.fixtures.is_dir():
        raise RuntimeError(f"Fixture catalog not found at {tools.fixtures}")
    return tools

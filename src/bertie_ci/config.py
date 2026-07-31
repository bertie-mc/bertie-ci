from __future__ import annotations

import json
import os
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


@dataclass(frozen=True)
class Tools:
    java: Path
    headlessmc: Path
    mc_runtime_test: Path
    xvfb: Path | None
    glxinfo: Path | None


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
    )


def load_tools() -> Tools:
    java_home = os.environ.get("BERTIE_CI_JAVA_HOME") or os.environ.get("JAVA_HOME")
    java_name = "java.exe" if os.name == "nt" else "java"
    if not java_home:
        raise RuntimeError(
            "Java 21 is unavailable; set JAVA_HOME or run through the Nix flake"
        )

    headlessmc = os.environ.get("BERTIE_CI_HEADLESSMC_JAR")
    runtime_test = os.environ.get("BERTIE_CI_MCRT_JAR")
    if not headlessmc or not runtime_test:
        raise RuntimeError(
            "HeadlessHQ artifacts are unavailable; set BERTIE_CI_HEADLESSMC_JAR and "
            "BERTIE_CI_MCRT_JAR or run through the Nix flake"
        )

    xvfb = os.environ.get("BERTIE_CI_XVFB")
    glxinfo = os.environ.get("BERTIE_CI_GLXINFO")
    tools = Tools(
        java=Path(java_home) / "bin" / java_name,
        headlessmc=Path(headlessmc),
        mc_runtime_test=Path(runtime_test),
        xvfb=Path(xvfb) if xvfb else None,
        glxinfo=Path(glxinfo) if glxinfo else None,
    )
    for name, path in (
        ("Java", tools.java),
        ("HeadlessMC", tools.headlessmc),
        ("mc-runtime-test", tools.mc_runtime_test),
        ("Xvfb", tools.xvfb),
        ("glxinfo", tools.glxinfo),
    ):
        if path is not None and not path.is_file():
            raise RuntimeError(f"{name} not found at {path}")
    return tools

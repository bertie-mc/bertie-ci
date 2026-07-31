from __future__ import annotations

import shutil
import subprocess
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .instance import read_pack_versions
from .process import run


@dataclass(frozen=True)
class PackSummary:
    metafiles: int
    client: int
    server: int
    both: int
    config_files: int


def _toml(path: Path) -> dict[str, Any]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"Cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid TOML document: {path}")
    return data


def _relative_file(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Invalid {label}: {value!r}")
    relative = Path(value)
    if relative.is_absolute():
        raise RuntimeError(f"{label} must be relative: {value}")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise RuntimeError(f"{label} escapes the pack: {value}") from error
    if not resolved.is_file():
        raise RuntimeError(f"{label} not found: {value}")
    return resolved


def _pack_index(project: Path) -> tuple[Path, dict[str, Any]]:
    pack = _toml(project / "pack.toml")
    index_config = pack.get("index")
    if not isinstance(index_config, dict):
        raise RuntimeError("pack.toml has no [index] table")
    index_path = _relative_file(project, index_config.get("file"), "pack index")
    index = _toml(index_path)
    files = index.get("files")
    if not isinstance(files, list) or not all(isinstance(item, dict) for item in files):
        raise RuntimeError(f"Invalid [[files]] entries in {index_path}")
    return index_path, index


def indexed_files(project: Path) -> list[tuple[Path, bool]]:
    _, index = _pack_index(project)
    result: list[tuple[Path, bool]] = []
    for entry in index["files"]:
        result.append(
            (
                _relative_file(project, entry.get("file"), "indexed file"),
                entry.get("metafile") is True,
            )
        )
    return result


def _tracked_jars(project: Path) -> list[str]:
    if not (project / ".git").exists() and not (project / ".git").is_file():
        return []
    result = subprocess.run(
        ["git", "ls-files", "--", "*.jar"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return [line for line in result.stdout.splitlines() if line]


def validate_pack(project: Path, packwiz: Path) -> PackSummary:
    project = project.resolve(strict=True)
    source_index, _ = _pack_index(project)
    source_pack = project / "pack.toml"
    read_pack_versions(project)

    with tempfile.TemporaryDirectory(prefix="bertie-ci-pack-") as temporary:
        copy = Path(temporary) / "pack"
        shutil.copytree(
            project,
            copy,
            ignore=shutil.ignore_patterns(".git", ".bertie-ci", ".packwizcache"),
        )
        copied_index, _ = _pack_index(copy)
        run([packwiz, "refresh"], cwd=copy)
        stale = [
            name
            for name, source, refreshed in (
                ("pack.toml", source_pack, copy / "pack.toml"),
                (
                    source_index.relative_to(project).as_posix(),
                    source_index,
                    copied_index,
                ),
            )
            if source.read_bytes() != refreshed.read_bytes()
        ]
        if stale:
            raise RuntimeError(
                f"Pack index is stale ({', '.join(stale)}); run packwiz refresh and commit it"
            )

    sides = {"client": 0, "server": 0, "both": 0}
    filenames: dict[str, list[str]] = {}
    metafiles = 0
    for path, is_metafile in indexed_files(project):
        relative = path.relative_to(project)
        if relative.parts[0] == ".bertie-ci":
            raise RuntimeError(f"Generated bertie-ci state is indexed: {relative}")
        if not is_metafile:
            if path.suffix.lower() == ".jar":
                raise RuntimeError(f"Indexed mod JAR is forbidden: {relative}")
            continue
        metafiles += 1
        metadata = _toml(path)
        side = metadata.get("side")
        if side not in sides:
            raise RuntimeError(
                f"Metafile must declare side as client, server, or both: {path.relative_to(project)}"
            )
        sides[side] += 1
        filename = metadata.get("filename")
        if not isinstance(filename, str) or not filename:
            raise RuntimeError(
                f"Metafile has no download filename: {path.relative_to(project)}"
            )
        filenames.setdefault(filename.casefold(), []).append(
            path.relative_to(project).as_posix()
        )

    duplicates = {name: paths for name, paths in filenames.items() if len(paths) > 1}
    if duplicates:
        detail = "; ".join(
            f"{name}: {', '.join(paths)}" for name, paths in duplicates.items()
        )
        raise RuntimeError(f"Duplicate target filenames: {detail}")
    tracked = _tracked_jars(project)
    if tracked:
        raise RuntimeError(f"Tracked mod JARs are forbidden: {', '.join(tracked)}")
    config = project / "config"
    config_files = (
        sum(1 for path in config.rglob("*") if path.is_file()) if config.is_dir() else 0
    )
    return PackSummary(
        metafiles, sides["client"], sides["server"], sides["both"], config_files
    )


def export_client_pack(project: Path, output: Path, packwiz: Path) -> Path:
    project = project.resolve(strict=True)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="bertie-ci-client-export-") as temporary:
        copy = Path(temporary) / "pack"
        shutil.copytree(
            project,
            copy,
            ignore=shutil.ignore_patterns(".git", ".bertie-ci", ".packwizcache"),
        )
        run([packwiz, "modrinth", "export", "-o", output], cwd=copy)
    if not output.is_file():
        raise RuntimeError(f"packwiz did not create {output}")
    return output


def _write_server_scripts(root: Path, neoforge: str) -> None:
    start_sh = root / "start.sh"
    start_sh.write_text(
        f"""#!/usr/bin/env sh
set -eu
PACK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PACK_ROOT"
if [ ! -f eula.txt ]; then
  echo "Accept https://aka.ms/MinecraftEULA by writing eula=true to eula.txt."
  printf 'eula=false\\n' > eula.txt
  exit 1
fi
if [ ! -f run.sh ]; then
  curl -fsSL -o neoforge-installer.jar "https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge}/neoforge-{neoforge}-installer.jar"
  java -jar neoforge-installer.jar --installServer
  rm -f neoforge-installer.jar
  [ -f user_jvm_args.txt ] || printf '%s\\n' '-Xmx8G' '-Xms4G' > user_jvm_args.txt
fi
java -cp packwiz-installer.jar link.infra.packwiz.installer.Main --bootstrap-no-update -g -s server "file://$PACK_ROOT/pack/pack.toml"
exec ./run.sh nogui "$@"
""",
        encoding="utf-8",
    )
    start_sh.chmod(0o755)
    (root / "start.bat").write_text(
        f"""@echo off
setlocal
cd /d "%~dp0"
if not exist eula.txt (
  echo Accept https://aka.ms/MinecraftEULA by writing eula=true to eula.txt.
  echo eula=false>eula.txt
  exit /b 1
)
if not exist run.bat (
  curl -fsSL -o neoforge-installer.jar "https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge}/neoforge-{neoforge}-installer.jar"
  java -jar neoforge-installer.jar --installServer
  del neoforge-installer.jar
)
java -cp packwiz-installer.jar link.infra.packwiz.installer.Main --bootstrap-no-update -g -s server "file:///%CD:\\=/%/pack/pack.toml"
call run.bat nogui
""",
        encoding="utf-8",
    )


def _zip_tree(source: Path, output: Path) -> None:
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, strict_timestamps=False
    ) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source.parent).as_posix())


def export_server_pack(project: Path, output: Path, installer: Path) -> Path:
    project = project.resolve(strict=True)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    _, loader, loader_version = read_pack_versions(project)
    if loader != "neoforge":
        raise RuntimeError(f"Server export does not support loader {loader}")
    with tempfile.TemporaryDirectory(prefix="bertie-ci-server-export-") as temporary:
        root = Path(temporary) / output.stem
        pack = root / "pack"
        pack.mkdir(parents=True)
        source_index, _ = _pack_index(project)
        sources = [project / "pack.toml", source_index]
        sources.extend(path for path, _ in indexed_files(project))
        for source in sources:
            relative = source.relative_to(project)
            target = pack / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copy2(installer, root / "packwiz-installer.jar")
        readme = project / "README.md"
        if readme.is_file():
            shutil.copy2(readme, root / "README.md")
        _write_server_scripts(root, loader_version)
        _zip_tree(root, output)
    return output

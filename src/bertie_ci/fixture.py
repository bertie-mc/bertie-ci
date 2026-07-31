from __future__ import annotations

import hashlib
import json
import shutil
import tomllib
from pathlib import Path

from .config import Tools, Versions
from .process import run
from .web import serve_directory


def _hash(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as error:
        raise RuntimeError(f"Unsupported pack hash format: {algorithm}") from error
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    return _hash(path, "sha256")


def _load_profiles(root: Path) -> dict[str, list[str]]:
    data = json.loads((root / "profiles.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(name, str)
        and isinstance(entries, list)
        and all(isinstance(entry, str) for entry in entries)
        for name, entries in data.items()
    ):
        raise RuntimeError("Invalid fixture profile catalog")
    return data


def _load_defaults(root: Path, side: str) -> list[str]:
    data = json.loads((root / "defaults.json").read_text(encoding="utf-8"))
    entries = data.get(side) if isinstance(data, dict) else None
    if not isinstance(entries, list) or not all(
        isinstance(entry, str) for entry in entries
    ):
        raise RuntimeError(f"Invalid default fixture catalog for {side}")
    return entries


def _canonical_mods(pack: Path, versions: Versions) -> set[str]:
    pack_file = pack / "pack.toml"
    pack_data = tomllib.loads(pack_file.read_text(encoding="utf-8"))
    pack_versions = pack_data.get("versions")
    expected_versions = {
        "minecraft": versions.minecraft,
        "neoforge": versions.neoforge,
    }
    if not isinstance(pack_versions, dict) or any(
        pack_versions.get(name) != expected
        for name, expected in expected_versions.items()
    ):
        actual = {
            name: pack_versions.get(name) if isinstance(pack_versions, dict) else None
            for name in expected_versions
        }
        raise RuntimeError(
            f"Canonical pack versions {actual} do not match runtime {expected_versions}"
        )

    index_metadata = pack_data.get("index")
    if not isinstance(index_metadata, dict):
        raise RuntimeError("Canonical pack has no index metadata")
    index_name = index_metadata.get("file")
    index_hash_format = index_metadata.get("hash-format")
    index_hash = index_metadata.get("hash")
    if not all(
        isinstance(value, str) for value in (index_name, index_hash_format, index_hash)
    ):
        raise RuntimeError("Canonical pack index metadata is invalid")

    index = pack / str(index_name)
    if _hash(index, str(index_hash_format)) != index_hash:
        raise RuntimeError("Canonical pack index hash does not match pack.toml")
    index_data = tomllib.loads(index.read_text(encoding="utf-8"))
    file_hash_format = index_data.get("hash-format")
    files = index_data.get("files")
    if not isinstance(file_hash_format, str) or not isinstance(files, list):
        raise RuntimeError("Canonical pack index is invalid")

    mods: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise RuntimeError("Canonical pack index contains an invalid entry")
        path = entry.get("file")
        if not isinstance(path, str) or not path.startswith("mods/"):
            continue
        name = Path(path).name
        if path != f"mods/{name}" or not name.endswith(".pw.toml"):
            raise RuntimeError(f"Invalid canonical mod path: {path}")
        logical_name = name.removesuffix(".pw.toml")
        if logical_name in mods:
            raise RuntimeError(f"Duplicate canonical mod entry: {path}")
        if entry.get("metafile") is not True or not isinstance(entry.get("hash"), str):
            raise RuntimeError(f"Canonical mod entry is invalid: {path}")
        source = pack / path
        if not source.is_file() or _hash(source, file_hash_format) != entry["hash"]:
            raise RuntimeError(f"Canonical pack index is stale for {path}")
        mods.add(logical_name)
    return mods


def build_fixture_pack(
    root: Path,
    canonical_pack: Path,
    destination: Path,
    selected_profiles: list[str],
    versions: Versions,
    side: str,
) -> Path:
    profiles = _load_profiles(root)
    unknown = sorted(set(selected_profiles) - profiles.keys())
    if unknown:
        available = ", ".join(sorted(profiles))
        raise RuntimeError(
            f"Unknown fixture profile(s): {', '.join(unknown)}; available: {available}"
        )

    canonical_mods = _canonical_mods(canonical_pack, versions)

    entries = sorted(
        {
            *_load_defaults(root, side),
            *(entry for profile in selected_profiles for entry in profiles[profile]),
        }
    )
    if destination.exists():
        shutil.rmtree(destination)
    mods = destination / "mods"
    mods.mkdir(parents=True)

    index_lines = ['hash-format = "sha256"']
    for entry in entries:
        if entry not in canonical_mods:
            raise RuntimeError(f"Canonical pack mod entry not found: {entry}")
        source = canonical_pack / "mods" / f"{entry}.pw.toml"
        target = mods / source.name
        shutil.copy2(source, target)
        index_lines.extend(
            [
                "",
                "[[files]]",
                f'file = "mods/{target.name}"',
                f'hash = "{_sha256(target)}"',
                "metafile = true",
            ]
        )

    index = destination / "index.toml"
    index.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    pack = destination / "pack.toml"
    pack.write_text(
        "\n".join(
            [
                'name = "bertie-ci runtime fixture"',
                'pack-format = "packwiz:1.1.0"',
                "",
                "[index]",
                'file = "index.toml"',
                'hash-format = "sha256"',
                f'hash = "{_sha256(index)}"',
                "",
                "[versions]",
                f'minecraft = "{versions.minecraft}"',
                f'neoforge = "{versions.neoforge}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return pack


def install_fixtures(
    tools: Tools,
    versions: Versions,
    game_dir: Path,
    work: Path,
    profiles: list[str],
    side: str,
) -> None:
    if not profiles and not _load_defaults(tools.fixtures, side):
        return
    if tools.fixture_pack is None:
        raise RuntimeError(
            "Canonical bertie-pack checkout is unavailable; set "
            "BERTIE_CI_FIXTURE_PACK or run through the Nix flake"
        )
    pack = build_fixture_pack(
        tools.fixtures,
        tools.fixture_pack,
        work / "fixture-pack",
        profiles,
        versions,
        side,
    )
    selected = ", ".join(profiles) if profiles else "defaults only"
    print(f"Installing fixture profiles for {side}: {selected}", flush=True)
    with serve_directory(pack.parent) as url:
        run(
            [
                tools.java,
                "-cp",
                tools.packwiz_installer,
                "link.infra.packwiz.installer.Main",
                "--bootstrap-no-update",
                "-g",
                "-s",
                side,
                url,
            ],
            cwd=game_dir,
            log=work / "fixture-install.log",
            stream_output=False,
        )

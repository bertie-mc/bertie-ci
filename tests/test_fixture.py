import hashlib
import json
import os
import tomllib
from pathlib import Path

import pytest

from bertie_ci.config import Versions
from bertie_ci.fixture import build_fixture_pack

VERSIONS = Versions("1.21.1", "21.1.233", "21", "2.10.0", "4.5.1", "0.5.14")
BUNDLED_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CANONICAL_PACK = Path(
    os.environ.get(
        "BERTIE_CI_FIXTURE_PACK",
        Path(__file__).resolve().parents[2] / "bertie-pack",
    )
)


def _catalog(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "fixtures"
    root.mkdir()
    (root / "profiles.json").write_text(
        json.dumps({"base": ["one", "two"], "extra": ["two", "three"]}),
        encoding="utf-8",
    )
    (root / "defaults.json").write_text(
        json.dumps({"client": ["default"], "server": []}), encoding="utf-8"
    )
    pack = tmp_path / "bertie-pack"
    mods = pack / "mods"
    mods.mkdir(parents=True)
    files = []
    for name in ("default", "direct", "one", "three", "two"):
        metafile = mods / f"{name}.pw.toml"
        metafile.write_text(
            f'name = "{name}"\nfilename = "{name}.jar"\n', encoding="utf-8"
        )
        files.append(
            {
                "file": f"mods/{metafile.name}",
                "hash": hashlib.sha256(metafile.read_bytes()).hexdigest(),
                "metafile": True,
            }
        )
    index = pack / "index.toml"
    index.write_text(
        'hash-format = "sha256"\n\n'
        + "\n\n".join(
            "[[files]]\n"
            f'file = "{entry["file"]}"\n'
            f'hash = "{entry["hash"]}"\n'
            "metafile = true"
            for entry in files
        )
        + "\n",
        encoding="utf-8",
    )
    (pack / "pack.toml").write_text(
        'name = "test pack"\n'
        'pack-format = "packwiz:1.1.0"\n\n'
        '[index]\nfile = "index.toml"\nhash-format = "sha256"\n'
        f'hash = "{hashlib.sha256(index.read_bytes()).hexdigest()}"\n\n'
        '[versions]\nminecraft = "1.21.1"\nneoforge = "21.1.233"\n',
        encoding="utf-8",
    )
    return root, pack


def test_build_fixture_pack_composes_and_hashes_profiles(tmp_path: Path) -> None:
    destination = tmp_path / "generated"
    profiles, pack_source = _catalog(tmp_path)
    pack = build_fixture_pack(
        profiles,
        pack_source,
        destination,
        ["base", "direct", "extra"],
        VERSIONS,
        "client",
    )

    pack_data = tomllib.loads(pack.read_text(encoding="utf-8"))
    index = destination / pack_data["index"]["file"]
    assert pack_data["index"]["hash"] == hashlib.sha256(index.read_bytes()).hexdigest()

    index_data = tomllib.loads(index.read_text(encoding="utf-8"))
    assert [entry["file"] for entry in index_data["files"]] == [
        "mods/default.pw.toml",
        "mods/direct.pw.toml",
        "mods/one.pw.toml",
        "mods/three.pw.toml",
        "mods/two.pw.toml",
    ]
    assert all(entry["metafile"] for entry in index_data["files"])
    assert (destination / "mods" / "one.pw.toml").read_bytes() == (
        pack_source / "mods" / "one.pw.toml"
    ).read_bytes()


def test_build_fixture_pack_rejects_unknown_selector(tmp_path: Path) -> None:
    profiles, pack_source = _catalog(tmp_path)
    with pytest.raises(RuntimeError, match="Unknown fixture selector.*canonical pack"):
        build_fixture_pack(
            profiles,
            pack_source,
            tmp_path / "generated",
            ["missing"],
            VERSIONS,
            "server",
        )


def test_build_fixture_pack_rejects_single_mod_profile(tmp_path: Path) -> None:
    profiles, pack_source = _catalog(tmp_path)
    (profiles / "profiles.json").write_text(
        json.dumps({"one": ["one"]}), encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="aggregate at least two mods"):
        build_fixture_pack(
            profiles,
            pack_source,
            tmp_path / "generated",
            ["one"],
            VERSIONS,
            "server",
        )


def test_build_fixture_pack_rejects_stale_canonical_index(tmp_path: Path) -> None:
    profiles, pack_source = _catalog(tmp_path)
    (pack_source / "mods" / "one.pw.toml").write_text(
        'name = "changed"\nfilename = "one.jar"\n', encoding="utf-8"
    )

    with pytest.raises(
        RuntimeError, match="Canonical pack index is stale for mods/one"
    ):
        build_fixture_pack(
            profiles,
            pack_source,
            tmp_path / "generated",
            ["base"],
            VERSIONS,
            "server",
        )


def test_build_fixture_pack_rejects_wrong_canonical_pack_version(
    tmp_path: Path,
) -> None:
    profiles, pack_source = _catalog(tmp_path)
    pack_toml = pack_source / "pack.toml"
    pack_toml.write_text(
        pack_toml.read_text(encoding="utf-8").replace("21.1.233", "21.1.217"),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Canonical pack versions.*21.1.217"):
        build_fixture_pack(
            profiles,
            pack_source,
            tmp_path / "generated",
            ["base"],
            VERSIONS,
            "server",
        )


def test_bundled_fixture_profiles_reference_canonical_pack(
    tmp_path: Path,
) -> None:
    profiles = json.loads(
        (BUNDLED_FIXTURES / "profiles.json").read_text(encoding="utf-8")
    )
    defaults = json.loads(
        (BUNDLED_FIXTURES / "defaults.json").read_text(encoding="utf-8")
    )
    direct = {"create", "fdlib", "immersive-armors", "refined-storage"}
    names = direct | {
        name for entries in [*profiles.values(), *defaults.values()] for name in entries
    }

    build_fixture_pack(
        BUNDLED_FIXTURES,
        CANONICAL_PACK,
        tmp_path / "generated",
        [*profiles, *direct],
        VERSIONS,
        "client",
    )

    for name in names:
        metafile = CANONICAL_PACK / "mods" / f"{name}.pw.toml"
        data = tomllib.loads(metafile.read_text(encoding="utf-8"))
        assert data["filename"].endswith(".jar")
        download = data["download"]
        assert download.get("url", "https://metadata").startswith("https://")
        assert download.get("url") or download.get("mode", "").startswith("metadata:")
        assert download["hash-format"] in hashlib.algorithms_available
        assert download["hash"]

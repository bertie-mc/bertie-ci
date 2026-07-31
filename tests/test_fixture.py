import hashlib
import json
import tomllib
from pathlib import Path

import pytest

from bertie_ci.config import Versions
from bertie_ci.fixture import build_fixture_pack


VERSIONS = Versions("1.21.1", "21.1.233", "21", "2.10.0", "4.5.1", "0.5.14")
BUNDLED_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _catalog(tmp_path: Path) -> Path:
    root = tmp_path / "fixtures"
    catalog = root / "catalog"
    catalog.mkdir(parents=True)
    (root / "profiles.json").write_text(
        json.dumps({"base": ["one", "two"], "extra": ["two"]}),
        encoding="utf-8",
    )
    (root / "defaults.json").write_text(
        json.dumps({"client": ["default"], "server": []}), encoding="utf-8"
    )
    for name in ("default", "one", "two"):
        (catalog / f"{name}.pw.toml").write_text(
            f'name = "{name}"\nfilename = "{name}.jar"\n', encoding="utf-8"
        )
    return root


def test_build_fixture_pack_composes_and_hashes_profiles(tmp_path: Path) -> None:
    destination = tmp_path / "generated"
    pack = build_fixture_pack(
        _catalog(tmp_path), destination, ["base", "extra"], VERSIONS, "client"
    )

    pack_data = tomllib.loads(pack.read_text(encoding="utf-8"))
    index = destination / pack_data["index"]["file"]
    assert pack_data["index"]["hash"] == hashlib.sha256(index.read_bytes()).hexdigest()

    index_data = tomllib.loads(index.read_text(encoding="utf-8"))
    assert [entry["file"] for entry in index_data["files"]] == [
        "mods/default.pw.toml",
        "mods/one.pw.toml",
        "mods/two.pw.toml",
    ]
    assert all(entry["metafile"] for entry in index_data["files"])


def test_build_fixture_pack_rejects_unknown_profile(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Unknown fixture profile.*available: base"):
        build_fixture_pack(
            _catalog(tmp_path),
            tmp_path / "generated",
            ["missing"],
            VERSIONS,
            "server",
        )


def test_bundled_fixture_profiles_reference_pinned_catalog_entries() -> None:
    profiles = json.loads(
        (BUNDLED_FIXTURES / "profiles.json").read_text(encoding="utf-8")
    )
    defaults = json.loads(
        (BUNDLED_FIXTURES / "defaults.json").read_text(encoding="utf-8")
    )
    names = {
        name for entries in [*profiles.values(), *defaults.values()] for name in entries
    }

    for name in names:
        metafile = BUNDLED_FIXTURES / "catalog" / f"{name}.pw.toml"
        data = tomllib.loads(metafile.read_text(encoding="utf-8"))
        assert data["filename"].endswith(".jar")
        download = data["download"]
        assert download.get("url", "https://metadata").startswith("https://")
        assert download.get("url") or download.get("mode", "").startswith("metadata:")
        assert download["hash-format"] in hashlib.algorithms_available
        assert download["hash"]

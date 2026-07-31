import os
from pathlib import Path
from zipfile import ZipFile

import pytest

import bertie_ci.pack as pack_module
from bertie_ci.pack import export_server_pack, validate_pack


def _pack(root: Path, second_filename: str | None = None) -> None:
    mods = root / "mods"
    config = root / "config"
    mods.mkdir()
    config.mkdir()
    (config / "example.json").write_text("{}\n", encoding="utf-8")
    (mods / "example.pw.toml").write_text(
        'name = "Example"\nfilename = "example.jar"\nside = "both"\n\n'
        '[download]\nurl = "https://example.invalid/example.jar"\n'
        'hash-format = "sha256"\nhash = "00"\n',
        encoding="utf-8",
    )
    entries = [
        '[[files]]\nfile = "config/example.json"\nhash = "00"',
        '[[files]]\nfile = "mods/example.pw.toml"\nhash = "00"\nmetafile = true',
    ]
    if second_filename is not None:
        (mods / "second.pw.toml").write_text(
            f'name = "Second"\nfilename = "{second_filename}"\nside = "client"\n\n'
            '[download]\nurl = "https://example.invalid/second.jar"\n'
            'hash-format = "sha256"\nhash = "00"\n',
            encoding="utf-8",
        )
        entries.append(
            '[[files]]\nfile = "mods/second.pw.toml"\nhash = "00"\nmetafile = true'
        )
    (root / "index.toml").write_text(
        'hash-format = "sha256"\n\n' + "\n\n".join(entries) + "\n",
        encoding="utf-8",
    )
    (root / "pack.toml").write_text(
        'name = "Example"\nversion = "1.0.0"\npack-format = "packwiz:1.1.0"\n\n'
        '[index]\nfile = "index.toml"\nhash-format = "sha256"\nhash = "00"\n\n'
        '[versions]\nminecraft = "1.21.1"\nneoforge = "21.1.233"\n',
        encoding="utf-8",
    )


def test_validate_pack_is_read_only_and_reports_sides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pack(tmp_path)
    before = (tmp_path / "index.toml").read_bytes()
    monkeypatch.setattr(pack_module, "run", lambda *args, **kwargs: None)

    summary = validate_pack(tmp_path, Path("packwiz"))

    assert summary.metafiles == 1
    assert summary.both == 1
    assert summary.config_files == 1
    assert (tmp_path / "index.toml").read_bytes() == before


def test_validate_pack_rejects_duplicate_download_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pack(tmp_path, "example.jar")
    monkeypatch.setattr(pack_module, "run", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="Duplicate target filenames"):
        validate_pack(tmp_path, Path("packwiz"))


def test_validate_pack_rejects_generated_state_in_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pack(tmp_path)
    generated = tmp_path / ".bertie-ci" / "runtime.log"
    generated.parent.mkdir()
    generated.write_text("generated", encoding="utf-8")
    with (tmp_path / "index.toml").open("a", encoding="utf-8") as index:
        index.write('\n[[files]]\nfile = ".bertie-ci/runtime.log"\nhash = "00"\n')
    monkeypatch.setattr(pack_module, "run", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="Generated bertie-ci state is indexed"):
        validate_pack(tmp_path, Path("packwiz"))


def test_export_server_pack_contains_manifest_not_mod_jars(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _pack(project)
    installer = tmp_path / "packwiz-installer.jar"
    installer.write_bytes(b"installer")
    os.utime(installer, (0, 0))
    output = tmp_path / "example-server.zip"

    export_server_pack(project, output, installer)

    with ZipFile(output) as archive:
        names = set(archive.namelist())
        root = "example-server"
        assert f"{root}/pack/pack.toml" in names
        assert f"{root}/pack/mods/example.pw.toml" in names
        assert f"{root}/packwiz-installer.jar" in names
        assert f"{root}/start.sh" in names
        assert not any(name.endswith("example.jar") for name in names)

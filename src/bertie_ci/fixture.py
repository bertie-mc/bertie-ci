from __future__ import annotations

import hashlib
import json
import shutil
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from .config import Tools, Versions
from .process import run


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def build_fixture_pack(
    root: Path,
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
        source = root / "catalog" / f"{entry}.pw.toml"
        if not source.is_file():
            raise RuntimeError(f"Fixture catalog entry not found: {entry}")
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


@contextmanager
def _serve(directory: Path) -> Iterator[str]:
    handler = partial(_QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}/pack.toml"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def install_fixtures(
    tools: Tools,
    versions: Versions,
    runtime: Path,
    profiles: list[str],
    side: str,
) -> None:
    if not profiles and not _load_defaults(tools.fixtures, side):
        return
    pack = build_fixture_pack(
        tools.fixtures, runtime / "fixture-pack", profiles, versions, side
    )
    selected = ", ".join(profiles) if profiles else "defaults only"
    print(f"Installing fixture profiles for {side}: {selected}", flush=True)
    with _serve(pack.parent) as url:
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
            cwd=runtime / "run",
            log=runtime / "fixture-install.log",
            stream_output=False,
        )

from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from bertie_ci.web import serve_directory


def test_serve_directory_uses_ipv6_loopback(tmp_path: Path) -> None:
    entry = tmp_path / "pack.toml"
    entry.write_text('name = "fixture"\n', encoding="utf-8")

    with serve_directory(tmp_path) as url:
        assert url.startswith("http://[::1]:")
        response = build_opener(ProxyHandler({})).open(url)
        assert response.read() == entry.read_bytes()

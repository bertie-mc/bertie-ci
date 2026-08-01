from __future__ import annotations

import socket
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


class _IPv6ThreadingHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6


@contextmanager
def serve_directory(directory: Path, entry: str = "pack.toml") -> Iterator[str]:
    handler = partial(_QuietHandler, directory=str(directory))
    server = _IPv6ThreadingHTTPServer(("::1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://[::1]:{port}/{entry}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
